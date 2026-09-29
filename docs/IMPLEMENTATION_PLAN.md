# English Class Implementation Plan
**Goal:** 可部署的公共层、独立学生脑端、Pi语音插件、小程序两页与课程资料。
**Architecture:** 独立安装包，不改生产aibot。公共FastAPI+SQLite、每生FastAPI脑端、出站Pi客户端、原生小程序。
**Tech Stack:** Python 3.11+, FastAPI/Pydantic/httpx, SQLite, Vosk/Edge-TTS, WXML/WXSS/JS.
**Spec:** DESIGN.md
## Global constraints
不含真实密钥；不混同跟读和主动表达；不混同没听清和答错；不覆盖其他学生记录；不伪造教材单元。
## Review focus
跨学生读写；重复提交；中文/英文短词；页面失败态；真实外部服务失败不能伪造成功。
## Tasks
- [x] 1. tests/test_core.py -> dictionary.py/models.py/store.py/public_api.py：先红后绿；验证原词库解析、分组、权限、进度单调、日期、幂等。
- [x] 2. tests/test_engine.py -> engine.py/providers.py/brain_api.py：先红后绿；验证完整学习主线、跟读/没听清/暂停/超时。
- [x] 3. tests/test_tools.py/tests_js -> cli.py、安装器、Pi、页面；验证配置生成、无破坏合并和页面状态逻辑。
- [x] 4. 运行全套pytest、node测试、编译、shell语法、真实HTTP本地集成；记录外部服务未测范围。
- [x] 5. 生成中文操作文档；ZIP/TAR及账号Library保存状态以交付清单和对话中的实际工具结果为准。
