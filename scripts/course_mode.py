#!/usr/bin/env python3
"""Explicit, reversible switch of microphone ownership. Never edits nox source."""
import argparse,json,os,subprocess,time
from pathlib import Path
STATE=Path('/var/lib/english-class-edge/previous-services.json')

def run(*args,check=True):
    return subprocess.run(['systemctl',*args],capture_output=True,text=True,check=check)

def restore(saved):
    run('disable','--now','english-edge.service',check=False)
    if saved.get('exists'):
        if saved.get('enabled')=='enabled': run('enable','nox-voice.service')
        elif saved.get('enabled')=='enabled-runtime': run('enable','--runtime','nox-voice.service')
        if saved.get('active'): run('start','nox-voice.service')

p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['on','off']);a=p.parse_args()
if os.geteuid()!=0: raise SystemExit('请由sudo/root执行')
if a.mode=='on':
    if STATE.exists(): saved=json.loads(STATE.read_text())
    else:
        exists=run('show','nox-voice.service','--property=LoadState','--value',check=False).stdout.strip()=='loaded'
        saved={'exists':exists,'active':run('is-active','--quiet','nox-voice.service',check=False).returncode==0,
               'enabled':run('is-enabled','nox-voice.service',check=False).stdout.strip()}
        STATE.parent.mkdir(parents=True,exist_ok=True);STATE.write_text(json.dumps(saved));STATE.chmod(0o600)
    try:
        if saved['exists']: run('disable','--now','nox-voice.service')
        run('enable','--now','english-edge.service')
        time.sleep(2)
        if run('is-active','--quiet','english-edge.service',check=False).returncode:
            raise RuntimeError('课程语音服务启动失败')
        print('课程模式已开启。查看日志：journalctl -u english-edge -f')
    except Exception:
        restore(saved);STATE.unlink(missing_ok=True)
        raise SystemExit('切换失败，已尝试恢复原机器人；请查看 english-edge 日志。')
else:
    if not STATE.exists(): raise SystemExit('没有保存过切换前状态；未猜测或修改原服务')
    saved=json.loads(STATE.read_text());restore(saved);STATE.unlink()
    print('已按切换前状态恢复原nox-voice。')
