#!/usr/bin/env python3
"""aibot course addon: local Chinese wake/control, English audio sent to own brain.

Only this process owns the microphone during course mode. It does not rewrite the
existing nox files. Stop nox-voice explicitly before enabling this service.
"""
from __future__ import annotations
import argparse
import io
import json
import logging
import os
import queue
import shlex
import signal
import subprocess
import threading
import time
import uuid
import wave
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from .audio import VoiceActivity,find_usb_mic,control_action,split_wake,amplify,WAKE_WORDS

LOG=logging.getLogger('english-edge')
TICK_SECONDS=5
READY_MESSAGE='小陈同学已就绪。说，小陈同学，学英语，开始上课；只说小陈同学，就是普通聊天。'


class Chat:
    """只说“小陈同学”时的普通聊天：中文文字交给原机器人的本机 bridge，由原机器人云端回答并用它自己的声音播放。
    不改原机器人文件；本进程仍独占麦克风，所以要按 bridge 的 tts_active 做回声屏蔽。"""
    def __init__(self,timeout=None,poll=None):
        self.url=os.environ.get('NOX_BRIDGE_URL','http://127.0.0.1:8888').rstrip('/')
        token=os.environ.get('NOX_API_TOKEN','')
        self.headers={'Authorization':'Bearer '+token} if token else {}
        self.timeout=float(os.environ.get('CHAT_TIMEOUT','120')) if timeout is None else timeout
        self.poll=poll or self.request
        self.until=0.;self.guard_until=0.;self.last_poll=0.;self.history=[]

    def request(self,method,path,body=None):
        with httpx.Client(timeout=httpx.Timeout(10,connect=3)) as c:
            r=c.request(method,self.url+path,headers=self.headers,json=body)
            if r.status_code>=400: raise RuntimeError(f'原机器人bridge返回{r.status_code}')
            return r.json()

    @property
    def active(self): return time.monotonic()<self.until

    def enter(self):
        """听到单独的“小陈同学”：进入/延长聊天，让原机器人应一声“我在”。"""
        self.until=time.monotonic()+self.timeout;self.guard_until=time.monotonic()+1.5
        try: self.poll('POST','/command',{'cmd':'speak_ack'})
        except Exception as exc: LOG.warning('原机器人没有应答：%s',exc);return False
        LOG.info('进入普通聊天');return True

    def say(self,text,had_wake):
        self.until=time.monotonic()+self.timeout
        body={'text':text,'had_wake_word':had_wake,'in_conversation':True,'recent_context':self.history[-3:]}
        try: ok=self.poll('POST','/voice/input',body).get('ok') is True
        except Exception as exc: LOG.warning('转交原机器人失败：%s',exc);ok=False
        if ok:
            self.history=(self.history+[text])[-5:];self.guard_until=time.monotonic()+2.0
            LOG.info('转交原机器人：%s',text)
        return ok

    def leave(self):
        if self.active: LOG.info('退出普通聊天')
        self.until=0.;self.history=[]

    def guarded(self,now):
        """原机器人正在说话（或刚发出去等它开口）时不收麦克风声音。每 0.25 秒问一次 bridge。"""
        if now-self.last_poll>=0.25:
            self.last_poll=now
            try:
                if self.poll('GET','/voice/tts_active').get('tts_active'): self.guard_until=max(self.guard_until,now+0.8)
            except Exception: pass
        return now<self.guard_until


def load_env(path:Path):
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        k,v=line.split('=',1);v=v.strip()
        if v[:1] in ('"',"'"): v=shlex.split(v)[0]
        os.environ[k.strip()]=v

class Edge:
    def __init__(self,play_audio=True,start_worker=True):
        self.url=os.environ.get('BRAIN_URL','').rstrip('/');self.token=os.environ.get('EDGE_TOKEN','')
        if not self.url or len(self.token)<16: raise ValueError('请填写BRAIN_URL和本人的EDGE_TOKEN')
        p=urlsplit(self.url)
        if p.scheme not in ('http','https') or not p.hostname: raise ValueError('脑端地址必须是HTTP(S) URL')
        if p.scheme=='http' and os.environ.get('ALLOW_INSECURE_HTTP','0')!='1':
            raise ValueError('默认只允许HTTPS；仅可信局域网/Tailscale测试可由老师设置ALLOW_INSECURE_HTTP=1')
        self.headers={'Authorization':'Bearer '+self.token}
        self.audio_enabled=play_audio;self.active=False;self.busy=False;self.playing=False
        self.phase='idle';self.player=None;self.generation=0;self.last_activity=time.monotonic()
        # spoken：机器人每出一道新题（回答/控制后的回复）加1；录音时记下，处理时若已换题则作废。
        self.spoken=0;self.question_key=None
        self.queue=queue.Queue(maxsize=4);self.stop_event=threading.Event();self.last_result=None
        self.thread=threading.Thread(target=self.worker,name='english-network',daemon=True)
        if start_worker: self.thread.start()

    def request(self,path,*,body=None,content=None,params=None,raw=False):
        headers=dict(self.headers)
        if content is not None: headers['Content-Type']='audio/wav'
        with httpx.Client(timeout=httpx.Timeout(110,connect=10)) as c:
            r=c.post(self.url+path,headers=headers,json=body,content=content,params=params)
            if r.status_code>=400:
                try: detail=r.json().get('detail','请求失败')
                except ValueError: detail='请求失败'
                raise RuntimeError(f'脑端返回{r.status_code}：{detail}')
            return r.content if raw else r.json()

    def submit(self,action='answer',text='',wav=None):
        if action in ('stop','pause'):
            self.generation+=1;self.stop_audio()
            while True:
                try: self.queue.get_nowait();self.queue.task_done()
                except queue.Empty: break
        # 忙时不再丢弃孩子的回答：排队等上一轮完成后处理。
        item={'generation':self.generation,'action':action,'text':text,'wav':wav,'request_id':uuid.uuid4().hex,'spoken':self.spoken}
        try: self.queue.put_nowait(item);return True
        except queue.Full:
            LOG.warning('待处理的语音太多，这一句没有发送');return False

    def submit_tick(self):
        """只在完全空闲时轮询：不忙、不在播放、队列里没有待处理的回答。"""
        if not self.active or self.busy or self.playing or not self.queue.empty(): return False
        return self.submit('tick')

    def stop_audio(self):
        player=self.player
        if player and player.poll() is None:
            try: player.terminate()
            except OSError: pass
        self.playing=False

    def local_message(self,text):
        LOG.info(text)
        if not self.audio_enabled: return
        self.playing=True
        try:
            self.player=subprocess.Popen(['espeak-ng','-v',os.environ.get('LOCAL_VOICE','cmn'),'-s','155',text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.player.wait(timeout=12)
        except (OSError,subprocess.SubprocessError): pass
        finally: self.playing=False;self.player=None

    def play(self,wav):
        if not self.audio_enabled: return
        self.playing=True
        try:
            self.player=subprocess.Popen(['aplay','-q','-D',os.environ.get('PLAYBACK_DEVICE','default')],stdin=subprocess.PIPE)
            self.player.communicate(wav,timeout=120)
            if self.player.returncode and self.player.returncode>0:
                raise RuntimeError('音频播放失败，请检查PLAYBACK_DEVICE和USB耳麦')
        except (OSError,subprocess.SubprocessError):
            self.stop_audio()
            raise RuntimeError('音频播放失败，请检查PLAYBACK_DEVICE和USB耳麦')
        finally: self.playing=False;self.player=None;self.last_activity=time.monotonic()

    def worker(self):
        while not self.stop_event.is_set():
            try: item=self.queue.get(timeout=0.3)
            except queue.Empty: continue
            try: self.process(item)
            finally: self.queue.task_done()

    def process(self,item):
        if item['action']=='answer' and item.get('spoken',self.spoken)!=self.spoken:
            # 这句是在上一题时录的，机器人已经换了新题；不拿它判新题。
            LOG.info('丢弃换题前录下的一句回答');return
        self.busy=True;received=False
        try:
            if item['wav'] is not None:
                result=self.request('/voice/audio',content=item['wav'],params={'request_id':item['request_id']})
            else:
                result=self.request('/voice/turn',body={k:item[k] for k in ('action','text','request_id')})
            received=True
            self.active=result['active'];self.phase=result['phase'];self.last_result=result
            segments=result.get('segments',[])
            if item['action'] not in ('tick','played'): self.note_question(result)
            if item['generation']!=self.generation: return
            if segments:
                LOG.info('机器人：%s',' '.join(s['text'] for s in segments))
                if self.audio_enabled:
                    audio=self.request('/voice/speech',body={'segments':segments,'slow':result.get('slow',False)},raw=True)
                    if item['generation']==self.generation: self.play(audio)
                if self.active: self.report_played()
        except Exception as exc:
            LOG.error('%s',exc)
            if item['generation']==self.generation:
                self.local_message('播报暂时没有完成。请说，再说一次，听当前题目。' if received else '连接暂时有问题。请检查服务后再继续。')
        finally:
            self.busy=False;self.last_activity=time.monotonic()

    def note_question(self,result):
        """题目位置变了（开始/换词/换阶段/对话下一轮）才算换题；“没听清再说一次”不算。
        对话阶段的轮次用脑端返回的 dialog_count 区分，不能用“有没有播报内容”判断——没听清的重问也有播报。"""
        key=(result.get('session_id'),result.get('phase'),result.get('word_index'),result.get('dialog_count'))
        if key!=self.question_key: self.spoken+=1
        self.question_key=key

    def report_played(self):
        """告诉脑端“刚播完”，20秒重问从播完开始算；失败只记日志，不打断上课。"""
        try: self.request('/voice/turn',body={'action':'played','text':'','request_id':uuid.uuid4().hex})
        except Exception as exc: LOG.warning('播完通知失败：%s',exc)

    def close(self):
        self.stop_event.set();self.stop_audio()


def recognize_chinese(model,wav):
    """本机中文识别，返回 (文字, 平均置信度)。"""
    import vosk
    with wave.open(io.BytesIO(wav),'rb') as w: pcm=w.readframes(w.getnframes())
    rec=vosk.KaldiRecognizer(model,16000);rec.SetWords(True)
    rec.AcceptWaveform(pcm);result=json.loads(rec.FinalResult())
    words=result.get('result',[])
    confidence=sum(w.get('conf',0) for w in words)/len(words) if words else 0
    return result.get('text',''),confidence


def recognize_control(model,wav):
    text,confidence=recognize_chinese(model,wav)
    # Control recognition is not constrained to one expected answer.
    return control_action(text) if confidence>=0.70 else None


def heard_wake(partial:str) -> bool:
    return any(w in partial.replace(' ','') for w in WAKE_WORDS)


def route(edge,chat,text,confidence,wav):
    """一段语音的去向。上课优先：课中“小陈同学”只打断播报，不切去聊天。
    空闲时“小陈同学，学英语”上课，“小陈同学”聊天；聊天中的后续句子转交原机器人，再说“小陈同学，学英语”可直接切到上课。"""
    # 进入类指令（上课/聊天）阈值放宽到 0.60：唤醒词必须说对，但 Vosk 对
    # 真人说话的平均置信度经常在 0.6-0.7 之间，0.70 会把正确的唤醒也丢掉。
    # 课中控制指令（停止/暂停等）保持 0.70，避免误触发。
    action=control_action(text)
    if action in ('start','chat'):
        if confidence<0.60: action=None
    elif confidence<0.70:
        action=None
    had_wake,rest=split_wake(text)
    if action=='start':
        chat.leave()
        if not edge.active: edge.submit('start')
        return 'start'
    if edge.active:
        if action=='chat': edge.generation+=1;edge.stop_audio();return 'interrupt'
        if action: edge.submit(action);return action
        if edge.phase!='paused': edge.submit(wav=wav);return 'answer'
        return None
    if action=='chat': chat.enter();return 'chat'
    if chat.active and (had_wake or confidence>=0.5) and len(rest)>=2:
        chat.say(rest,had_wake);return 'say'
    # Idle environmental speech is never sent anywhere.
    return None


def voice_loop(edge,chat=None):
    chat=chat or Chat()
    import vosk
    model_path=Path(os.environ.get('VOSK_ZH_PATH','models/vosk-model-small-cn-0.22'))
    if not model_path.is_dir(): raise RuntimeError('中文唤醒模型不存在：先安装模型或指向原aibot中文模型目录')
    vosk.SetLogLevel(-1);model=vosk.Model(str(model_path))
    wake=vosk.KaldiRecognizer(model,16000)
    capture=os.environ.get('CAPTURE_DEVICE','auto')
    if capture=='auto': capture=find_usb_mic()
    gain=float(os.environ.get('MIC_GAIN','1'));threshold=float(os.environ.get('VAD_THRESHOLD','450'))
    if not 0.25<=gain<=8 or not 50<=threshold<=10000: raise ValueError('MIC_GAIN应在0.25—8，VAD_THRESHOLD应在50—10000')
    vad=VoiceActivity(threshold=threshold)
    proc=subprocess.Popen(['arecord','-q','-D',capture,'-t','raw','-f','S16_LE','-r','16000','-c','1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    edge.local_message(READY_MESSAGE)
    guard_until=time.monotonic()+0.4;was_playing=False;last_tick=time.monotonic()
    try:
        while not edge.stop_event.is_set():
            chunk=proc.stdout.read(3200)
            if not chunk: raise RuntimeError('麦克风采集停止，systemd将重启服务')
            chunk=amplify(chunk,gain)
            now=time.monotonic()
            if edge.playing:
                was_playing=True;vad.reset()
                if wake.AcceptWaveform(chunk):
                    heard=json.loads(wake.Result()).get('text','');action=control_action(heard)
                    if action in ('stop','pause'): edge.submit(action)
                else:
                    partial=json.loads(wake.PartialResult()).get('partial','')
                    if heard_wake(partial):
                        edge.generation+=1;edge.stop_audio();guard_until=now+0.4
                        wake=vosk.KaldiRecognizer(model,16000)
                continue
            if was_playing:
                was_playing=False;guard_until=now+0.35;vad.reset();wake=vosk.KaldiRecognizer(model,16000)
            # Chinese stop/pause remains usable while waiting for a network response.
            if now<guard_until or (not edge.active and chat.active and chat.guarded(now)):
                vad.reset();continue
            wav=vad.feed(chunk)
            if wav:
                text,confidence=recognize_chinese(model,wav)
                LOG.info('听到 %r conf=%.2f',text,confidence)
                route(edge,chat,text,confidence,wav)
            # 5 秒轮询一次，脑端据此判断 20 秒重问、3 分钟自动暂停（服务器决定，这里不计时）。
            if now-last_tick>TICK_SECONDS and edge.submit_tick(): last_tick=now
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env',type=Path,default=Path('/etc/english-class/pi.env'))
    p.add_argument('--text',action='store_true',help='键盘输入调试，无需Vosk或麦克风')
    p.add_argument('--no-audio',action='store_true',help='文字调试不播声音')
    a=p.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)  # 5 秒一次轮询，避免日志刷屏；机器人话术仍会记录
    if a.env.is_file(): load_env(a.env)
    edge=Edge(play_audio=not a.no_audio)
    signal.signal(signal.SIGTERM,lambda *_:edge.close())
    try:
        if a.text:
            print('输入 /start 开始，/stop 结束，/quit 退出；其他文字为回答。')
            while not edge.stop_event.is_set():
                try: text=input('你：').strip()
                except EOFError: break
                if text=='/quit': break
                action={'/start':'start','/stop':'stop','/pause':'pause','/resume':'resume','/repeat':'repeat','/help':'help'}.get(text,'answer')
                edge.submit(action,text if action=='answer' else '');edge.queue.join()
        else: voice_loop(edge)
    except KeyboardInterrupt: pass
    finally: edge.close()

if __name__=='__main__': main()
