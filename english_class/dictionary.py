"""Read the original WordMaster dictionary as data, never execute JavaScript."""
from __future__ import annotations
import json
import math
import re
from pathlib import Path
from typing import Any


def parse_source(source: str) -> list[dict[str, Any]]:
    text = source.lstrip('\ufeff').strip()
    if not text.startswith('['):
        match = re.search(r'\b(?:const|let|var)\s+fullDictionary\s*=\s*', text)
        if not match:
            raise ValueError('找不到 fullDictionary 数组；请使用原仓库的 utils/fullDictionary.js')
        text = text[match.end():]
    try:
        rows, _ = json.JSONDecoder().raw_decode(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError('词库数组不是合法JSON；程序不会执行JavaScript') from exc
    if not isinstance(rows, list) or not rows:
        raise ValueError('词库必须是非空数组')
    return rows


class Dictionary:
    GROUP_SIZE = 10

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise ValueError(f'正式词库不存在：{self.path}。先执行 scripts/prepare_sources.py 或导入原 fullDictionary.js；测试夹具不会作为正式词库。')
        self.rows = parse_source(self.path.read_text(encoding='utf-8'))
        self.by_id: dict[str, dict] = {}
        self.terms: dict[tuple[int, int], list[dict]] = {}
        for row in self.rows:
            if not isinstance(row, dict):
                raise ValueError('词库条目必须是对象')
            for key in ('word_id', 'word', 'meaning'):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f'词库缺少有效 {key}')
            if type(row.get('grade')) is not int or not 1 <= row['grade'] <= 12:
                raise ValueError(f"无效年级：{row['word_id']}")
            if type(row.get('semester')) is not int or row['semester'] not in (1, 2):
                raise ValueError(f"无效学期：{row['word_id']}")
            if row['word_id'] in self.by_id:
                raise ValueError(f"重复 word_id：{row['word_id']}")
            self.by_id[row['word_id']] = row
            self.terms.setdefault((row['grade'], row['semester']), []).append(row)

    def select(self, grade: int, semester: int, unit: int = 0) -> list[dict]:
        rows = self.terms.get((grade, semester))
        if not rows:
            raise ValueError('原词库中没有这个年级/学期')
        if unit < 0 or unit > math.ceil(len(rows) / self.GROUP_SIZE):
            raise ValueError('不存在这个词库练习组；分组不是教材单元')
        chosen = rows if unit == 0 else rows[(unit-1)*self.GROUP_SIZE:unit*self.GROUP_SIZE]
        return [{k: r[k] for k in ('word_id', 'word', 'meaning')} for r in chosen]

    def catalogue(self, grade: int, semester: int, unit: int = 0) -> dict:
        words = self.select(grade, semester, unit)
        total = len(self.terms[(grade, semester)])
        groups = [{'value': 0, 'label': '本学期全部词汇', 'count': total}]
        for i in range(math.ceil(total/self.GROUP_SIZE)):
            groups.append({'value': i+1, 'label': f'词库练习组 {i+1}（非教材单元）',
                           'count': min(self.GROUP_SIZE, total-i*self.GROUP_SIZE)})
        return {'words': words, 'units': groups, 'unit_kind': 'ordered_group_not_textbook',
                'available_terms': [{'grade':g, 'semester':s} for g,s in sorted(self.terms)],
                'source': 'watsonbkeel/WordMaster_SZ / utils/fullDictionary.js'}
