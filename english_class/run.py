"""Service runner; supports a simple KEY=VALUE env file without executing shell code."""
from __future__ import annotations
import argparse
import os
import shlex
from pathlib import Path


def load_env(path:Path):
    for lineno,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'): continue
        if '=' not in line: raise ValueError(f'环境文件第{lineno}行缺少等号')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not key.replace('_','').isalnum(): raise ValueError('无效环境变量名称')
        if value[:1] in ('"',"'"):
            parts=shlex.split(value,comments=True)
            value=parts[0] if len(parts)==1 else ''
        os.environ[key]=value


def main():
    p=argparse.ArgumentParser();p.add_argument('service',choices=['public','brain']);p.add_argument('--env',type=Path)
    a=p.parse_args()
    if a.env: load_env(a.env)
    import uvicorn
    if a.service=='public':
        from .public_api import from_env
        from . import DEFAULT_PUBLIC_PORT
        app=from_env();host=os.environ.get('PUBLIC_HOST','127.0.0.1');port=int(os.environ.get('PUBLIC_PORT',str(DEFAULT_PUBLIC_PORT)))
    else:
        from .brain_api import from_env
        app=from_env();host=os.environ.get('BRAIN_HOST','127.0.0.1');port=int(os.environ.get('BRAIN_PORT','9101'))
    uvicorn.run(app,host=host,port=port,access_log=False)

if __name__=='__main__': main()
