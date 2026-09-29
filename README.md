# 英语听说陪练课程作品 · v0.1.0

覆盖 1—12 年级（小学、初中、高中），树莓派 4B + USB 耳麦，沿用 aibot 的「身体／云端脑端」分工，并接入 WordMaster_SZ 原词库。

**先读 [安装部署说明](docs/INSTALL.md)。** 这是可运行的课程扩展代码与老师参考实现，不是已经在你的树莓派、真实AI接口和微信手机端验收过的成品。

## 这一包提供什么

- `english_class/`：老师公共服务、每学生独立脑端、原词库导入、配置、学习记录、AI/ASR/TTS 适配。
- `pi/`：英语课程语音插件；本地中文唤醒／控制，英语录音发到本人的脑端，主动请求语音播放。无需云端反向连接树莓派。
- `miniprogram/`：可独立导入微信开发者工具的两个完整页面，也可非破坏性合入原 WordMaster_SZ。
- `scripts/`、`deploy/`：安装、创建学生、模型下载、原项目合并、课程模式切换、systemd 和 Nginx 配置例子。
- `tests/`、`tests_js/`：自动化测试；测试数据不作为运行时词库。
- `course/`：六次课的参考实现拆解。老师可用本实现验证基础，再让学生制作自己的版本。

## 明确边界

代码包不含供应商密钥、预置学生凭证、Vosk 模型权重，也**没有内嵌两个完整上游仓库和完整原词库**。首次安装从用户仓库的锁定提交导入词库并核验 Git blob 摘要；已有 `utils/fullDictionary.js` 时可直接本地导入，不依赖 GitHub。原仓库始终不被安装器覆盖。

原词库没有教材单元字段。本版直接使用原年级、学期、词义和 word_id：`unit=0` 为整个学期，正整数为原顺序每 10 个词的练习组，页面明确注明「不是教材单元」。不生成新的教材词库、不猜教材归属。

学生主线：听词说意思 → 主动说词 → 一个简短情境 → 结果写回。跟读不算独立会说，没听清不算不会；状态表示在本工具中已达到的历史最高档，不是永不遗忘的掌握证明。听写、摄像头、额外入口不属于本版必做实现。

## 快速检查源代码

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
PATH="$PWD/.venv/bin:$PATH" bash scripts/test_all.sh
```

完整检查还需要 Node.js（推荐 22）和 ffmpeg；其中 HTTP 语音集成测试会实际调用 ffmpeg。部署到机器之前请阅读 [测试报告](docs/TEST_REPORT.md)。

文档：
[安装](docs/INSTALL.md) · [接口](docs/API.md) · [结构与扩展](docs/CODE_MAP.md) · [六次课程](course/SIX_LESSONS.md) · [来源](docs/SOURCES.md)
