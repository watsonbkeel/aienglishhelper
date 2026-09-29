"""Small audio helpers for the aibot English-course voice addon (16k PCM)."""
from __future__ import annotations
import array
import io
import math
import re
import subprocess
import wave
from collections import deque


def control_action(text:str):
    s=re.sub(r'[\s，。！？,.!?]','',text.lower())
    if s in ('小爱同学','小艾同学','小愛同學'): return 'wake'
    for w in ('小爱同学','小艾同学','小愛同學'):
        if s.startswith(w): s=s[len(w):]
    return {'开始英语练习':'start','开始今天的英语练习':'start','开始练习':'start','结束':'stop','结束练习':'stop',
            '停止练习':'stop','暂停':'pause','暂停练习':'pause','继续':'resume','继续练习':'resume','再说一次':'repeat',
            '再读一次':'repeat','慢一点':'slow','说慢一点':'slow','我不会':'help','给我提示':'help','用中文解释':'help'}.get(s)


def wav_bytes(pcm:bytes):
    f=io.BytesIO()
    with wave.open(f,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm)
    return f.getvalue()


def amplify(pcm:bytes,gain:float) -> bytes:
    if gain==1: return pcm
    a=array.array('h');a.frombytes(pcm)
    return array.array('h',(max(-32768,min(32767,int(v*gain))) for v in a)).tobytes()

class VoiceActivity:
    def __init__(self,threshold=450,silence_chunks=10,max_chunks=180):
        self.threshold=threshold;self.silence_chunks=silence_chunks;self.max_chunks=max_chunks
        self.reset()
    def reset(self):
        self.parts=[];self.before=deque(maxlen=3);self.silence=0
    def feed(self,chunk:bytes):
        a=array.array('h');a.frombytes(chunk[:len(chunk)//2*2])
        rms=math.sqrt(sum(v*v for v in a)/max(1,len(a)))
        voice=rms>=self.threshold
        if not self.parts:
            if not voice: self.before.append(chunk);return None
            self.parts=list(self.before);self.before.clear()
        self.parts.append(chunk)
        self.silence=0 if voice else self.silence+1
        if self.silence>=self.silence_chunks or len(self.parts)>=self.max_chunks:
            pcm=b''.join(self.parts);self.reset();return wav_bytes(pcm)
        return None


def find_usb_mic() -> str:
    """Stable ALSA CARD names, following the existing aibot USB-audio convention."""
    result=subprocess.run(['arecord','-l'],capture_output=True,text=True,timeout=10)
    for line in result.stdout.splitlines():
        if 'USB' not in line and 'usb' not in line: continue
        match=re.search(r'card\s+\d+:\s*([^\s]+).*device\s+(\d+):',line)
        if match: return f'plughw:CARD={match.group(1)},DEV={match.group(2)}'
    raise RuntimeError('未找到USB麦克风；运行arecord -l，或设置CAPTURE_DEVICE')
