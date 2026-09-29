import json
import sqlite3
import pytest
from conftest import headers


def test_dictionary_parser_does_not_execute_javascript(tmp_path):
    from english_class.dictionary import parse_source
    s='const fullDictionary = [{"word_id":"x","grade":1,"semester":1,"word":"cat","meaning":"猫"}];\nmodule.exports = { fullDictionary }'
    assert parse_source(s)[0]['word']=='cat'
    with pytest.raises(ValueError): parse_source('const fullDictionary = runMaliciousCode();')


def test_dictionary_duplicate_ids_fail(tmp_path):
    from english_class.dictionary import Dictionary
    x={'word_id':'x','grade':1,'semester':1,'word':'a','meaning':'一'}
    p=tmp_path/'x.json';p.write_text(json.dumps([x,x]))
    with pytest.raises(ValueError): Dictionary(p)


def test_words_whole_term_and_groups(client):
    r=client.get('/api/words?student_id=s001&grade=1&semester=1&unit=0',headers=headers())
    assert r.status_code==200
    assert len(r.json()['words'])==3
    assert r.json()['unit_kind']=='ordered_group_not_textbook'
    assert client.get('/api/words?student_id=s001&grade=1&semester=1&unit=99',headers=headers()).status_code==422


def test_middle_and_high_school_grades_are_open(client):
    r=client.get('/api/words?student_id=s001&grade=7&semester=1&unit=0',headers=headers())
    assert r.status_code==200 and r.json()['words'][0]['word']=='background'
    terms=r.json()['available_terms']
    assert {'grade':7,'semester':1} in terms and {'grade':12,'semester':2} in terms
    assert client.get('/api/words?student_id=s001&grade=12&semester=2&unit=0',headers=headers()).status_code==200
    assert client.get('/api/words?student_id=s001&grade=13&semester=1&unit=0',headers=headers()).status_code==422
    c={'grade':12,'semester':2,'unit':0,'duration_minutes':10,'chinese_help':True,'difficulty':'basic'}
    assert client.put('/api/config?student_id=s001',json=c,headers=headers()).status_code==200
    assert client.put('/api/config?student_id=s001',json={**c,'grade':13},headers=headers()).status_code==422
    body={'word_id':'12b_001','status':1,'unclear':False}
    assert client.post('/api/progress?student_id=s001',json=body,headers=headers('brain')).status_code==200


def test_credentials_must_match_student(client):
    assert client.get('/api/config?student_id=s001').status_code==401
    assert client.get('/api/config?student_id=s002',headers=headers()).status_code==403
    assert client.get('/api/config?student_id=s001',headers={'Authorization':'Bearer wrong'}).status_code==401


def test_config_roundtrip_and_validation(client):
    c={'grade':1,'semester':1,'unit':1,'duration_minutes':5,'chinese_help':False,'difficulty':'challenge','practice_words':3}
    assert client.put('/api/config?student_id=s001',json=c,headers=headers()).json()==c
    assert client.get('/api/config?student_id=s001',headers=headers('brain')).json()==c
    assert client.get('/api/config?student_id=s002',headers=headers(student='B')).json()['unit']==0
    assert client.put('/api/config?student_id=s001',json={**c,'difficulty':'magic'},headers=headers()).status_code==422
    assert client.put('/api/config?student_id=s001',json={**c,'unit':999},headers=headers()).status_code==422


def test_progress_parent_readonly_and_other_students_protected(client):
    body={'word_id':'1a_021','status':1,'unclear':False}
    assert client.post('/api/progress?student_id=s001',json=body,headers=headers()).status_code==403
    assert client.post('/api/progress?student_id=s002',json=body,headers=headers('brain')).status_code==403
    assert client.post('/api/progress?student_id=s001',json=body,headers=headers('brain')).status_code==200
    assert client.get('/api/progress?student_id=s002',headers=headers(student='B')).json()['words']==[]


def test_progress_monotonic_unclear_and_idempotency(client):
    def post(status,unclear=False,key=None):
        h=headers('brain')
        if key: h['Idempotency-Key']=key
        return client.post('/api/progress?student_id=s001',json={'word_id':'1a_021','status':status,'unclear':unclear},headers=h)
    assert post(2).json()['status']==2
    assert post(1).json()['status']==2
    assert post(None,True,'same-event').json()['unclear_count']==1
    assert post(None,True,'same-event').json()['unclear_count']==1
    assert post(1,False,'same-event').status_code==409
    assert post(2,True).status_code==422
    assert post(3).status_code==422
    assert post(True).status_code==422
    r=client.get('/api/progress?student_id=s001',headers=headers()).json()
    assert r['words'][0]['last_practiced_date']==r['today']
    assert r['words'][0]['word']=='apple'


def test_progress_unknown_word_and_empty_requests(client):
    assert client.post('/api/progress?student_id=s001',json={'word_id':'not_real','status':2,'unclear':False},headers=headers('brain')).status_code==422
    assert client.post('/api/progress?student_id=s001',json={'word_id':'1a_021','status':None,'unclear':False},headers=headers('brain')).status_code==200
    r=client.get('/api/progress?student_id=s001',headers=headers()).json()['words'][0]
    assert r['status']==0 and r['last_practiced_date']


def test_restart_persists_and_database_no_plaintext_tokens(db):
    from english_class.store import Store
    db.add_student('s001','Parent_A_very_long_token','Brain_A_very_long_token')
    db.record('s001','1a_021',1,False)
    again=Store(db.path,db.dictionary)
    assert again.progress('s001')['words'][0]['status']==1
    assert b'Parent_A_very_long_token' not in db.path.read_bytes()


def test_duplicate_student_never_overwrites(db):
    db.add_student('s001','parent-abc-1234567890','brain-abc-1234567890')
    with pytest.raises(ValueError): db.add_student('s001','parent-other-12345678','brain-other-123456789')


def test_providers_require_brain_not_parent(client):
    r=client.post('/internal/chat?student_id=s001',json={'messages':[{'role':'user','content':'hi'}]},headers=headers())
    assert r.status_code==403


def test_config_accepts_longer_sessions_and_practice_words(client):
    c={'grade':8,'semester':1,'unit':0,'duration_minutes':30,'chinese_help':True,'difficulty':'standard','practice_words':10}
    assert client.put('/api/config?student_id=s001',json={**c,'grade':7},headers=headers()).json()['practice_words']==10
    for bad in ({'duration_minutes':25},{'practice_words':0},{'practice_words':11}):
        assert client.put('/api/config?student_id=s001',json={**c,'grade':7,**bad},headers=headers()).status_code==422


def test_old_saved_config_gets_default_practice_words(db):
    db.add_student('s009','parent-old-1234567890','brain-old-12345678901')
    with db.connect() as con:
        con.execute("UPDATE students SET config=? WHERE id='s009'",(json.dumps({'grade':1,'semester':1,'unit':0,'duration_minutes':10,'chinese_help':True,'difficulty':'basic'}),))
    assert db.config('s009')['practice_words']==3


class FakeProviders:
    """Test double only: records which model answered; never used in production."""
    llm_model='deepseek-flash'
    def __init__(self): self.calls=[];self.student_fail=False;self.student_text='{"correct":true}';self.last=None
    def check_llm_url(self,url):
        from english_class.providers import validate_llm_url
        return validate_llm_url(url,resolve=lambda h,p,type=0:[(0,0,0,'',('10.0.0.5' if h=='intranet.example' else '8.8.8.8',p))])
    async def chat(self,messages,json_output=False,llm=None,timeout=None):
        from english_class.providers import ProviderError
        self.calls.append('student' if llm else 'platform');self.last={'messages':messages,'json_output':json_output,'timeout':timeout}
        if llm and (self.student_fail or llm['api_key']=='bad-key-123456'): raise ProviderError('自带模型的密钥无效或无权限')
        return self.student_text if llm else '{"ok":"platform"}'


@pytest.fixture
def llm_client(db):
    from fastapi.testclient import TestClient
    from english_class.public_api import create_app
    db.add_student('s001','Parent_A_very_long_token','Brain_A_very_long_token')
    db.add_student('s002','Parent_B_very_long_token','Brain_B_very_long_token')
    fake=FakeProviders()
    with TestClient(create_app(db,fake)) as c: yield c,fake,db


def test_student_llm_is_preferred_masked_and_falls_back(llm_client):
    c,fake,db=llm_client
    chat=lambda: c.post('/internal/chat?student_id=s001',json={'messages':[{'role':'user','content':'hi'}],'json_output':True},headers=headers('brain'))
    assert c.get('/api/llm?student_id=s001',headers=headers()).json()['mode']=='platform'
    assert chat().json()['provider']=='platform'
    body={'base_url':'https://api.example.com/v1/chat/completions','model':'gpt-4o-mini','api_key':'sk-student-secret-9876'}
    r=c.put('/api/llm?student_id=s001',json=body,headers=headers())
    assert r.status_code==200 and r.json()['mode']=='custom' and r.json()['base_url']=='https://api.example.com/v1'
    assert 'sk-student-secret-9876' not in r.text and r.json()['key_hint'].endswith('9876')
    assert chat().json()['provider']=='student'
    assert c.post('/internal/chat?student_id=s002',json={'messages':[{'role':'user','content':'hi'}]},headers=headers('brain',student='B')).json()['provider']=='platform'
    fake.student_fail=True
    assert chat().json()['provider']=='platform'
    view=c.get('/api/llm?student_id=s001',headers=headers()).json()
    assert view['last_status']=='fallback' and '密钥' in view['last_error']
    fake.student_fail=False;fake.student_text='not json'
    assert chat().json()['provider']=='platform'
    assert c.delete('/api/llm?student_id=s001',headers=headers()).json()['mode']=='platform'


def test_student_llm_validation_roles_and_keep_key(llm_client):
    c,fake,db=llm_client
    ok={'base_url':'https://api.example.com','model':'deepseek-chat','api_key':'sk-first-key-123456'}
    assert c.put('/api/llm?student_id=s001',json=ok,headers=headers('brain')).status_code==403
    assert c.put('/api/llm?student_id=s002',json=ok,headers=headers()).status_code==403
    for bad in ({'base_url':'http://api.example.com'},{'base_url':'https://intranet.example'},{'base_url':'https://127.0.0.1'},
                {'model':'bad model'},{'api_key':'bad-key-123456'}):
        assert c.put('/api/llm?student_id=s001',json={**ok,**bad},headers=headers()).status_code==422
    assert c.get('/api/llm?student_id=s001',headers=headers()).json()['mode']=='platform'
    assert c.put('/api/llm?student_id=s001',json={**ok,'api_key':None},headers=headers()).status_code==422
    assert c.put('/api/llm?student_id=s001',json=ok,headers=headers()).status_code==200
    r=c.put('/api/llm?student_id=s001',json={**ok,'model':'deepseek-reasoner','api_key':''},headers=headers())
    assert r.status_code==200 and r.json()['model']=='deepseek-reasoner'
    assert db.llm('s001')['api_key']=='sk-first-key-123456'


def test_llm_url_guard_blocks_private_targets():
    from english_class.providers import validate_llm_url
    pub=lambda h,p,type=0:[(0,0,0,'',('104.18.1.1',p))]
    assert validate_llm_url('https://api.x.com/v1/chat/completions/',resolve=pub)=='https://api.x.com/v1'
    for bad in ('http://api.x.com','https://user:pw@api.x.com','https://api.x.com?a=1','https://127.0.0.1','https://[::1]','https://169.254.169.254','ftp://x.com'):
        with pytest.raises(ValueError): validate_llm_url(bad,resolve=pub)
    with pytest.raises(ValueError): validate_llm_url('https://api.x.com',resolve=lambda h,p,type=0:[(0,0,0,'',('192.168.1.8',p))])


def test_old_database_gets_evidence_columns_without_losing_progress(tmp_path,dictionary_path):
    import sqlite3
    from english_class.store import Store
    from english_class.dictionary import Dictionary
    path=tmp_path/'old.sqlite3';con=sqlite3.connect(path)
    con.executescript('''CREATE TABLE students (id TEXT PRIMARY KEY, config TEXT NOT NULL);
    CREATE TABLE progress (student_id TEXT NOT NULL REFERENCES students(id), word_id TEXT NOT NULL, status INTEGER NOT NULL DEFAULT 0 CHECK(status BETWEEN 0 AND 2), unclear_count INTEGER NOT NULL DEFAULT 0, last_practiced_date TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(student_id,word_id));
    INSERT INTO students VALUES ('s001','{}');
    INSERT INTO progress VALUES ('s001','1a_021',2,3,'2026-09-01','2026-09-01T10:00:00+08:00');''')
    con.commit();con.close()
    db=Store(path,Dictionary(dictionary_path))
    row=db.progress('s001')['words'][0]
    assert (row['status'],row['unclear_count'],row['last_practiced_date'])==(2,3,'2026-09-01')
    assert (row['valid_count'],row['used_word_count'],row['imitated_count'])==(0,0,0)
    Store(path,Dictionary(dictionary_path))  # 再次打开不重复加列


def test_progress_evidence_accumulates_and_never_changes_status_rules(client):
    def post(status,evidence,unclear=False,key=None):
        h=headers('brain')
        if key: h['Idempotency-Key']=key
        body={'word_id':'1a_021','status':status,'unclear':unclear}
        if evidence is not None: body['evidence']=evidence
        return client.post('/api/progress?student_id=s001',json=body,headers=h)
    r=post(None,{'answer_valid':True,'used_word':True,'imitated':True},key='ev-1').json()
    assert r['status']==0 and (r['valid_count'],r['used_word_count'],r['imitated_count'])==(1,1,1)
    assert post(None,{'answer_valid':True,'used_word':True,'imitated':True},key='ev-1').json()['imitated_count']==1
    assert post(None,{'answer_valid':False,'used_word':True,'imitated':True},key='ev-1').status_code==409
    r=post(1,{'answer_valid':True,'used_word':False,'imitated':False}).json()
    assert r['status']==1 and r['valid_count']==2 and r['used_word_count']==1
    assert post(None,{'answer_valid':True},unclear=True).status_code==422
    assert post(None,{'bogus':True}).status_code==422
    assert post(None,None).json()['valid_count']==2


def test_student_llm_changing_address_requires_new_key(llm_client):
    c,fake,db=llm_client
    ok={'base_url':'https://api.example.com/v1','model':'m1','api_key':'sk-first-key-123456'}
    assert c.put('/api/llm?student_id=s001',json=ok,headers=headers()).status_code==200
    # 同一地址（写法不同）改模型可沿用旧密钥
    assert c.put('/api/llm?student_id=s001',json={**ok,'base_url':'https://api.example.com/v1/','model':'m2','api_key':None},headers=headers()).status_code==200
    r=c.put('/api/llm?student_id=s001',json={**ok,'base_url':'https://other.example.com/v1','api_key':None},headers=headers())
    assert r.status_code==422 and '密钥' in r.json()['detail']
    assert db.llm('s001')['base_url']=='https://api.example.com/v1'
    assert c.put('/api/llm?student_id=s001',json={**ok,'base_url':'https://other.example.com/v1','api_key':'sk-second-key-1234'},headers=headers()).status_code==200


def test_student_llm_save_test_uses_course_json_format_and_short_timeout(llm_client):
    c,fake,db=llm_client
    ok={'base_url':'https://api.example.com','model':'m1','api_key':'sk-first-key-123456'}
    assert c.put('/api/llm?student_id=s001',json=ok,headers=headers()).status_code==200
    assert fake.last['json_output'] is True and fake.last['timeout']==20
    assert 'VOCABULARY_JUDGE' in fake.last['messages'][0]['content']
    for bad in ('OK','{"correct":"yes"}','[1]','{"ok":true}'):
        fake.student_text=bad
        r=c.put('/api/llm?student_id=s001',json={**ok,'model':'m-bad'},headers=headers())
        assert r.status_code==422 and '格式' in r.json()['detail'],bad
    assert db.llm('s001')['model']=='m1'
