#!/usr/bin/env python3
"""Optional original-bridge adapter; the course voice addon does NOT need this."""
import argparse,ast,datetime,shutil
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('file',type=Path);a=p.parse_args()
s=a.file.read_text(encoding='utf-8')
if 'ENGLISH_EDGE_TOKEN' in s: raise SystemExit('已有英语凭证适配，未重复修改')
anchor='            request.add_header("Content-Type", "application/json")'
if s.count(anchor)!=1: raise SystemExit('文件结构与锁定aibot版本不一致，未修改；请使用课程语音插件')
s=s.replace(anchor,anchor+'\n            if os.environ.get("ENGLISH_EDGE_TOKEN"):\n                request.add_header("Authorization", "Bearer " + os.environ["ENGLISH_EDGE_TOKEN"])')
s=s.replace('def push_to_brain(data: dict[str, Any], timeout: float = 5)', 'def push_to_brain(data: dict[str, Any], timeout: float = 90)')
ast.parse(s)
backup=a.file.with_name(a.file.name+'.before-english-'+datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
shutil.copy2(a.file,backup);a.file.write_text(s,encoding='utf-8')
print('已备份到',backup,'；配置ENGLISH_EDGE_TOKEN与BRAIN_CALLBACK_PORT后由你手动重启nox-bridge。')
