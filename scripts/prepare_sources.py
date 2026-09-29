#!/usr/bin/env python3
"""Import the original open dictionary, optionally download pinned full repositories."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from english_class.sources import import_dictionary, download_upstreams


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dictionary',type=Path,help='直接使用已有原版utils/fullDictionary.js，无需联网')
    p.add_argument('--destination',type=Path,default=ROOT/'data')
    p.add_argument('--all',action='store_true',help='同时下载两个锁定提交的完整原仓库用于对照或合并')
    a=p.parse_args()
    try:
        result=import_dictionary(a.destination,a.dictionary)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if a.all: download_upstreams(ROOT/'sources')
    except Exception as exc:
        print(str(exc),file=sys.stderr);return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
