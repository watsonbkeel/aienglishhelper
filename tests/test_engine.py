import copy
import json
import pytest

class MemoryIO:
    """Test fixture only. Not imported by the installed application."""
    def __init__(self):
        self.config_value={'grade':1,'semester':1,'unit':0,'duration_minutes':5,'chinese_help':True,'difficulty':'basic'}
        self.words_value=[{'word_id':'a','word':'apple','meaning':'苹果'}, {'word_id':'b','word':'banana','meaning':'香蕉'}, {'word_id':'c','word':'bag','meaning':'书包'}]
        self.rows={};self.writes=[];self.chat_calls=[];self.fail=False
    async def config(self): return copy.deepcopy(self.config_value)
    async def words(self,cfg): return copy.deepcopy(self.words_value)
    async def progress(self): return {'today':'2026-09-29','words':list(self.rows.values())}
    async def record(self,word_id,status,unclear,key):
        self.writes.append((word_id,status,unclear,key))
        r=self.rows.setdefault(word_id,{'word_id':word_id,'status':0,'unclear_count':0})
        r['status']=max(r['status'],status or 0);r['unclear_count']+=int(unclear)
        return dict(r)
    async def chat(self,messages,json_output=True):
        from english_class.client import ServiceError
        if self.fail: raise ServiceError('provider unavailable')
        self.chat_calls.append(messages)
        prompt=messages[0]['content']
        data=json.loads(messages[-1]['content'])
        if 'VOCABULARY_JUDGE' in prompt:
            answer=data['answer'].lower().strip();word=data['word']
            correct=answer==data['meaning'] if data['kind']=='listen' else answer in [word,word+'s']
            return json.dumps({'correct':correct})
        if 'ENGLISH_CUE' in prompt: return json.dumps({'cue':'Which fruit is often red?'})
        return json.dumps({'reply':[{'text':'What do you like to eat?','language':'en'}],'relevant':True})

@pytest.mark.asyncio
async def test_lesson_listen_recall_dialog_and_records():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io)
    start=await t.turn('',action='start',request_id='request-000')
    assert start['phase']=='listen' and start['expected_language']=='zh'
    for i,answer in enumerate(['苹果','香蕉','书包']): await t.turn(answer,request_id=f'listen-{i:04}')
    assert all(r['status']==1 for r in io.rows.values())
    for i,answer in enumerate(['apple','banana','bag']): result=await t.turn(answer,request_id=f'speak-{i:04}')
    assert result['phase']=='dialog'
    assert all(r['status']==2 for r in io.rows.values())
    assert all(w[0] in {'a','b','c'} for w in io.writes)

@pytest.mark.asyncio
async def test_unclear_never_degrades_or_advances():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    r=await t.turn('banana',confidence=0.1,request_id='unclear-1')
    assert r['phase']=='listen' and t.index==0
    assert io.rows['a']['status']==0 and io.rows['a']['unclear_count']==1
    assert not io.chat_calls

@pytest.mark.asyncio
async def test_repeat_after_help_does_not_count_as_independent_speech():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    for i,a in enumerate(['苹果','香蕉','书包']): await t.turn(a,request_id=f'listen-{i}')
    help_result=await t.turn('',action='help',request_id='help-001')
    assert help_result['phase']=='repeat'
    await t.turn('apple',request_id='echo-001')
    assert io.rows['a']['status']==1
    assert t.phase=='recall' and t.index==1

@pytest.mark.asyncio
async def test_wrong_answer_not_unclear():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    await t.turn('香蕉',request_id='wrong-00')
    assert io.rows['a']['status']==0 and io.rows['a']['unclear_count']==0
    assert t.index==1

@pytest.mark.asyncio
async def test_new_start_reads_new_config_and_progress():
    from english_class.engine import Tutor
    io=MemoryIO();io.rows['a']={'word_id':'a','status':2,'unclear_count':0}
    t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    assert t.words[0]['word_id']=='b'
    io.config_value['difficulty']='challenge'
    assert t.config['difficulty']=='basic'
    await t.turn('',action='start',request_id='start-01')
    assert t.config['difficulty']=='challenge'

@pytest.mark.asyncio
async def test_timeout_and_pause_no_writes():
    from english_class.engine import Tutor
    io=MemoryIO();clock=[0.0];t=Tutor(io,clock=lambda:clock[0])
    await t.turn('',action='start',request_id='start-00')
    await t.turn('',action='pause',request_id='pause-00')
    clock[0]=500
    await t.turn('',action='resume',request_id='resume-0')
    assert t.phase=='listen'
    clock[0]=801
    r=await t.turn('',action='tick',request_id='tick-000')
    assert not r['active'] and io.writes==[]

@pytest.mark.asyncio
async def test_provider_failure_not_fake_correct():
    from english_class.engine import Tutor
    from english_class.client import ServiceError
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00');io.fail=True
    with pytest.raises(ServiceError): await t.turn('苹果',request_id='err-0001')
    assert io.writes==[]

@pytest.mark.asyncio
async def test_chinese_help_off_uses_english_prompt():
    from english_class.engine import Tutor
    io=MemoryIO();io.config_value['chinese_help']=False;t=Tutor(io)
    r=await t.turn('',action='start',request_id='start-00')
    assert all(s['language']=='en' for s in r['segments'])

@pytest.mark.asyncio
async def test_dialog_prompt_repetition_cannot_upgrade():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    t.phase='dialog';t.known={'a':1,'b':1,'c':1};t.last_demonstrated={'a'}
    await t.turn('apple',request_id='dialog-1')
    assert not any(s==2 and w=='a' for w,s,u,k in io.writes)


def test_brain_auth_and_request_replay():
    from fastapi.testclient import TestClient
    from english_class.brain_api import create_brain
    io=MemoryIO();app=create_brain(io,'edge-secret-1234567890')
    with TestClient(app) as c:
        body={'action':'start','request_id':'session-start-001','text':''}
        assert c.post('/voice/turn',json=body).status_code==401
        h={'Authorization':'Bearer edge-secret-1234567890'}
        r=c.post('/voice/turn',json=body,headers=h)
        assert r.status_code==200
        assert c.post('/voice/turn',json=body,headers=h).json()==r.json()
        assert c.post('/voice/turn',json={**body,'text':'different'},headers=h).status_code==409
        assert c.post('/voice/turn',json={'request_id':'tick-001','action':'tick'},headers=h).status_code==200

@pytest.mark.asyncio
async def test_unclear_preserves_question_for_repeat():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io)
    original=await t.turn('',action='start',request_id='start-00')
    await t.turn('',unclear=True,request_id='unclear-001')
    again=await t.turn('',action='repeat',request_id='repeat-001')
    # 重复只重播完整题目，不重播开场白
    assert again['segments']==original['segments'][1:]
    assert '什么意思' in ' '.join(s['text'] for s in again['segments'])

@pytest.mark.asyncio
async def test_unclear_does_not_erase_demonstrated_dialog_words():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    t.phase='dialog';t.known={'a':1,'b':1,'c':1}
    t.result([{'text':'You can say apple. What would you like?', 'language':'en'}])
    await t.turn('',unclear=True,request_id='unclear-001')
    await t.turn('apple',request_id='answer-001')
    assert not any(s==2 and w=='a' for w,s,u,k in io.writes)

def _say(r): return ' '.join(s['text'] for s in r['segments'])

@pytest.mark.asyncio
async def test_first_prompt_is_full_later_prompts_are_short():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io)
    first=_say(await t.turn('',action='start',request_id='start-00'))
    assert '什么意思' in first and 'apple' in first
    second=await t.turn('苹果',request_id='listen-000')
    s=_say(second)
    assert 'banana' in s and '什么意思' not in s and '理解对了' not in s
    assert len(s)<=len('对！ banana.')+2
    third=_say(await t.turn('书包',request_id='listen-001'))  # wrong for banana
    assert '还需要继续练习' not in third and 'bag' in third
    # recall: first question full, later short
    recall=_say(await t.turn('书包',request_id='listen-002'))
    assert '用英语怎么说' in recall and '苹果' in recall
    nxt=_say(await t.turn('apple',request_id='speak-000'))
    assert '香蕉' in nxt and '用英语怎么说' not in nxt and '你说出了这个词' not in nxt

@pytest.mark.asyncio
async def test_unclear_reasks_current_question_briefly_after_first_time():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    u1=_say(await t.turn('',unclear=True,request_id='unclear-001'))
    assert '不算答错' in u1 and 'apple' in u1
    u2=_say(await t.turn('',unclear=True,request_id='unclear-002'))
    assert '不算答错' not in u2 and 'apple' in u2 and len(u2)<len(u1)
    assert t.index==0 and io.rows['a']['status']==0

@pytest.mark.asyncio
async def test_new_session_explains_in_full_again():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    await t.turn('苹果',request_id='listen-000')
    again=_say(await t.turn('',action='start',request_id='start-01'))
    assert '什么意思' in again

@pytest.mark.asyncio
async def test_silence_reasks_after_20s_at_most_twice():
    from english_class.engine import Tutor
    io=MemoryIO();clock=[0.0];t=Tutor(io,clock=lambda:clock[0])
    await t.turn('',action='start',request_id='start-00')
    clock[0]=10;assert (await t.turn('',action='tick',request_id='tick-0001'))['segments']==[]
    clock[0]=21;r=await t.turn('',action='tick',request_id='tick-0002')
    assert 'apple' in _say(r) and r['active']
    clock[0]=30;assert (await t.turn('',action='tick',request_id='tick-0003'))['segments']==[]
    clock[0]=42;assert 'apple' in _say(await t.turn('',action='tick',request_id='tick-0004'))
    clock[0]=70;assert (await t.turn('',action='tick',request_id='tick-0005'))['segments']==[]
    assert io.writes==[]

@pytest.mark.asyncio
async def test_idle_3min_pauses_saves_and_next_start_resumes(tmp_path):
    from english_class.engine import Tutor
    io=MemoryIO();clock=[0.0];wall=[1000.0];state=tmp_path/'resume.json'
    t=Tutor(io,clock=lambda:clock[0],wall=lambda:wall[0],state_path=state)
    await t.turn('',action='start',request_id='start-00')
    await t.turn('苹果',request_id='listen-000')
    clock[0]=181;r=await t.turn('',action='tick',request_id='tick-0001')
    assert not r['active'] and '休息' in _say(r) and state.exists()
    assert io.rows['a']['status']==1
    t2=Tutor(io,clock=lambda:clock[0],wall=lambda:wall[0]+3600,state_path=state)
    r2=await t2.turn('',action='start',request_id='start-01')
    assert '接着上次' in _say(r2) and 'banana' in _say(r2)
    assert t2.index==1 and [w['word_id'] for w in t2.words]==['a','b','c']

@pytest.mark.asyncio
async def test_resume_expires_after_7_days_or_config_change(tmp_path):
    from english_class.engine import Tutor
    state=tmp_path/'resume.json'
    for change in ('expire','config'):
        io=MemoryIO();clock=[0.0];wall=[1000.0]
        t=Tutor(io,clock=lambda:clock[0],wall=lambda:wall[0],state_path=state)
        await t.turn('',action='start',request_id='start-00');await t.turn('苹果',request_id='listen-000')
        await t.turn('',action='stop',request_id='stop-0000');assert state.exists()
        if change=='expire': wall[0]+=8*86400
        else: io.config_value['unit']=2
        r=await t.turn('',action='start',request_id='start-01')
        assert '接着上次' not in _say(r) and t.index==0

@pytest.mark.asyncio
async def test_completed_lesson_clears_resume_and_stop_when_idle_keeps_it(tmp_path):
    from english_class.engine import Tutor
    io=MemoryIO();state=tmp_path/'resume.json';t=Tutor(io,state_path=state)
    await t.turn('',action='start',request_id='start-00');await t.turn('',action='stop',request_id='stop-0000')
    assert state.exists()
    await t.turn('',action='stop',request_id='stop-0001');assert state.exists()
    await t.turn('',action='start',request_id='start-01')
    t.phase='dialog';t.dialog_count=3
    r=await t.turn('I like apples',request_id='dialog-01')
    assert not r['active'] and not state.exists()

@pytest.mark.asyncio
async def test_entering_dialog_clears_stale_resume_point(tmp_path):
    from english_class.engine import Tutor
    io=MemoryIO();state=tmp_path/'resume.json';t=Tutor(io,state_path=state)
    await t.turn('',action='start',request_id='start-00');await t.turn('',action='stop',request_id='stop-0000')
    assert state.exists()
    await t.turn('',action='start',request_id='start-01')
    t.phase='recall';t.index=len(t.words)-1
    await t.turn(t.words[-1]['word'],request_id='recall-last')
    assert t.phase=='dialog' and not state.exists()
    await t.turn('',action='stop',request_id='stop-0001')
    assert not state.exists()

@pytest.mark.asyncio
async def test_max_request_id_fits_progress_idempotency_header():
    from english_class.engine import Tutor
    io=MemoryIO();t=Tutor(io);await t.turn('',action='start',request_id='start-00')
    await t.turn('苹果',request_id='x'*128)
    assert len(io.writes[-1][3])<=128

@pytest.mark.asyncio
async def test_audio_transcription_and_turn_are_one_serial_operation():
    import asyncio
    import httpx
    from english_class.brain_api import create_brain
    io=MemoryIO();languages=[]
    async def transcribe(wav,language):
        languages.append(language)
        await asyncio.sleep(.01)
        return {'text':'苹果' if language=='zh' else 'apple','confidence':1.0,'unclear':False}
    io.transcribe=transcribe
    app=create_brain(io,'edge-secret-1234567890',practice_size=1)
    h={'Authorization':'Bearer edge-secret-1234567890'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers=h) as c:
        await c.post('/voice/turn',json={'action':'start','request_id':'start-001'})
        results=await asyncio.gather(c.post('/voice/audio?request_id=audio-001',content=b'test1'),c.post('/voice/audio?request_id=audio-002',content=b'test2'))
    assert all(r.status_code==200 for r in results)
    assert languages==['zh','en']


@pytest.mark.asyncio
async def test_practice_words_from_config_controls_batch_size():
    from english_class.engine import Tutor
    io=MemoryIO();io.words_value=[{'word_id':f'w{i}','word':f'word{i}','meaning':f'意思{i}'} for i in range(12)]
    io.config_value['practice_words']=8
    t=Tutor(io);r=await t.turn('',action='start',request_id='start-00')
    assert r['word_count']==8
    io.config_value.pop('practice_words');t=Tutor(io,practice_size=3)
    assert (await t.turn('',action='start',request_id='start-01'))['word_count']==3


@pytest.mark.asyncio
@pytest.mark.parametrize('grade,stage',[(3,'elementary school'),(8,'middle school'),(11,'high school')])
async def test_llm_persona_follows_school_stage(grade,stage):
    from english_class.engine import Tutor
    io=MemoryIO();io.config_value['grade']=grade;t=Tutor(io)
    await t.turn('',action='start',request_id='start-00')
    t.phase='dialog';await t.turn('I like apples',request_id='dialog-01')
    system=io.chat_calls[-1][0]['content']
    assert stage in system
    if grade>6: assert 'elementary' not in system
