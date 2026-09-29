#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from english_class.sources import merge_miniprogram
p=argparse.ArgumentParser(description='非破坏性地把两页英语陪练合入原WordMaster_SZ副本')
p.add_argument('--source',type=Path,required=True,help='原项目中有app.json的目录')
p.add_argument('--output',type=Path,required=True,help='全新输出目录，不覆盖原项目')
p.add_argument('--connection',type=Path,help='本生生成的english-env.local.js')
a=p.parse_args()
try:
    merge_miniprogram(a.source,ROOT/'miniprogram',a.output)
    if a.connection: shutil.copy2(a.connection,a.output/'utils'/'english-env.local.js')
    print('已生成：'+str(a.output.resolve())+'；原项目未修改。')
except Exception as e: print(str(e),file=sys.stderr);raise SystemExit(1)
