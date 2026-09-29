# 接口约定 v0.1.0

所有学习数据接口必须提供查询参数 `student_id` 和 `Authorization: Bearer <课堂凭证>`。公共服务核验凭证绑定的学生，返回错误时不继续操作。

公共数据只有三个路径。词表与进度返回少量展示字段，避免小程序重新复制整个词库。

## GET /api/words

查询：`student_id=s001&grade=1&semester=1&unit=0`。grade1—12（1—6小学，7—9初中，10—12高中）；semester1/2；unit0全学期，unit正整数原词库顺序每10词一组。

返回 `words:[{word_id,word,meaning}]`、`units:[{value,label,count}]`、`available_terms`、`unit_kind:"ordered_group_not_textbook"`、`source`。非法范围422，不擅自回退到其他学期。只读，两个角色都可调用。

## GET /api/config / PUT /api/config

同一学生的parent与brain角色可以读写。PUT正文：

```json
{"grade":1,"semester":1,"unit":0,"duration_minutes":10,"practice_words":3,"chinese_help":true,"difficulty":"basic"}
```

时长5/10/15/20/30；practice_words每轮练几个词1—10（旧配置读出时补默认3）；难度basic/standard/challenge；不接受额外字段。配置下一轮生效。返回实际保存值。

大模型陪练口吻按grade自动切换：1—6小学（短句、具体、多鼓励）、7—9初中（自然句子，给出生活/学校场景）、10—12高中（更完整表达，可带观点与理由）。

## GET /api/llm / PUT /api/llm / DELETE /api/llm

仅parent角色（小程序家长凭证）可用，brain/edge角色返回403。学生可填自己的大模型；填了优先用学生自己的，平台DeepSeek作为备选。

GET返回二选一：

```json
{"mode":"platform","platform_model":"deepseek-flash"}
{"mode":"custom","base_url":"https://api.example.com/v1","model":"xxx","key_hint":"sk-…abcd","last_status":"ok","last_error":null,"last_used_at":"...","platform_model":"deepseek-flash"}
```

密钥永不回传，只给掩码key_hint。

PUT正文：`{"base_url":"https://…/v1","model":"模型ID","api_key":"sk-…"}`。base_url为OpenAI兼容API根地址（末尾多写的`/chat/completions`会被去掉）；已保存过时api_key可传null沿用旧密钥，新密钥至少8字符；base_url与已保存地址不同时必须同时提供新api_key，否则422（旧密钥不会发往新地址）。保存前用课程判题格式（系统提示+JSON数据，要求回复含布尔字段correct的JSON对象）做一次真实测试调用，限时20秒；失败、超时或格式不符返回422「…未保存：…」，原设置不变。小程序保存请求超时30秒，其余请求15秒。

地址安全限制：只允许https；不允许用户名密码、查询串、锚点；IP或域名解析结果必须全部是公网地址（拒绝本机、内网、链路本地等，返回422「接口地址不能指向内网或本机」）；不跟随重定向。

DELETE清除学生设置，改回平台模型。

## GET /api/progress / POST /api/progress

GET两个角色可用，返回：

```json
{"today":"2026-09-29","words":[{"word_id":"1a_021","word":"apple","meaning":"苹果","status":1,"unclear_count":0,"last_practiced_date":"2026-09-29","valid_count":2,"used_word_count":2,"imitated_count":1}]}
```

例子只说明字段，不是包内预置的学习记录。未返回的词视为状态0、次数0、未练。

POST仅brain角色可用：`{"word_id":"...","status":1,"unclear":false,"evidence":{"answer_valid":true,"used_word":true,"imitated":false}}`。evidence可省略（旧格式兼容）；unclear=true时不能带evidence。三项为true时分别累加valid_count（回答有效）、used_word_count（说出目标词，含词形变化）、imitated_count（紧跟在老师明确示范/跟读之后说出，不算独立会说）。这三列为增量新增列，旧库启动时自动ALTER补列，默认0，不改动已有进度。

status0/1/2/null；保存历史最大档。unclear=true必须status=null，增加累计没听清次数但不降级。status=null且unclear=false记录尝试日期，不升级。仅实际练到的词写入。日期按公共服务CLASS_TIMEZONE生成。

脑端提供 `Idempotency-Key`（最多128字符）；同学生同编号同数据返回第一次结果，不重复计次；同编号不同内容409。新一轮新问题使用新编号；这是请求防重复，不是离线补偿系统。

0已练过显示“继续练习”，0从未练过显示“没练过”；1听懂了，2会说了。状态是本练习确认的历史水平，不是长期记忆评价。

## 内部能力（学生调用封装，不公开给小程序）

`POST /internal/chat`、`/internal/asr?language=en|zh`、`/internal/tts` 需要brain角色和自己的student_id。仅服务器本机访问，不在Nginx中公开。

模型入参messages与json_output；有学生自带模型时先调它，调用失败或json_output时返回非JSON，就记录last_status=fallback与错误原因并改用平台模型；响应含`provider`（custom/platform）。ASR输入原始16kHz单声道16位PCM WAV，返回text/confidence/null/unclear/provider；provider为vosk、http、gate（静音或噪声被拦截，text为空、unclear=true）或vosk-fallback（云端失败改用本机）；TTS输入segments[{text,language}]和slow，输出WAV。真供应商密钥只在公共服务。

## 树莓派到本人脑端

树莓派使用独立 EDGE_TOKEN，不是公共层的 BRAIN_TOKEN。

- `POST /voice/turn`：`{request_id,action,text,confidence?,unclear?}`。action为start/answer/stop/pause/resume/repeat/slow/help/tick/played。answer文本只有在识别清楚（非unclear且confidence缺省或≥0.65）时才会被当作口令（停止/暂停/重复等）解析。text可空；request_id8—128字符。相同请求复用编号避免重复处理，不能复用编号发新回答。
- `POST /voice/audio?request_id=...`：原始WAV，request_id8—80字符、最大1MB。根据当前题目选择识别语言；识别与推进在同一个串行锁内完成。
- `POST /voice/speech`：`{segments:[{text,language}],slow:false}`，返回WAV。将已生成文本合成为语音，不再次更新学习记录。

/voice/turn和/voice/audio返回 `ok/active/phase/session_id/expected_language/segments/slow/word_index/word_count/request_id`；audio另有recognized_text。tick、played不算一次回答、不写进度。played由树莓派在一段语音播放完毕后上报，沉默计时从播放结束开始。树莓派空闲（未在处理、未在播放、队列为空）时每5秒发一次tick，服务端据此判断沉默：播放结束后20秒、40秒无人说话时返回简短重问（每题最多2次），3分钟无人说话时自动暂停（active=false）并保存断点；其余tick返回空segments。

断点：保存在大脑的systemd StateDirectory（`/var/lib/english-class-brain/<sid>/resume.json`，可用环境变量RESUME_STATE_PATH覆盖），内容为本批单词、当前位置和阶段（listen/recall）。下次start若断点7天内有效且学习配置未改，回复以“接着上次继续。”开头并从原位置继续；配置改变、过期、进入对话阶段或整节课完成时断点清除。单词进度仍实时写入，不依赖断点。

`/voice/push` 是旧 aibot 文本桥兼容入口，亦需EDGE_TOKEN。主安装流程不依赖它；旧桥默认未发送这个凭证，需要显式使用附带patch工具，并配置可反向访问的AIBOT_BODY_URL。原中文语音识别并不会因改端口就获得英语识别能力，推荐使用新课程插件。

## 共同错误处理

401未认证，403越学生／角色权限，409编号或已有配置冲突，413录音太大，422字段／词库范围不合法，503实际模型／语音／公共服务无法完成。UI应区分“没记录”和“没有读到服务”。不要把失败显示为成功或0分。
