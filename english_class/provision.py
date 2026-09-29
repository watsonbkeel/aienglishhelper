"""Generate only classroom-scoped secrets; no provider credentials in exports."""
from __future__ import annotations
import json
import os
import re
import secrets
import shutil
from pathlib import Path
from urllib.parse import urlsplit


def provision(store,student_id:str,port:int,out:Path,public_url:str,external_api_url:str,brain_url:str):
    out=Path(out)
    if out.exists(): raise ValueError('输出目录已存在；拒绝覆盖已有凭证')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,31}',student_id) or not 1024<=port<=65535:
        raise ValueError('学生ID或端口无效')
    for url in (public_url,external_api_url,brain_url):
        p=urlsplit(url)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment or any(x in url for x in '\n\r\"'):
            raise ValueError('服务URL必须是不含凭证、查询参数的HTTP(S)地址')
    parent=secrets.token_urlsafe(32);brain=secrets.token_urlsafe(32);edge=secrets.token_urlsafe(32)
    out.mkdir(parents=True,mode=0o700)
    try:
        (out/'brain.env').write_text(f'STUDENT_ID={student_id}\nPUBLIC_URL={public_url.rstrip("/")}\nBRAIN_TOKEN={brain}\nEDGE_TOKEN={edge}\nBRAIN_HOST=127.0.0.1\nBRAIN_PORT={port}\nPRACTICE_WORDS=3\nSTUDENT_PROMPT_PATH=prompts/student.md\n',encoding='utf-8')
        (out/'pi.env').write_text(f'BRAIN_URL={brain_url.rstrip("/")}\nEDGE_TOKEN={edge}\nCAPTURE_DEVICE=auto\nPLAYBACK_DEVICE=default\nVOSK_ZH_PATH=/opt/english-class-edge/models/vosk-model-small-cn-0.22\nVAD_THRESHOLD=450\nMIC_GAIN=1.0\nALLOW_INSECURE_HTTP=0\n',encoding='utf-8')
        mini={'baseUrl':external_api_url.rstrip('/'),'studentId':student_id,'token':parent,'allowHttpForLan':False}
        (out/'english-env.local.js').write_text('// 仅限本人课堂预览，不要提交到公开仓库。\nmodule.exports = '+json.dumps(mini,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (out/'README.txt').write_text('brain.env：只交给老师放到本人的服务器进程。\npi.env：放到自己的树莓派。\nenglish-env.local.js：替换小程序 utils 下同名文件，只含家长课堂凭证。\n这些不是大模型密钥，但仍不要公开分享。\n',encoding='utf-8')
        for p in out.iterdir(): p.chmod(0o600)
        store.add_student(student_id,parent,brain)
    except Exception:
        shutil.rmtree(out)
        raise
    return {'student_id':student_id,'port':port,'output':str(out)}
