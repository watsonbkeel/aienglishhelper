"""One student, one process, one port. No shared global class conversation."""
from __future__ import annotations
import asyncio
import copy
import hashlib
import hmac
import json
import logging
import os
from collections import OrderedDict
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Depends, Query, Request
from fastapi.responses import Response
from .client import PublicClient, ServiceError
from .engine import Tutor
from .models import TurnInput, SpeechInput

LOG=logging.getLogger('english-class.brain')


def create_brain(io,edge_token:str,student_prompt:str='',practice_size:int=3,state_path=None):
    if len(edge_token)<16: raise ValueError('EDGE_TOKEN须为至少16位随机凭证')
    app=FastAPI(title='Student English brain',version='0.1.0',docs_url=None,redoc_url=None)
    tutor=Tutor(io,student_prompt=student_prompt,practice_size=practice_size,state_path=state_path)
    app.state.tutor=tutor
    lock=asyncio.Lock();cache=OrderedDict();audio_cache=OrderedDict()

    def auth(authorization:str|None=Header(default=None)):
        expected='Bearer '+edge_token
        if authorization is None or not hmac.compare_digest(authorization,expected):
            raise HTTPException(401,'树莓派脑端凭证无效')

    @app.get('/health')
    def health(): return {'ok':True,'service':'student-brain','version':'0.1.0'}

    async def run_turn_locked(body:TurnInput,fingerprint:str|None=None):
        fingerprint=fingerprint or hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        key=body.request_id
        if key in cache:
            old_fp,reply=cache[key]
            if old_fp!=fingerprint: raise HTTPException(409,'相同请求编号不能用于不同内容')
            return reply
        # Roll back transient state on upstream failure; completed progress writes use stable idempotency keys.
        state={k:copy.deepcopy(v) for k,v in tutor.__dict__.items() if k not in ('io','clock')}
        try:
            reply=await tutor.turn(body.text,action=body.action,request_id=key,confidence=body.confidence,unclear=body.unclear)
        except (ServiceError,ValueError) as exc:
            for k in list(tutor.__dict__):
                if k not in ('io','clock'): del tutor.__dict__[k]
            tutor.__dict__.update(state)
            raise HTTPException(503,str(exc)) from exc
        reply['request_id']=key
        cache[key]=(fingerprint,reply)
        while len(cache)>256: cache.popitem(last=False)
        return reply

    async def run_turn(body:TurnInput,fingerprint:str|None=None):
        async with lock:
            return await run_turn_locked(body,fingerprint)

    @app.post('/voice/turn',dependencies=[Depends(auth)])
    async def turn(body:TurnInput): return await run_turn(body)

    @app.post('/voice/audio',dependencies=[Depends(auth)])
    async def audio(request:Request,request_id:str=Query(min_length=8,max_length=80)):
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>1_000_000: raise HTTPException(413,'每轮录音不得超过30秒')
            chunks.append(chunk)
        wav=b''.join(chunks);fingerprint='audio:'+hashlib.sha256(wav).hexdigest()
        async with lock:
            if request_id in audio_cache:
                prior_fp,asr=audio_cache[request_id]
                if prior_fp!=fingerprint: raise HTTPException(409,'录音请求编号重复但内容不同')
            else:
                try: asr=await io.transcribe(wav,tutor.last_expected)
                except (ServiceError,ValueError) as exc:
                    LOG.warning('asr failed class_request=%s error=%s',request_id,exc)
                    raise HTTPException(503,str(exc)) from exc
                # 课堂请求编号与识别服务请求编号对上，便于事后排查；不记录音频和识别文本。
                LOG.info('asr class_request=%s provider=%s fallback_reason=%s asr_request=%s unclear=%d',request_id,
                         asr.get('provider','-'),asr.get('fallback_reason') or '-',asr.get('request_id') or '-',int(bool(asr.get('unclear'))))
                audio_cache[request_id]=(fingerprint,asr)
                while len(audio_cache)>128: audio_cache.popitem(last=False)
            body=TurnInput(text=asr['text'],confidence=asr.get('confidence'),unclear=asr.get('unclear',False),request_id=request_id)
            reply=await run_turn_locked(body,fingerprint)
            return {**reply,'recognized_text':asr['text'],'asr_provider':asr.get('provider')}

    @app.post('/voice/speech',dependencies=[Depends(auth)])
    async def speech(body:SpeechInput):
        try: data=await io.speak([x.model_dump() for x in body.segments],body.slow)
        except (ServiceError,ValueError) as exc: raise HTTPException(503,str(exc)) from exc
        return Response(data,media_type='audio/wav',headers={'Cache-Control':'no-store'})

    @app.post('/voice/push',dependencies=[Depends(auth)])
    async def legacy_push(request:Request):
        """Text bridge adapter. Optional trusted-LAN callback uses original /speak API."""
        payload=await request.json()
        if not isinstance(payload,dict) or not isinstance(payload.get('text'),str): raise HTTPException(422,'text is required')
        encoded=json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()
        body=TurnInput(text=payload['text'],request_id='legacy-'+hashlib.sha256(encoded).hexdigest()[:32])
        reply=await run_turn(body)
        callback=os.environ.get('AIBOT_BODY_URL','').rstrip('/')
        if callback and reply['segments']:
            import httpx
            headers={}
            if os.environ.get('NOX_API_TOKEN'): headers['Authorization']='Bearer '+os.environ['NOX_API_TOKEN']
            try:
                async with httpx.AsyncClient(timeout=45) as c:
                    r=await c.post(callback+'/speak',headers=headers,json={'text':' '.join(x['text'] for x in reply['segments'])})
                    r.raise_for_status()
            except httpx.HTTPError as exc: raise HTTPException(503,'原aibot播报回调失败；使用课程语音插件可避免反向回调') from exc
        return reply
    return app


def from_env():
    required=('STUDENT_ID','BRAIN_TOKEN','EDGE_TOKEN')
    for key in required:
        if not os.environ.get(key): raise ValueError(f'未配置{key}')
    from . import DEFAULT_PUBLIC_PORT
    io=PublicClient(os.environ.get('PUBLIC_URL',f'http://127.0.0.1:{DEFAULT_PUBLIC_PORT}'),os.environ['STUDENT_ID'],os.environ['BRAIN_TOKEN'])
    prompt_path=Path(os.environ.get('STUDENT_PROMPT_PATH','prompts/student.md'))
    prompt=prompt_path.read_text(encoding='utf-8') if prompt_path.is_file() else ''
    # 断点文件：默认放在 systemd StateDirectory（/var/lib/english-class-brain/<sid>/），未设置则不保存断点。
    state=os.environ.get('RESUME_STATE_PATH') or (os.path.join(os.environ['STATE_DIRECTORY'],'resume.json') if os.environ.get('STATE_DIRECTORY') else None)
    return create_brain(io,os.environ['EDGE_TOKEN'],prompt,int(os.environ.get('PRACTICE_WORDS','3')),state_path=state)
