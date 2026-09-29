import importlib.util
import json
from pathlib import Path
import pytest


def test_provision_creates_only_student_credentials(db,tmp_path):
    from english_class.provision import provision
    out=tmp_path/'s001'
    provision(db,'s001',9101,out,'http://127.0.0.1:18090','https://class.example/api-host','https://class.example/students/s001')
    brain=(out/'brain.env').read_text();pi=(out/'pi.env').read_text();mini=(out/'english-env.local.js').read_text()
    assert 'LLM_API_KEY' not in brain+pi+mini
    assert 'BRAIN_TOKEN=' in brain and 'EDGE_TOKEN=' in pi
    assert 'BRAIN_TOKEN' not in pi+mini
    assert '9101' in brain
    assert db.config('s001')['unit']==0
    with pytest.raises(ValueError): provision(db,'s001',9101,out,'http://x','https://x','https://y')


def test_source_hash_detects_modified_dictionary():
    from english_class.sources import git_blob_sha, verify_blob
    raw=b'hello\n'
    assert git_blob_sha(raw)=='ce013625030ba8dba906f756967f9e9ca394464a'
    with pytest.raises(ValueError): verify_blob(raw,'0000000000000000000000000000000000000000')


def test_miniprogram_merge_preserves_original(tmp_path):
    from english_class.sources import merge_miniprogram
    src=tmp_path/'original';src.mkdir()
    (src/'app.json').write_text(json.dumps({'pages':['pages/learn/index'],'tabBar':{'list':[{'pagePath':'pages/learn/index','text':'学习'}]}}))
    (src/'app.js').write_text('App({original: true})')
    dest=tmp_path/'merged'
    overlay=Path(__file__).resolve().parents[1]/'miniprogram'
    merge_miniprogram(src,overlay,dest)
    cfg=json.loads((dest/'app.json').read_text())
    assert cfg['pages'][0]=='pages/english-config/index'
    assert 'pages/learn/index' in cfg['pages']
    assert cfg['tabBar']['list'][0]['text']=='学习'
    assert (dest/'app.js').read_text()=='App({original: true})'
    assert json.loads((src/'app.json').read_text())['pages']==['pages/learn/index']
    with pytest.raises(ValueError): merge_miniprogram(src,overlay,dest)


def test_no_extract_path_traversal(tmp_path):
    import io, zipfile
    from english_class.sources import extract_archive
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z: z.writestr('../bad.txt','bad')
    with pytest.raises(ValueError): extract_archive(buf.getvalue(),tmp_path/'out')


def test_pi_command_and_vad_no_training_on_silence():
    from pi.audio import VoiceActivity, control_action
    import array
    v=VoiceActivity(threshold=100,silence_chunks=2,max_chunks=20)
    assert all(v.feed(b'\x00'*3200) is None for _ in range(5))
    speech=array.array('h',[1000]*1600).tobytes()
    assert v.feed(speech) is None
    assert v.feed(b'\x00'*3200) is None
    wav=v.feed(b'\x00'*3200)
    assert wav and wav.startswith(b'RIFF')
    assert control_action('小爱同学')=='wake'
    assert control_action('我 不 会')=='help'
    assert control_action('do not stop') is None


def test_wave_validation():
    from english_class.providers import pcm_wav,validate_wav
    wav=pcm_wav(b'\x00'*3200)
    assert validate_wav(wav)==(b'\x00'*3200,16000)
    with pytest.raises(ValueError): validate_wav(b'not wave')

def test_provision_does_not_create_student_if_files_cannot_be_written(db,tmp_path):
    from english_class.provision import provision
    blocked=tmp_path/'not-a-directory';blocked.write_text('occupied')
    with pytest.raises(OSError):
        provision(db,'s003',9103,blocked/'s003','http://127.0.0.1:18090','https://class.example','https://class.example/students/s003')
    with pytest.raises(ValueError): db.config('s003')


def test_public_port_default_avoids_known_conflict_and_is_single_sourced(monkeypatch):
    # 目标服务器 127.0.0.1:18080 已被其他生产服务(flower)占用；默认端口不得再用 18080，
    # 且代码、配置模板、安装脚本必须用同一来源，不能各自写死。
    from english_class import DEFAULT_PUBLIC_PORT
    assert DEFAULT_PUBLIC_PORT==18090
    root=Path(__file__).resolve().parents[1]
    env=(root/'deploy/public.env.example').read_text()
    assert f'PUBLIC_PORT={DEFAULT_PUBLIC_PORT}' in env
    nginx=(root/'deploy/nginx-locations.conf.example').read_text()
    assert f'127.0.0.1:{DEFAULT_PUBLIC_PORT};' in nginx
    for rel in ('english_class/run.py','english_class/brain_api.py','english_class/cli.py',
                'scripts/install_server.sh','scripts/create_student.sh'):
        assert '18080' not in (root/rel).read_text(),rel
    monkeypatch.delenv('PUBLIC_URL',raising=False)
    import english_class.brain_api as b
    seen={}
    monkeypatch.setattr(b,'PublicClient',lambda url,*a:seen.setdefault('url',url))
    monkeypatch.setattr(b,'create_brain',lambda *a,**k:None)
    for k,v in {'STUDENT_ID':'s001','BRAIN_TOKEN':'x'*20,'EDGE_TOKEN':'y'*20}.items(): monkeypatch.setenv(k,v)
    b.from_env()
    assert seen['url']==f'http://127.0.0.1:{DEFAULT_PUBLIC_PORT}'


def test_install_health_check_verifies_it_is_our_service():
    # 端口上若是别的服务，安装器不能把它的200当成本服务健康。
    script=(Path(__file__).resolve().parents[1]/'scripts/install_server.sh').read_text()
    assert "['service']=='public'" in script


def test_pi_tick_is_frequent_enough_for_20s_reask_and_brain_has_state_dir():
    from pi.english_voice import TICK_SECONDS
    from english_class.engine import REASK_SECONDS
    assert TICK_SECONDS<=REASK_SECONDS/4
    unit=(Path(__file__).resolve().parents[1]/'deploy/english-brain@.service').read_text()
    assert 'StateDirectory=english-class-brain/%i' in unit


def test_pi_playback_failure_is_not_silent(monkeypatch):
    from pi.english_voice import Edge
    class FailedPlayer:
        returncode=1
        def communicate(self,*args,**kwargs): pass
        def poll(self): return 1
    monkeypatch.setattr('pi.english_voice.subprocess.Popen',lambda *a,**k:FailedPlayer())
    edge=object.__new__(Edge);edge.audio_enabled=True;edge.playing=False;edge.player=None
    with pytest.raises(RuntimeError,match='播放'):
        edge.play(b'RIFF-test')
