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
from .audio import VoiceActivity,find_usb_mic,control_action,amplify

LOG=logging.getLogger('english-edge')
TICK_SECONDS=5


def load_env(path:Path):
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        k,v=line.split('=',1);v=v.strip()
        if v[:1] in ('"',"'"): v=shlex.split(v)[0]
        os.environ[k.strip()]=v

class Edge:
    def __init__(self,play_audio=True):
        self.url=os.environ.get('BRAIN_URL','').rstrip('/');self.token=os.environ.get('EDGE_TOKEN','')
        if not self.url or len(self.token)<16: raise ValueError('请填写BRAIN_URL和本人的EDGE_TOKEN')
        p=urlsplit(self.url)
        if p.scheme not in ('http','https') or not p.hostname: raise ValueError('脑端地址必须是HTTP(S) URL')
        if p.scheme=='http' and os.environ.get('ALLOW_INSECURE_HTTP','0')!='1':
            raise ValueError('默认只允许HTTPS；仅可信局域网/Tailscale测试可由老师设置ALLOW_INSECURE_HTTP=1')
        self.headers={'Authorization':'Bearer '+self.token}
        self.audio_enabled=play_audio;self.active=False;self.busy=False;self.playing=False
        self.phase='idle';self.player=None;self.generation=0;self.last_activity=time.monotonic()
        self.queue=queue.Queue(maxsize=4);self.stop_event=threading.Event();self.last_result=None
        self.thread=threading.Thread(target=self.worker,name='english-network',daemon=True)
        self.thread.start()

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
        if self.busy and action not in ('stop','pause'): return False
        item={'generation':self.generation,'action':action,'text':text,'wav':wav,'request_id':uuid.uuid4().hex}
        try: self.queue.put_nowait(item);return True
        except queue.Full: return False

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
            self.busy=True;received=False
            try:
                if item['wav'] is not None:
                    result=self.request('/voice/audio',content=item['wav'],params={'request_id':item['request_id']})
                else:
                    result=self.request('/voice/turn',body={k:item[k] for k in ('action','text','request_id')})
                received=True
                self.active=result['active'];self.phase=result['phase'];self.last_result=result
                segments=result.get('segments',[])
                if item['generation']!=self.generation: continue
                if segments:
                    LOG.info('机器人：%s',' '.join(s['text'] for s in segments))
                    if self.audio_enabled:
                        audio=self.request('/voice/speech',body={'segments':segments,'slow':result.get('slow',False)},raw=True)
                        if item['generation']==self.generation: self.play(audio)
            except Exception as exc:
                LOG.error('%s',exc)
                if item['generation']==self.generation:
                    self.local_message('播报暂时没有完成。请说，再说一次，听当前题目。' if received else '连接暂时有问题。请检查服务后再继续。')
            finally:
                self.busy=False;self.last_activity=time.monotonic();self.queue.task_done()

    def close(self):
        self.stop_event.set();self.stop_audio()


def recognize_control(model,wav):
    import vosk
    with wave.open(io.BytesIO(wav),'rb') as w: pcm=w.readframes(w.getnframes())
    rec=vosk.KaldiRecognizer(model,16000);rec.SetWords(True)
    rec.AcceptWaveform(pcm);result=json.loads(rec.FinalResult())
    words=result.get('result',[])
    confidence=sum(w.get('conf',0) for w in words)/len(words) if words else 0
    text=result.get('text','')
    # Control recognition is not constrained to one expected answer.
    return control_action(text) if confidence>=0.70 else None


def voice_loop(edge):
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
    edge.local_message('英语练习已就绪。请说，小爱同学，开始英语练习。')
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
                    partial=json.loads(wake.PartialResult()).get('partial','').replace(' ','')
                    if '小爱同学' in partial or '小艾同学' in partial:
                        edge.generation+=1;edge.stop_audio();guard_until=now+0.4
                        wake=vosk.KaldiRecognizer(model,16000)
                continue
            if was_playing:
                was_playing=False;guard_until=now+0.35;vad.reset();wake=vosk.KaldiRecognizer(model,16000)
            # Chinese stop/pause remains usable while waiting for a network response.
            if now<guard_until:
                vad.reset();continue
            wav=vad.feed(chunk)
            if wav:
                action=recognize_control(model,wav)
                if action=='wake':
                    if not edge.active: edge.submit('start')
                    else: edge.generation+=1;edge.stop_audio()
                elif action: edge.submit(action)
                elif edge.active and edge.phase!='paused' and not edge.busy: edge.submit(wav=wav)
                # Idle environmental speech is never sent to the server.
            # 5 秒轮询一次，脑端据此判断 20 秒重问、3 分钟自动暂停（服务器决定，这里不计时）。
            if edge.active and not edge.busy and not edge.playing and now-last_tick>TICK_SECONDS:
                edge.submit('tick');last_tick=now
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
