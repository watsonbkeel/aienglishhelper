"""Single public SQLite owner; student applications never open this database."""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .dictionary import Dictionary
from .models import LearningConfig

class Conflict(ValueError):
    pass

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

class Store:
    def __init__(self, path: str | Path, dictionary: Dictionary, timezone: str = 'Asia/Shanghai'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dictionary = dictionary
        self.timezone = ZoneInfo(timezone)
        with self.connect() as con:
            con.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, config TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS credentials (hash TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id), role TEXT NOT NULL CHECK(role IN ('parent','brain')));
            CREATE TABLE IF NOT EXISTS progress (student_id TEXT NOT NULL REFERENCES students(id), word_id TEXT NOT NULL, status INTEGER NOT NULL DEFAULT 0 CHECK(status BETWEEN 0 AND 2), unclear_count INTEGER NOT NULL DEFAULT 0, last_practiced_date TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(student_id,word_id));
            CREATE TABLE IF NOT EXISTS student_llm (student_id TEXT PRIMARY KEY REFERENCES students(id), base_url TEXT NOT NULL, model TEXT NOT NULL, api_key TEXT NOT NULL, updated_at TEXT NOT NULL, last_status TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '', last_used_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS events (student_id TEXT NOT NULL REFERENCES students(id), event_key TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(student_id,event_key));
            ''')

    def connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=15000')
        return con

    def add_student(self, student_id: str, parent_token: str, brain_token: str):
        if not re.fullmatch(r'[a-z][a-z0-9_-]{1,31}', student_id):
            raise ValueError('学生ID使用2—32位小写字母、数字、下划线或短横线，首位为字母')
        if min(len(parent_token), len(brain_token)) < 16 or parent_token == brain_token:
            raise ValueError('parent/brain 必须使用不同的、至少16位随机凭证')
        g,s = sorted(self.dictionary.terms)[0]
        cfg = LearningConfig(grade=g, semester=s).model_dump_json()
        try:
            with self.connect() as con:
                con.execute('INSERT INTO students VALUES (?,?)', (student_id,cfg))
                con.executemany('INSERT INTO credentials VALUES (?,?,?)',[(token_hash(parent_token),student_id,'parent'),(token_hash(brain_token),student_id,'brain')])
        except sqlite3.IntegrityError as exc:
            raise ValueError('学生ID或凭证已经存在；未覆盖原有数据') from exc

    def authenticate(self, token: str):
        with self.connect() as con:
            row=con.execute('SELECT student_id,role FROM credentials WHERE hash=?',(token_hash(token),)).fetchone()
        return dict(row) if row else None

    def config(self, student_id: str) -> dict:
        with self.connect() as con:
            row=con.execute('SELECT config FROM students WHERE id=?',(student_id,)).fetchone()
        if row is None: raise ValueError('学生不存在')
        return LearningConfig.model_validate(json.loads(row['config'])).model_dump()

    def save_config(self, student_id: str, config: dict) -> dict:
        obj=LearningConfig.model_validate(config)
        self.dictionary.select(obj.grade,obj.semester,obj.unit)
        with self.connect() as con:
            cur=con.execute('UPDATE students SET config=? WHERE id=?',(obj.model_dump_json(),student_id))
            if not cur.rowcount: raise ValueError('学生不存在')
        return obj.model_dump()

    # 学生自带大模型。密钥只在服务端使用，接口永不回传明文。
    def llm(self, student_id: str) -> dict | None:
        with self.connect() as con:
            row=con.execute('SELECT * FROM student_llm WHERE student_id=?',(student_id,)).fetchone()
        return dict(row) if row else None

    def save_llm(self, student_id: str, base_url: str, model: str, api_key: str):
        now=datetime.now(self.timezone).isoformat(timespec='seconds')
        with self.connect() as con:
            con.execute('''INSERT INTO student_llm(student_id,base_url,model,api_key,updated_at,last_status,last_error,last_used_at) VALUES (?,?,?,?,?,'ok','',?)
            ON CONFLICT(student_id) DO UPDATE SET base_url=excluded.base_url,model=excluded.model,api_key=excluded.api_key,updated_at=excluded.updated_at,last_status='ok',last_error='',last_used_at=excluded.last_used_at''',
                        (student_id,base_url,model,api_key,now,now))

    def clear_llm(self, student_id: str):
        with self.connect() as con: con.execute('DELETE FROM student_llm WHERE student_id=?',(student_id,))

    def mark_llm(self, student_id: str, status: str, error: str = ''):
        now=datetime.now(self.timezone).isoformat(timespec='seconds')
        with self.connect() as con:
            con.execute('UPDATE student_llm SET last_status=?,last_error=?,last_used_at=? WHERE student_id=?',(status,error[:200],now,student_id))

    def today(self) -> str:
        return datetime.now(self.timezone).date().isoformat()

    def _decorate(self,row) -> dict:
        item=dict(row)
        item.pop('student_id',None);item.pop('updated_at',None)
        word=self.dictionary.by_id.get(item['word_id'],{})
        item.update(word=word.get('word',item['word_id']), meaning=word.get('meaning',''))
        return item

    def progress(self,student_id: str) -> dict:
        with self.connect() as con:
            rows=con.execute('SELECT * FROM progress WHERE student_id=? ORDER BY updated_at DESC, word_id',(student_id,)).fetchall()
        return {'today':self.today(),'words':[self._decorate(r) for r in rows]}

    def record(self,student_id: str,word_id: str,status: int | None,unclear: bool,event_key: str | None=None) -> dict:
        if word_id not in self.dictionary.by_id:
            raise ValueError('未知的词库word_id')
        if status is not None and (type(status) is not int or status not in (0,1,2)):
            raise ValueError('status只能为0/1/2/null')
        if type(unclear) is not bool or (unclear and status is not None):
            raise ValueError('没听清时不得更新状态')
        if event_key is not None and not 1<=len(event_key)<=128:
            raise ValueError('无效事件编号')
        fingerprint=hashlib.sha256(json.dumps([word_id,status,unclear]).encode()).hexdigest()
        now=datetime.now(self.timezone)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if event_key:
                prior=con.execute('SELECT fingerprint,result FROM events WHERE student_id=? AND event_key=?',(student_id,event_key)).fetchone()
                if prior:
                    if prior['fingerprint']!=fingerprint: raise Conflict('同一请求编号不能提交不同结果')
                    return json.loads(prior['result'])
            con.execute('''INSERT INTO progress(student_id,word_id,status,unclear_count,last_practiced_date,updated_at) VALUES (?,?,?,?,?,?)
            ON CONFLICT(student_id,word_id) DO UPDATE SET status=MAX(progress.status,excluded.status), unclear_count=progress.unclear_count+excluded.unclear_count,last_practiced_date=excluded.last_practiced_date,updated_at=excluded.updated_at''',
                        (student_id,word_id,status or 0,int(unclear),now.date().isoformat(),now.isoformat()))
            row=con.execute('SELECT * FROM progress WHERE student_id=? AND word_id=?',(student_id,word_id)).fetchone()
            result=self._decorate(row)
            if event_key: con.execute('INSERT INTO events VALUES (?,?,?,?)',(student_id,event_key,fingerprint,json.dumps(result,ensure_ascii=False)))
        return result
