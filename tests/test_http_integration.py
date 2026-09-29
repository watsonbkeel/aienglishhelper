"""Real loopback HTTP across brain/public/test-provider + SQLite + ffmpeg.
The provider below is explicitly a test fixture: no real child/LLM/ASR is measured.
"""
import contextlib
import json
import socket
import threading
import time
import uuid
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response
from english_class.brain_api import create_brain
from english_class.public_api import create_app
from english_class.providers import Providers, pcm_wav, validate_wav
from english_class.client import PublicClient

@contextlib.contextmanager
def running(app):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off',ws='none'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not server.started:
        if time.monotonic()>deadline: raise RuntimeError('test HTTP server failed to start')
        time.sleep(.01)
    try: yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()
        assert not thread.is_alive()

def test_real_http_lesson_config_audio_speech_and_progress(db):
    upstream=FastAPI();seen=[];audio_state={'text':'苹果'}
    @upstream.post('/chat/completions')
    async def chat(request:Request):
        body=await request.json();seen.append(body)
        task=body['messages'][0]['content'];data=json.loads(body['messages'][-1]['content'])
        if 'VOCABULARY_JUDGE' in task:
            answer={'correct':data['answer'] in (data['word'],data['meaning'])}
        elif 'ENGLISH_CUE' in task: answer={'cue':'What fruit is often red?'}
        else: answer={'reply':[{'text':'Welcome to our shop. What would you like?', 'language':'en'}],'relevant':True}
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer)}}]}
    @upstream.post('/audio/transcriptions')
    async def asr(): return {'text':audio_state['text']}
    @upstream.post('/audio/speech')
    async def tts(): return Response(pcm_wav(b'\0'*6400),media_type='audio/wav')
    db.add_student('s001','Parent_A_very_long_token','Brain_A_very_long_token')
    with running(upstream) as provider_url:
        p=Providers(llm_base=provider_url,llm_key='test-only',asr_backend='http',asr_base=provider_url,asr_key='test-only',asr_model='test-fixture',tts_backend='http',tts_base=provider_url,tts_key='test-only',tts_model='test-fixture')
        with running(create_app(db,p)) as public_url:
            io=PublicClient(public_url,'s001','Brain_A_very_long_token')
            with running(create_brain(io,'edge-test-1234567890')) as brain_url, httpx.Client(timeout=15) as c:
                edge={'Authorization':'Bearer edge-test-1234567890'};parent={'Authorization':'Bearer Parent_A_very_long_token'}
                def turn(text='',action='answer'):
                    r=c.post(brain_url+'/voice/turn',headers=edge,json={'request_id':uuid.uuid4().hex,'text':text,'action':action})
                    assert r.status_code==200,r.text
                    return r.json()
                start=turn(action='start');assert start['phase']=='listen'
                speech=c.post(brain_url+'/voice/speech',headers=edge,json={'segments':start['segments']})
                assert speech.status_code==200 and len(validate_wav(speech.content)[0])>0
                wav=pcm_wav(b'\0'*6400);key=uuid.uuid4().hex
                r=c.post(brain_url+'/voice/audio',headers=edge,params={'request_id':key},content=wav)
                assert r.status_code==200 and r.json()['word_index']==1,r.text
                repeat=c.post(brain_url+'/voice/audio',headers=edge,params={'request_id':key},content=wav)
                assert repeat.json()==r.json()
                for answer in ['香蕉','书包','apple','banana','bag']: result=turn(answer)
                assert result['phase']=='dialog'
                report=c.get(public_url+'/api/progress',headers=parent,params={'student_id':'s001'}).json()
                assert len(report['words'])==3 and all(x['status']==2 for x in report['words'])
                assert all(x['last_practiced_date']==report['today'] for x in report['words'])
                config=c.get(public_url+'/api/config',headers=parent,params={'student_id':'s001'}).json()
                config.update(semester=2,unit=0,difficulty='challenge')
                assert c.put(public_url+'/api/config',headers=parent,params={'student_id':'s001'},json=config).status_code==200
                start2=turn(action='start')
                assert any('cat' in x['text'] for x in start2['segments'])
    assert seen and all(x['thinking']=={'type':'disabled'} for x in seen)
