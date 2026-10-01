"""Teacher-owned providers. No silent demo responses on real-service errors."""
from __future__ import annotations
import array
import asyncio
import base64
import hashlib
import hmac
import io
import ipaddress
import json
import logging
import math
import os
import socket
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import httpx

ASR_LOG=logging.getLogger('english-class.asr')


class ProviderError(RuntimeError):
    """code：供应商错误码或本地分类（Timeout/HTTPError/MalformedResponse…）；request_id：供应商返回的请求编号。"""
    def __init__(self,message:str,*,code:str|None=None,request_id:str|None=None):
        super().__init__(message);self.code=code;self.request_id=request_id


def validate_wav(data:bytes) -> tuple[bytes,int]:
    try:
        with wave.open(io.BytesIO(data),'rb') as w:
            if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getframerate()!=16000 or w.getcomptype()!='NONE':
                raise ValueError('音频须为16kHz、单声道、16位PCM WAV')
            frames=w.readframes(w.getnframes())
            if not 320 <= len(frames) <= 16000*2*30:
                raise ValueError('录音应介于0.01秒和30秒之间')
            if len(frames)!=w.getnframes()*2: raise ValueError('WAV数据不完整')
            return frames,16000
    except (wave.Error,EOFError) as exc:
        raise ValueError('无法读取WAV音频') from exc


def validate_llm_url(url:str,resolve=socket.getaddrinfo) -> str:
    """学生自带的大模型地址：只允许 https 公网地址，防止借服务器访问内网/本机服务。"""
    if not isinstance(url,str) or len(url)>300: raise ValueError('接口地址无效')
    url=url.strip().rstrip('/')
    if url.endswith('/chat/completions'): url=url[:-len('/chat/completions')]
    try: parts=urlsplit(url);port=parts.port
    except ValueError as exc: raise ValueError('接口地址无效') from exc
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('接口地址须为 https:// 开头的公网地址，例如 https://api.deepseek.com')
    try: literal=ipaddress.ip_address(parts.hostname)
    except ValueError: literal=None
    if literal is not None and not literal.is_global: raise ValueError('接口地址不能指向内网或本机')
    try: infos=resolve(parts.hostname,port or 443,type=socket.SOCK_STREAM)
    except (OSError,UnicodeError) as exc: raise ValueError('接口域名无法解析') from exc
    addrs={ipaddress.ip_address(i[4][0].split('%')[0]) for i in infos}
    if not addrs or any(not a.is_global for a in addrs): raise ValueError('接口地址不能指向内网或本机')
    return url


def mask_key(key:str) -> str:
    return (key[:3]+'…'+key[-4:]) if len(key)>=12 else '已设置'


GATE_FRAME_MS=30
GATE_FLOOR_PERCENTILE=0.05   # 底噪取最安静的5%帧：树莓派录音前后都有静音，这部分就是环境底噪
GATE_FLOOR_RATIO=2.5         # 有声帧须高于底噪2.5倍（持续白噪声每帧都差不多响，过不了）
GATE_MIN_RUN=2               # 至少连续2帧（60毫秒）有声：一个单词能过，一下咔哒声过不了


def has_speech(pcm:bytes,min_rms:float,rate:int=16000) -> bool:
    """粗判是否有人说话：按30毫秒分帧，看“有声帧”是否连续出现。
    有声帧 = 音量≥min_rms 且 ≥底噪×2.5。不看整段的高分位音量——
    树莓派切出的录音有约0.3秒前导和1秒尾部静音，只说一个短词时有声帧不到一成，高分位会落在静音上。"""
    a=array.array('h');a.frombytes(pcm[:len(pcm)//2*2])
    size=rate*GATE_FRAME_MS//1000
    levels=[math.sqrt(sum(v*v for v in a[i:i+size])/size) for i in range(0,len(a)-size+1,size)]
    if not levels: return False
    floor=sorted(levels)[int(len(levels)*GATE_FLOOR_PERCENTILE)]
    threshold=max(min_rms,GATE_FLOOR_RATIO*max(floor,1.0))
    run=0
    for level in levels:
        run=run+1 if level>=threshold else 0
        if run>=GATE_MIN_RUN: return True
    return False


TENCENT_ASR_HOST='asr.tencentcloudapi.com'
TENCENT_ASR_ENGINES={'en':'16k_en','zh':'16k_zh'}


def tc3_authorization(secret_id:str,secret_key:str,service:str,host:str,body:bytes,timestamp:int) -> str:
    """腾讯云 API 3.0 TC3-HMAC-SHA256 签名（POST，签 content-type 与 host）。"""
    date=datetime.fromtimestamp(timestamp,timezone.utc).strftime('%Y-%m-%d')
    canonical='\n'.join(['POST','/','',f'content-type:application/json; charset=utf-8\nhost:{host}\n',
                         'content-type;host',hashlib.sha256(body).hexdigest()])
    scope=f'{date}/{service}/tc3_request'
    to_sign='\n'.join(['TC3-HMAC-SHA256',str(timestamp),scope,hashlib.sha256(canonical.encode()).hexdigest()])
    def sign(key:bytes,msg:str) -> bytes: return hmac.new(key,msg.encode(),hashlib.sha256).digest()
    k=sign(sign(sign(('TC3'+secret_key).encode(),date),service),'tc3_request')
    signature=hmac.new(k,to_sign.encode(),hashlib.sha256).hexdigest()
    return f'TC3-HMAC-SHA256 Credential={secret_id}/{scope}, SignedHeaders=content-type;host, Signature={signature}'


def pcm_wav(pcm:bytes,rate:int=16000) -> bytes:
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm)
    return out.getvalue()

@dataclass
class Providers:
    llm_base:str='https://api.deepseek.com'
    llm_key:str=''
    llm_model:str='deepseek-flash'
    asr_backend:str='vosk'
    asr_base:str=''
    asr_key:str=''
    asr_model:str=''
    asr_language_map:str=''          # 例 en:English,zh:Chinese（Qwen3-ASR 要求语言全名）
    asr_fallback:str=''              # vosk：云端失败/超时改用本机 Vosk
    asr_timeout:float=8.0
    asr_retry_after:float=60.0       # 云端失败后这段时间直接走本机，不让每轮都等超时
    tencent_secret_id:str=field(default='',repr=False)   # asr_backend=tencent：腾讯云一句话识别
    tencent_secret_key:str=field(default='',repr=False)
    asr_min_rms:float=200.0          # 云端模式（http/tencent）：低于此音量或没有起伏的录音按“没听清”处理；0 关闭
    vosk_en:str='models/vosk-model-small-en-us-0.15'
    vosk_zh:str='models/vosk-model-small-cn-0.22'
    tts_backend:str='edge'
    tts_base:str=''
    tts_key:str=''
    tts_model:str=''
    tts_voice:str='alloy'
    voice_en:str='en-US-JennyNeural'
    voice_zh:str='zh-CN-XiaoxiaoNeural'
    _models:dict=field(default_factory=dict,init=False,repr=False)
    _asr_down_until:float=field(default=0.0,init=False,repr=False)

    @classmethod
    def from_env(cls):
        mapping={'llm_base':'LLM_BASE_URL','llm_key':'LLM_API_KEY','llm_model':'LLM_MODEL',
                 'asr_backend':'ASR_BACKEND','asr_base':'ASR_BASE_URL','asr_key':'ASR_API_KEY','asr_model':'ASR_MODEL',
                 'asr_language_map':'ASR_LANGUAGE_MAP','asr_fallback':'ASR_FALLBACK','asr_timeout':'ASR_TIMEOUT',
                 'asr_retry_after':'ASR_RETRY_AFTER','asr_min_rms':'ASR_MIN_RMS',
                 'tencent_secret_id':'TENCENT_SECRET_ID','tencent_secret_key':'TENCENT_SECRET_KEY',
                 'vosk_en':'VOSK_EN_PATH','vosk_zh':'VOSK_ZH_PATH','tts_backend':'TTS_BACKEND',
                 'tts_base':'TTS_BASE_URL','tts_key':'TTS_API_KEY','tts_model':'TTS_MODEL','tts_voice':'TTS_VOICE',
                 'voice_en':'TTS_VOICE_EN','voice_zh':'TTS_VOICE_ZH'}
        values={k:os.environ[v] for k,v in mapping.items() if v in os.environ}
        for k in ('asr_timeout','asr_retry_after','asr_min_rms'):
            if k in values: values[k]=float(values[k])
        return cls(**values)

    def check_llm_url(self,url:str) -> str:
        return validate_llm_url(url)

    async def chat(self,messages:list[dict],json_output:bool=False,llm:dict|None=None,timeout:float|None=None) -> str:
        """llm 为学生自带配置 {base_url,model,api_key}；None 时用老师平台的模型。timeout 为整次调用上限（秒）。"""
        if llm:
            try: base=validate_llm_url(llm['base_url'])
            except ValueError as exc: raise ProviderError(str(exc)) from exc
            key,model=llm['api_key'],llm['model']
            payload={'model':model,'messages':messages,'max_tokens':900,'temperature':0.3,'stream':False}
        else:
            if not self.llm_key: raise ProviderError('老师尚未配置LLM_API_KEY；不会使用假对话代替')
            base,key,model=self.llm_base,self.llm_key,self.llm_model
            payload={'model':model,'messages':messages,'thinking':{'type':'disabled'},'max_tokens':900,'temperature':0.3,'stream':False}
        if json_output: payload['response_format']={'type':'json_object'}
        try:
            limit=timeout or 45
            async with httpx.AsyncClient(timeout=httpx.Timeout(limit,connect=min(10,limit)),follow_redirects=False) as c:
                # wait_for 限制整次调用（含慢速流式返回），保证保存测试在小程序超时之前返回。
                r=await asyncio.wait_for(c.post(base.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload),limit)
                if llm and r.status_code in (401,403): raise ProviderError('自带模型的密钥无效或无权限')
                if llm and r.status_code==404: raise ProviderError('自带模型的接口地址或模型名不对')
                if llm and r.status_code==429: raise ProviderError('自带模型额度不足或请求过快')
                r.raise_for_status();obj=r.json();choice=obj['choices'][0]
                if choice.get('finish_reason') not in ('stop',None): raise ProviderError('模型输出未正常完成，请重试这一轮')
                content=choice['message']['content']
                if not isinstance(content,str) or not content.strip(): raise ProviderError('模型没有返回有效回答')
                return content
        except (asyncio.TimeoutError,httpx.TimeoutException) as exc:
            raise ProviderError('自带模型响应太慢（超时）' if llm else '模型响应超时，请重试这一轮') from exc
        except (httpx.HTTPError,KeyError,ValueError,IndexError) as exc:
            raise ProviderError(('自带模型调用失败' if llm else '模型调用失败；请检查公共层模型名、接口地址和凭证')) from exc

    async def transcribe(self,data:bytes,language:str) -> dict:
        started=time.monotonic()
        result=await self._transcribe(data,language)
        if self.asr_backend in ('http','tencent'):
            # 只记诊断字段；不记密钥、签名、音频或识别文本。
            ASR_LOG.info('asr backend=%s provider=%s fallback=%d code=%s request_id=%s ms=%d unclear=%d',
                         self.asr_backend,result.get('provider'),int(result.get('provider')=='vosk-fallback'),
                         result.get('fallback_reason') or '-',result.get('request_id') or '-',
                         int((time.monotonic()-started)*1000),int(bool(result.get('unclear'))))
        return result

    async def _transcribe(self,data:bytes,language:str) -> dict:
        pcm,rate=validate_wav(data)
        if self.asr_backend=='vosk':
            return await asyncio.to_thread(self._vosk,pcm,rate,language)
        if self.asr_backend not in ('http','tencent'): raise ProviderError('ASR_BACKEND只能为vosk、http或tencent')
        if self.asr_backend=='http' and not (self.asr_base and self.asr_model): raise ProviderError('老师尚未配置兼容ASR服务')
        if self.asr_backend=='tencent' and not (self.tencent_secret_id and self.tencent_secret_key):
            raise ProviderError('老师尚未配置腾讯云语音识别密钥')
        # 云端模型对静音/持续噪声会编出 "Okay." 之类的句子；这类录音直接按“没听清”处理，不送识别、不降级。
        if self.asr_min_rms>0 and not has_speech(pcm,self.asr_min_rms):
            return {'text':'','confidence':None,'unclear':True,'provider':'gate'}
        if self.asr_fallback=='vosk' and time.monotonic()<self._asr_down_until:
            return await self._asr_fallback(pcm,rate,language,'CoolingDown')
        call=self._tencent_asr(data,language) if self.asr_backend=='tencent' else self._http_asr(data,language)
        try:
            # wait_for 限制整次调用；httpx 的读超时只管“两块数据之间”，慢速分块返回会远超 ASR_TIMEOUT。
            return await asyncio.wait_for(call,self.asr_timeout)
        except asyncio.TimeoutError:
            error=ProviderError('语音识别服务响应超时；本轮不计为答错',code='Timeout')
        except ProviderError as exc: error=exc
        if self.asr_fallback!='vosk': raise error
        self._asr_down_until=time.monotonic()+self.asr_retry_after
        return await self._asr_fallback(pcm,rate,language,error.code or 'Error',error.request_id)

    async def _asr_fallback(self,pcm:bytes,rate:int,language:str,reason:str,request_id:str|None=None) -> dict:
        result=await asyncio.to_thread(self._vosk,pcm,rate,language)
        out={**result,'provider':'vosk-fallback','fallback_reason':reason}
        if request_id: out['request_id']=request_id
        return out

    def _asr_language(self,language:str) -> str:
        names=dict(x.split(':',1) for x in self.asr_language_map.split(',') if ':' in x)
        return names.get(language,language).strip()

    async def _tencent_asr(self,data:bytes,language:str) -> dict:
        body=json.dumps({'EngSerViceType':TENCENT_ASR_ENGINES.get(language,'16k_en'),'SourceType':1,'VoiceFormat':'wav',
                         'Data':base64.b64encode(data).decode(),'DataLen':len(data),'FilterDirty':0,'ConvertNumMode':0},
                        separators=(',',':')).encode()
        ts=int(time.time())
        headers={'Authorization':tc3_authorization(self.tencent_secret_id,self.tencent_secret_key,'asr',TENCENT_ASR_HOST,body,ts),
                 'Content-Type':'application/json; charset=utf-8','Host':TENCENT_ASR_HOST,
                 'X-TC-Action':'SentenceRecognition','X-TC-Version':'2019-06-14','X-TC-Timestamp':str(ts)}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.asr_timeout,connect=min(3.0,self.asr_timeout)),trust_env=False) as c:
                r=await c.post(f'https://{TENCENT_ASR_HOST}/',headers=headers,content=body)
                r.raise_for_status();obj=r.json()
        except httpx.TimeoutException as exc:
            raise ProviderError('语音识别服务响应超时；本轮不计为答错',code='Timeout') from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError('语音识别服务调用失败；本轮不计为答错',code=f'HTTP{exc.response.status_code}') from exc
        except httpx.HTTPError as exc:
            raise ProviderError('语音识别服务调用失败；本轮不计为答错',code='NetworkError') from exc
        except ValueError as exc:
            raise ProviderError('语音识别服务返回格式异常；本轮不计为答错',code='MalformedResponse') from exc
        return self._parse_tencent(obj)

    @staticmethod
    def _parse_tencent(obj) -> dict:
        """严格解析：只有字符串 Result 才算识别成功；其余一律是协议错误（走降级，不算“没听清”）。"""
        resp=obj.get('Response') if isinstance(obj,dict) else None
        if not isinstance(resp,dict):
            raise ProviderError('腾讯云语音识别返回格式异常；本轮不计为答错',code='MalformedResponse')
        rid=resp.get('RequestId') if isinstance(resp.get('RequestId'),str) else None
        if 'Error' in resp:
            err=resp['Error']
            code=err['Code'] if isinstance(err,dict) and isinstance(err.get('Code'),str) and err['Code'] else 'MalformedError'
            raise ProviderError(f'腾讯云语音识别返回错误（{code}）；本轮不计为答错',code=code,request_id=rid)
        result=resp.get('Result')
        if not isinstance(result,str):
            raise ProviderError('腾讯云语音识别返回格式异常；本轮不计为答错',code='MalformedResponse',request_id=rid)
        text=result.strip()
        out={'text':text,'confidence':None,'unclear':not text,'provider':'tencent'}
        if rid: out['request_id']=rid
        return out

    async def _http_asr(self,data:bytes,language:str) -> dict:
        headers={'Authorization':'Bearer '+self.asr_key} if self.asr_key else {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.asr_timeout,connect=min(3.0,self.asr_timeout)),trust_env=False) as c:
                r=await c.post(self.asr_base.rstrip('/')+'/audio/transcriptions',headers=headers,
                               files={'file':('speech.wav',data,'audio/wav')},
                               data={'model':self.asr_model,'language':self._asr_language(language),'response_format':'json'})
                r.raise_for_status();obj=r.json()
        except httpx.TimeoutException as exc:
            raise ProviderError('语音识别服务响应超时；本轮不计为答错',code='Timeout') from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError('语音识别服务调用失败；本轮不计为答错',code=f'HTTP{exc.response.status_code}') from exc
        except httpx.HTTPError as exc:
            raise ProviderError('语音识别服务调用失败；本轮不计为答错',code='NetworkError') from exc
        except ValueError as exc:
            raise ProviderError('语音识别服务返回格式异常；本轮不计为答错',code='MalformedResponse') from exc
        text=obj.get('text') if isinstance(obj,dict) else None
        if not isinstance(text,str):
            raise ProviderError('语音识别服务返回格式异常；本轮不计为答错',code='MalformedResponse')
        text=text.strip()
        # No confidence value is invented when the provider does not return one.
        return {'text':text,'confidence':None,'unclear':not text,'provider':'http'}

    def _vosk(self,pcm:bytes,rate:int,language:str) -> dict:
        path=self.vosk_zh if language=='zh' else self.vosk_en
        if not Path(path).is_dir(): raise ProviderError('Vosk语言模型未安装，请先执行模型下载脚本')
        try:
            import vosk
            if path not in self._models:
                self._models[path]=vosk.Model(path)
            rec=vosk.KaldiRecognizer(self._models[path],rate)
            rec.SetWords(True)
            # Intentionally no expected-answer-only grammar: incorrect answers must survive recognition.
            partials=[]
            for i in range(0,len(pcm),8000):
                if rec.AcceptWaveform(pcm[i:i+8000]): partials.append(json.loads(rec.Result()))
            partials.append(json.loads(rec.FinalResult()))
            text=' '.join(x.get('text','') for x in partials).strip()
            confs=[w.get('conf',0) for p in partials for w in p.get('result',[])]
            confidence=sum(confs)/len(confs) if confs else None
            return {'text':text,'confidence':confidence,'unclear':not text or (confidence is not None and confidence<0.65),'provider':'vosk'}
        except ImportError as exc: raise ProviderError('公共层尚未安装vosk依赖') from exc
        except ProviderError: raise
        except Exception as exc: raise ProviderError('Vosk识别失败；本轮不计为答错') from exc

    async def speak(self,segments:list[dict],slow:bool=False) -> bytes:
        pcm_parts=[]
        for segment in segments:
            if self.tts_backend=='edge':
                try:
                    import edge_tts
                    voice=self.voice_zh if segment['language']=='zh' else self.voice_en
                    chunks=[]
                    async for chunk in edge_tts.Communicate(segment['text'],voice,rate='-20%' if slow else '-5%').stream():
                        if chunk['type']=='audio': chunks.append(chunk['data'])
                    audio=b''.join(chunks)
                except Exception as exc: raise ProviderError('Edge语音合成不可用；可由老师配置兼容TTS服务') from exc
            elif self.tts_backend=='http':
                if not (self.tts_base and self.tts_key and self.tts_model): raise ProviderError('兼容TTS服务尚未配置')
                try:
                    async with httpx.AsyncClient(timeout=40) as c:
                        r=await c.post(self.tts_base.rstrip('/')+'/audio/speech',headers={'Authorization':'Bearer '+self.tts_key},
                            json={'model':self.tts_model,'input':segment['text'],'voice':self.tts_voice,'response_format':'mp3','speed':0.8 if slow else 1.0})
                        r.raise_for_status();audio=r.content
                except httpx.HTTPError as exc: raise ProviderError('TTS服务调用失败') from exc
            else: raise ProviderError('TTS_BACKEND只能为edge或http')
            if not audio: raise ProviderError('TTS返回了空音频')
            pcm_parts.append(await asyncio.to_thread(self._decode_audio,audio))
            pcm_parts.append(b'\x00'*3200)
        return pcm_wav(b''.join(pcm_parts))

    @staticmethod
    def _decode_audio(audio:bytes) -> bytes:
        try:
            result=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i','pipe:0','-f','s16le','-ar','16000','-ac','1','pipe:1'],
                                  input=audio,capture_output=True,timeout=45,check=True)
            if not result.stdout: raise ProviderError('无法解码TTS音频')
            return result.stdout
        except (OSError,subprocess.SubprocessError) as exc: raise ProviderError('TTS音频解码失败，请检查ffmpeg') from exc
