#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from english_class.sources import fetch_bytes,extract_archive
p=argparse.ArgumentParser(description='下载Vosk语言模型；文件较大，不包含在代码包中')
p.add_argument('--dest',type=Path,default=ROOT/'models');p.add_argument('--language',choices=['en','zh','both'],default='both')
a=p.parse_args();a.dest.mkdir(parents=True,exist_ok=True)
models={'en':'vosk-model-small-en-us-0.15','zh':'vosk-model-small-cn-0.22'}
try:
    for language,name in models.items():
        if a.language not in ('both',language): continue
        target=a.dest/name
        if target.is_dir(): print('已存在，保留：',target);continue
        stage=a.dest/(name+'-extract')
        print('正在下载：',name,flush=True)
        data=fetch_bytes('https://alphacephei.com/vosk/models/'+name+'.zip')
        extract_archive(data,stage)
        src=stage/name
        if not src.is_dir() or not (src/'am'/'final.mdl').is_file(): raise ValueError('下载的模型结构不正确')
        src.rename(target);stage.rmdir();print('完成：',target)
except Exception as e: print(str(e),file=sys.stderr);raise SystemExit(1)
