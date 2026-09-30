"""Wire-format tests with substituted external HTTP, not a real provider trial."""
import json
import pytest
import httpx
from english_class.providers import Providers, ProviderError, pcm_wav

@pytest.fixture
def external_http(monkeypatch):
    real_client=httpx.AsyncClient
    seen=[]
    response={'status':200,'json':{'choices':[{'finish_reason':'stop','message':{'content':'{"correct":true}'}}]}}
    def handle(request):
        seen.append(request)
        return httpx.Response(response['status'],json=response['json'])
    monkeypatch.setattr('english_class.providers.httpx.AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handle),**kw))
    return seen,response

@pytest.mark.asyncio
async def test_provider_sends_disabled_thinking_and_json_mode(external_http):
    seen,response=external_http
    p=Providers(llm_key='test-only-not-a-real-secret')
    assert await p.chat([{'role':'system','content':'Return JSON.'}],True)=='{"correct":true}'
    payload=json.loads(seen[0].content)
    assert payload['thinking']=={'type':'disabled'}
    assert payload['model']=='deepseek-flash'
    assert payload['response_format']=={'type':'json_object'}
    assert 'reasoning_effort' not in payload

@pytest.mark.asyncio
@pytest.mark.parametrize('finish', ['length','content_filter'])
async def test_incomplete_model_response_is_not_a_success(external_http,finish):
    seen,response=external_http
    response['json']['choices'][0]['finish_reason']=finish
    with pytest.raises(ProviderError): await Providers(llm_key='test-only').chat([])

@pytest.mark.asyncio
async def test_upstream_failure_not_demo_fallback(external_http):
    seen,response=external_http;response['status']=500
    with pytest.raises(ProviderError): await Providers(llm_key='test-only').chat([])

@pytest.mark.asyncio
async def test_no_key_fails_before_sending(external_http):
    seen,_=external_http
    with pytest.raises(ProviderError): await Providers().chat([])
    assert seen==[]

def speech_like(seconds=1.0,amp=6000):
    """有起伏的“说话”：0.3秒有声、0.2秒无声交替，前后留静音，模拟树莓派切好的一段录音。"""
    import math,array
    a=array.array('h')
    n=int(16000*seconds)
    for i in range(n):
        on=(i//1600)%5<3 and 1600<i<n-1600
        a.append(int(amp*math.sin(i*2*math.pi*220/16000)) if on else 0)
    return pcm_wav(a.tobytes())

def steady_noise(seconds=3.0,amp=800):
    import random,array
    rnd=random.Random(1)
    return pcm_wav(array.array('h',(rnd.randint(-amp,amp) for _ in range(int(16000*seconds)))).tobytes())

@pytest.mark.asyncio
async def test_asr_has_no_invented_confidence(external_http):
    seen,response=external_http;response['json']={'text':'apple'}
    p=Providers(asr_backend='http',asr_base='https://asr.example/v1',asr_key='test-only',asr_model='configured-model')
    result=await p.transcribe(speech_like(),'en')
    assert result=={'text':'apple','confidence':None,'unclear':False,'provider':'http'}
    assert str(seen[0].url)=='https://asr.example/v1/audio/transcriptions'
    assert b'name="language"' in seen[0].content and b'\r\nen\r\n' in seen[0].content
    assert seen[0].headers['authorization']=='Bearer test-only'
    response['json']={'text':''}
    assert (await p.transcribe(speech_like(),'en'))['unclear'] is True

@pytest.mark.asyncio
async def test_asr_language_names_and_optional_key(external_http):
    seen,response=external_http;response['json']={'text':'我不知道。'}
    p=Providers(asr_backend='http',asr_base='http://asr.test:3102/v1',asr_model='Qwen/Qwen3-ASR-1.7B',asr_language_map='en:English,zh:Chinese')
    assert (await p.transcribe(speech_like(),'zh'))['text']=='我不知道。'
    assert b'\r\nChinese\r\n' in seen[0].content and 'authorization' not in seen[0].headers
    await p.transcribe(speech_like(),'en')
    assert b'\r\nEnglish\r\n' in seen[1].content

@pytest.mark.asyncio
@pytest.mark.parametrize('audio',[pcm_wav(b'\0'*48000),steady_noise()],ids=['silence','steady-noise'])
async def test_asr_does_not_send_silence_or_noise_to_cloud(external_http,audio):
    # 云端模型对静音/噪声会编出 "Okay." "I'm sorry."，不能当成学生回答；按没听清处理，不降级
    seen,response=external_http;response['json']={'text':'Okay.'}
    p=Providers(asr_backend='http',asr_base='http://asr.local/v1',asr_model='m')
    result=await p.transcribe(audio,'en')
    assert result['text']=='' and result['unclear'] is True and result['confidence'] is None
    assert seen==[]

@pytest.mark.asyncio
async def test_asr_falls_back_to_local_and_pauses_cloud(external_http,monkeypatch):
    seen,response=external_http;response['status']=502
    p=Providers(asr_backend='http',asr_base='http://asr.local/v1',asr_model='m',asr_fallback='vosk')
    local=[]
    def fake_vosk(pcm,rate,language):
        local.append(language);return {'text':'apple','confidence':0.9,'unclear':False,'provider':'vosk'}
    monkeypatch.setattr(p,'_vosk',fake_vosk)
    first=await p.transcribe(speech_like(),'en')
    assert first['text']=='apple' and first['provider']=='vosk-fallback'
    second=await p.transcribe(speech_like(),'en')
    assert second['provider']=='vosk-fallback'
    assert len(seen)==1 and local==['en','en']   # 云端刚失败，冷却期内不再每轮等超时

@pytest.mark.asyncio
async def test_asr_without_fallback_still_reports_failure(external_http):
    seen,response=external_http;response['status']=502
    p=Providers(asr_backend='http',asr_base='http://asr.local/v1',asr_model='m')
    with pytest.raises(ProviderError): await p.transcribe(speech_like(),'en')

def test_asr_env_settings(monkeypatch):
    for k,v in {'ASR_BACKEND':'http','ASR_BASE_URL':'http://x/v1','ASR_MODEL':'m','ASR_LANGUAGE_MAP':'en:English',
                'ASR_FALLBACK':'vosk','ASR_TIMEOUT':'2.5','ASR_MIN_RMS':'150',
                'TENCENT_SECRET_ID':'AKIDenv','TENCENT_SECRET_KEY':'envkey'}.items(): monkeypatch.setenv(k,v)
    p=Providers.from_env()
    assert (p.asr_fallback,p.asr_timeout,p.asr_min_rms,p.asr_language_map)==('vosk',2.5,150.0,'en:English')
    assert (p.tencent_secret_id,p.tencent_secret_key)==('AKIDenv','envkey')
    assert 'envkey' not in repr(p)

@pytest.mark.asyncio
async def test_malformed_audio_rejected_before_asr_request(external_http):
    seen,_=external_http
    with pytest.raises(ValueError): await Providers().transcribe(b'not-wav','en')
    assert not seen

@pytest.mark.asyncio
async def test_tencent_asr_signed_request_and_engine(external_http):
    seen,response=external_http;response['json']={'Response':{'Result':'Apple.','AudioDuration':900,'RequestId':'r1'}}
    p=Providers(asr_backend='tencent',tencent_secret_id='AKIDtest-only',tencent_secret_key='test-only-key')
    result=await p.transcribe(speech_like(),'en')
    assert result=={'text':'Apple.','confidence':None,'unclear':False,'provider':'tencent'}
    req=seen[0]
    assert str(req.url)=='https://asr.tencentcloudapi.com/'
    assert req.headers['x-tc-action']=='SentenceRecognition' and req.headers['x-tc-version']=='2019-06-14'
    auth=req.headers['authorization']
    assert auth.startswith('TC3-HMAC-SHA256 Credential=AKIDtest-only/') and '/asr/tc3_request' in auth
    assert 'SignedHeaders=content-type;host' in auth and 'test-only-key' not in auth
    body=json.loads(req.content)
    assert body['EngSerViceType']=='16k_en' and body['SourceType']==1 and body['VoiceFormat']=='wav'
    import base64
    assert body['DataLen']==len(base64.b64decode(body['Data']))
    await p.transcribe(speech_like(),'zh')
    assert json.loads(seen[1].content)['EngSerViceType']=='16k_zh'

@pytest.mark.asyncio
async def test_tencent_asr_error_falls_back_and_empty_is_unclear(external_http,monkeypatch):
    seen,response=external_http
    response['json']={'Response':{'Error':{'Code':'AuthFailure.SignatureFailure','Message':'bad'},'RequestId':'r'}}
    p=Providers(asr_backend='tencent',tencent_secret_id='AKIDx',tencent_secret_key='k',asr_fallback='vosk')
    monkeypatch.setattr(p,'_vosk',lambda pcm,rate,language:{'text':'apple','confidence':0.8,'unclear':False,'provider':'vosk'})
    assert (await p.transcribe(speech_like(),'en'))['provider']=='vosk-fallback'
    q=Providers(asr_backend='tencent',tencent_secret_id='AKIDx',tencent_secret_key='k')
    with pytest.raises(ProviderError): await q.transcribe(speech_like(),'en')
    response['json']={'Response':{'Result':'','RequestId':'r'}}
    assert (await q.transcribe(speech_like(),'en'))['unclear'] is True

@pytest.mark.asyncio
async def test_tencent_asr_needs_keys_and_skips_silence(external_http):
    seen,_=external_http
    with pytest.raises(ProviderError): await Providers(asr_backend='tencent').transcribe(speech_like(),'en')
    p=Providers(asr_backend='tencent',tencent_secret_id='AKIDx',tencent_secret_key='k')
    assert (await p.transcribe(pcm_wav(b'\0'*48000),'en'))['provider']=='gate'
    assert seen==[]

def test_tencent_signature_is_deterministic():
    from english_class.providers import tc3_authorization
    a=tc3_authorization('AKIDx','key','asr','asr.tencentcloudapi.com',b'{}',1700000000)
    assert a==tc3_authorization('AKIDx','key','asr','asr.tencentcloudapi.com',b'{}',1700000000)
    assert 'Credential=AKIDx/2023-11-14/asr/tc3_request' in a
    assert a!=tc3_authorization('AKIDx','key2','asr','asr.tencentcloudapi.com',b'{}',1700000000)
