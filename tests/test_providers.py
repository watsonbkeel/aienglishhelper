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

@pytest.mark.asyncio
async def test_asr_has_no_invented_confidence(external_http):
    seen,response=external_http;response['json']={'text':'apple'}
    p=Providers(asr_backend='http',asr_base='https://asr.example/v1',asr_key='test-only',asr_model='configured-model')
    result=await p.transcribe(pcm_wav(b'\0'*3200),'en')
    assert result=={'text':'apple','confidence':None,'unclear':False,'provider':'http'}
    assert str(seen[0].url)=='https://asr.example/v1/audio/transcriptions'
    assert b'name="language"' in seen[0].content and b'\r\nen\r\n' in seen[0].content
    response['json']={'text':''}
    assert (await p.transcribe(pcm_wav(b'\0'*3200),'en'))['unclear'] is True

@pytest.mark.asyncio
async def test_malformed_audio_rejected_before_asr_request(external_http):
    seen,_=external_http
    with pytest.raises(ValueError): await Providers().transcribe(b'not-wav','en')
    assert not seen
