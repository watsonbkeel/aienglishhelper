"""Teacher-owned providers. No silent demo responses on real-service errors."""
from __future__ import annotations
import array
import asyncio
import io
import ipaddress
import json
import math
import os
import socket
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
import httpx

class ProviderError(RuntimeError):
    pass


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


def has_speech(pcm:bytes,min_rms:float,rate:int=16000) -> bool:
    """粗判是否有人说话：按30毫秒分帧，响的帧要够响，且明显高于底噪（静音、持续白噪声都不算）。"""
    a=array.array('h');a.frombytes(pcm[:len(pcm)//2*2])
    size=rate*30//1000
    levels=sorted(math.sqrt(sum(v*v for v in a[i:i+size])/size) for i in range(0,len(a)-size+1,size))
    if not levels: return False
    loud=levels[int(len(levels)*0.9)] if len(levels)>=10 else levels[-1]
    floor=levels[int(len(levels)*0.1)]
    return loud>=min_rms and loud>=2*max(floor,1.0)


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
    asr_min_rms:float=200.0          # 仅 http 模式：低于此音量或没有起伏的录音按“没听清”处理；0 关闭
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
        pcm,rate=validate_wav(data)
        if self.asr_backend=='vosk':
            return await asyncio.to_thread(self._vosk,pcm,rate,language)
        if self.asr_backend!='http': raise ProviderError('ASR_BACKEND只能为vosk或http')
        if not (self.asr_base and self.asr_model): raise ProviderError('老师尚未配置兼容ASR服务')
        # 云端模型对静音/持续噪声会编出 "Okay." 之类的句子；这类录音直接按“没听清”处理，不送识别、不降级。
        if self.asr_min_rms>0 and not has_speech(pcm,self.asr_min_rms):
            return {'text':'','confidence':None,'unclear':True,'provider':'gate'}
        if self.asr_fallback=='vosk' and time.monotonic()<self._asr_down_until:
            return await self._asr_fallback(pcm,rate,language)
        try: return await self._http_asr(data,language)
        except ProviderError:
            if self.asr_fallback!='vosk': raise
            self._asr_down_until=time.monotonic()+self.asr_retry_after
            return await self._asr_fallback(pcm,rate,language)

    async def _asr_fallback(self,pcm:bytes,rate:int,language:str) -> dict:
        result=await asyncio.to_thread(self._vosk,pcm,rate,language)
        return {**result,'provider':'vosk-fallback'}

    def _asr_language(self,language:str) -> str:
        names=dict(x.split(':',1) for x in self.asr_language_map.split(',') if ':' in x)
        return names.get(language,language).strip()

    async def _http_asr(self,data:bytes,language:str) -> dict:
        headers={'Authorization':'Bearer '+self.asr_key} if self.asr_key else {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.asr_timeout,connect=min(3.0,self.asr_timeout)),trust_env=False) as c:
                r=await c.post(self.asr_base.rstrip('/')+'/audio/transcriptions',headers=headers,
                               files={'file':('speech.wav',data,'audio/wav')},
                               data={'model':self.asr_model,'language':self._asr_language(language),'response_format':'json'})
                r.raise_for_status();obj=r.json();text=obj.get('text','').strip()
                # No confidence value is invented when the provider does not return one.
                return {'text':text,'confidence':None,'unclear':not bool(text),'provider':'http'}
        except (httpx.HTTPError,ValueError,AttributeError) as exc:
            raise ProviderError('语音识别服务调用失败；本轮不计为答错') from exc

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
