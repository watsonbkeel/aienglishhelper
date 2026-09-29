from __future__ import annotations
import argparse
import json
from pathlib import Path
from .dictionary import Dictionary
from .store import Store
from .provision import provision
from . import DEFAULT_PUBLIC_PORT


def main():
    p=argparse.ArgumentParser(description='老师本机/服务器上的初始化与学生配置工具')
    p.add_argument('--dictionary',type=Path,default=Path('data/dictionary.json'))
    p.add_argument('--database',type=Path,default=Path('var/class.sqlite3'))
    s=p.add_subparsers(dest='command',required=True)
    s.add_parser('init')
    add=s.add_parser('add-student')
    add.add_argument('--id',required=True);add.add_argument('--port',type=int,required=True);add.add_argument('--output',type=Path,required=True)
    add.add_argument('--public-url',default=f'http://127.0.0.1:{DEFAULT_PUBLIC_PORT}')
    add.add_argument('--external-api-url',required=True);add.add_argument('--brain-url',required=True)
    a=p.parse_args()
    store=Store(a.database,Dictionary(a.dictionary))
    if a.command=='init': print(json.dumps({'ok':True,'dictionary_count':len(store.dictionary.rows),'database':str(store.path)}))
    else:
        print(json.dumps(provision(store,a.id,a.port,a.output,a.public_url,a.external_api_url,a.brain_url),ensure_ascii=False))

if __name__=='__main__': main()
