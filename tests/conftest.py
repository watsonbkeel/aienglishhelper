import json
from pathlib import Path
import pytest

@pytest.fixture
def dictionary_path(tmp_path):
    rows = [
        {'word_id':'1a_021','grade':1,'semester':1,'word':'apple','meaning':'苹果'},
        {'word_id':'1a_022','grade':1,'semester':1,'word':'banana','meaning':'香蕉'},
        {'word_id':'1a_017','grade':1,'semester':1,'word':'bag','meaning':'书包'},
        {'word_id':'1b_001','grade':1,'semester':2,'word':'cat','meaning':'猫'},
        {'word_id':'7a_001','grade':7,'semester':1,'word':'background','meaning':'背景'},
        {'word_id':'12b_001','grade':12,'semester':2,'word':'announce','meaning':'宣布；通告'},
    ]
    p=tmp_path/'dictionary.json'; p.write_text(json.dumps(rows,ensure_ascii=False))
    return p

@pytest.fixture
def db(tmp_path, dictionary_path):
    from english_class.store import Store
    from english_class.dictionary import Dictionary
    return Store(tmp_path/'state.sqlite3', Dictionary(dictionary_path), timezone='Asia/Shanghai')

@pytest.fixture
def app(db):
    from english_class.public_api import create_app
    db.add_student('s001','Parent_A_very_long_token','Brain_A_very_long_token')
    db.add_student('s002','Parent_B_very_long_token','Brain_B_very_long_token')
    return create_app(db)

@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c: yield c

def headers(role='parent', student='A'):
    return {'Authorization':f'Bearer {role.title()}_{student}_very_long_token'}
