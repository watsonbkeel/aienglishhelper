"""Small, shared API contracts. Extra fields are rejected to catch classroom bugs."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class LearningConfig(StrictModel):
    grade: StrictInt = Field(default=1, ge=1, le=12)
    semester: StrictInt = Field(default=1, ge=1, le=2)
    unit: StrictInt = Field(default=0, ge=0, le=2000)
    duration_minutes: Literal[5, 10, 15, 20, 30] = 10
    practice_words: StrictInt = Field(default=3, ge=1, le=10)
    chinese_help: StrictBool = True
    difficulty: Literal['basic', 'standard', 'challenge'] = 'basic'

class LlmSettings(StrictModel):
    base_url: str = Field(min_length=8, max_length=300)
    model: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:/@+-]+$')
    api_key: str | None = Field(default=None, max_length=400)

class Evidence(StrictModel):
    """一次练习的附加证据；可选，旧客户端不传也可以。"""
    answer_valid: StrictBool = False
    used_word: StrictBool = False
    imitated: StrictBool = False

class ProgressUpdate(StrictModel):
    word_id: str = Field(min_length=1, max_length=128)
    status: StrictInt | None = Field(default=None, ge=0, le=2)
    unclear: StrictBool = False
    evidence: Evidence | None = None

    @model_validator(mode='after')
    def check_unclear(self):
        if self.unclear and self.status is not None:
            raise ValueError('没听清时 status 必须为 null，不得改变学习状态')
        if self.unclear and self.evidence and any(self.evidence.model_dump().values()):
            raise ValueError('没听清时不得记录回答证据')
        return self

class ChatMessage(StrictModel):
    role: Literal['system', 'user', 'assistant']
    content: str = Field(max_length=24000)

class ChatInput(StrictModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    json_output: bool = False

class Segment(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    language: Literal['zh', 'en'] = 'en'

class SpeechInput(StrictModel):
    segments: list[Segment] = Field(min_length=1, max_length=8)
    slow: bool = False

class TurnInput(StrictModel):
    text: str = Field(default='', max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    unclear: bool = False
    request_id: str = Field(min_length=8, max_length=128)
    action: Literal['answer', 'start', 'stop', 'pause', 'resume', 'repeat', 'slow', 'help', 'tick', 'played'] = 'answer'
