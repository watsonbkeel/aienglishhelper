# 安装部署说明
## 英语听说陪练课程作品 v0.1.0

这份说明按「服务器 → 文字测试 → 小程序 → 树莓派 → 完整演示」推进。先跑通一个学生，再增加其他学生。不需要先让全班同时安装。

> 安装器使用独立目录和服务，不覆盖 `/opt/asist-embodiment`，不修改原 aibot Git 仓库，也不向 GitHub 推送代码。只有你明确执行树莓派的 `course_mode.py on`，才会暂停原 `nox-voice.service` 对麦克风的占用；`off` 恢复切换前状态。

## 1. 文件与运行位置

| 内容 | 放在哪里 | 谁维护 |
|---|---|---|
| 公共数据与模型／语音适配 | 云服务器 `/opt/english-class` | 老师 |
| 真实供应商凭证 | `/etc/english-class/public.env` | 只给老师 |
| 学习数据库 | `/var/lib/english-class/class.sqlite3` | 公共服务 |
| 每位学生的脑端代码 | `/opt/english-class/students/s001` 等 | 学生修改自己的副本，由老师部署 |
| 学生脑端配置 | `/etc/english-class/students/s001.env` | 老师 |
| 树莓派课程插件 | 树莓派 `/opt/english-class-edge` | 每位学生自己的终端 |
| 小程序页面 | 解压后的 `miniprogram`，或合并后的新目录 | 每位学生自己的本地工程 |

自动安装器面向 Debian 12+/Ubuntu 24.04+ 和 64 位 Raspberry Pi OS（Python 3.11+）。其他 Linux 请参考第 11 节手工运行方式。自动安装需要能下载系统包、Python 依赖及所选语音模型。

老师的机器和每位学生的终端需要能访问所配置的服务。第一次验证可以全部在服务器回环地址运行，不必立即开放公网端口。真实微信手机预览建议使用已有的 HTTPS 域名和合法证书。

## 2. 原词库：直接使用，不重新创建

本代码包没有内嵌整个上游仓库／完整词库；默认导入目标固定为：

```text
仓库：watsonbkeel/WordMaster_SZ
提交：4701d5bc72097c8851b180bf6025fb8b9db12ae4
文件：utils/fullDictionary.js
Git blob：ea9b65ea1c1ae6e4b871bbd27f8d46796097d8cc
```

联网导入会核验原文件 blob 摘要，不接收 HTML 错误页或悄悄替换成示例词表。`data/dictionary-source.json` 记录实际来源、词条数和摘要。导入保留原 `word_id`、年级、学期、词义和其他字段；首版接口仅开放小学 1—6 年级。

你已经有原项目时，推荐先直接用现有文件：

```bash
# 在解压后的 english-class-assistant 目录执行
python3 scripts/prepare_sources.py \
  --dictionary /你的实际路径/WordMaster_SZ/utils/fullDictionary.js
```

本地导入会校验结构和唯一 ID，接受你自己后续修改的词库版本，记录实际摘要而不冒称它是锁定提交。没有本地文件时运行：

```bash
python3 scripts/prepare_sources.py
```

输出包含 `records`、`elementary_records` 和实际来源后才算导入成功。文件会保存在 `data/`，不会执行词库中的 JavaScript。

原词库没有教材单元字段，所以配置页提供「整个学期」和「练习组」：每组按原顺序最多 10 个词。它们不是教材第几单元。`unit` 字段保留用于接口兼容，但页面没有伪称课本单元。

## 3. 云服务器：第一次安装公共层

将完整代码包上传服务器并解压。以下目录以解压后得到的 `english-class-assistant` 为例；命令中的 `/你的实际路径/` 必须换成真实路径。

```bash
cd /你的实际路径/english-class-assistant

# 已有原词库：
sudo bash scripts/install_server.sh \
  --dictionary /你的实际路径/WordMaster_SZ/utils/fullDictionary.js

# 或者没有本地原词库，允许安装时自动从锁定提交下载：
# sudo bash scripts/install_server.sh
```

安装器会创建独立虚拟环境、公共服务用户、数据库和两个服务定义，不安装 Nginx、不改你现有网站配置。

完成后检查：

```bash
sudo systemctl status english-public --no-pager
curl -fsS http://127.0.0.1:18090/health
```

`ok: true` 只说明公共数据服务启动、数据库可访问、词库已载入，**不说明真实大模型、语音识别或朗读已经通过测试**。

安装器只用于第一次安装。发现 `/opt/english-class` 已存在会停止，不覆盖已有修改。若安装中途失败，先看具体错误和第 12 节，不要直接删除已有学习数据库。

## 4. 老师配置模型、识别与朗读

编辑公共层配置：

```bash
sudo nano /etc/english-class/public.env
```

### 4.1 大模型

填写你实际使用的接口地址、模型 ID 和密钥：

```ini
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=在服务器本地填写你的真实密钥
```

这里的模型名是适配器默认值。使用你现有的 DeepSeek v4.1 Flash 中转或其他供应商时，改成**该服务实际接受的模型 ID**，不要把产品显示名称当成接口 ID。`LLM_BASE_URL` 填到 API 根地址（中转通常包含 `/v1`）；程序追加 `/chat/completions`，不能把完整 endpoint 再填进去。

程序明确发送 `thinking: {"type":"disabled"}`，不发送 `reasoning_effort`；使用 JSON 输出安排和判断当前练习。所配置接口必须支持这种请求格式。真实密钥不能写入学生源码、小程序或者公开 Git 仓库。

这里配置的是**平台模型**。学生也可以在小程序「大模型（可选）」卡片里填自己的 OpenAI 兼容接口：保存前会先测试调用，成功才保存；之后优先用学生自己的，失败自动退回平台模型。学生密钥只存在服务器 SQLite 的 `student_llm` 表，不回传给小程序，只显示掩码。接口只允许公网 https 地址。

### 4.2 语音识别：默认 Vosk，也可以接你已验证的兼容转写服务

默认公共层使用 Vosk 中英两套模型，树莓派本地只用中文模型做唤醒和控制。先下载到公共服务器：

```bash
cd /opt/english-class
sudo .venv/bin/python scripts/download_models.py \
  --language both --dest /opt/english-class/models
```

默认配置：

```ini
ASR_BACKEND=vosk
VOSK_EN_PATH=/opt/english-class/models/vosk-model-small-en-us-0.15
VOSK_ZH_PATH=/opt/english-class/models/vosk-model-small-cn-0.22
```

当前线上英文识别已换成更大的 `vosk-model-en-us-0.22-lgraph`（约465MB，公共服务常驻内存约470MB）：12个测试词/短语全对，每句约3秒；小模型0.56秒但会把 announce 听成 an ounce。完整版 `vosk-model-en-us-0.22`（约6GB内存）在8GB服务器上会被系统杀掉，不要使用。切换方法：解压到 `/opt/english-class/models/`，改 `VOSK_EN_PATH` 后重启 `english-public`。

已经有模型目录时可自行复制到这些位置，或修改路径。模型目录要让 `english-public` 用户能够读取；不要指向该用户无法访问的 `/root/` 目录。

**Vosk 是可运行的默认接入，不是儿童英语识别效果承诺。**开课前一定用真实学生测试。你已有更合适的语音转写服务时，可以改为兼容 HTTP 模式：

```ini
ASR_BACKEND=http
ASR_BASE_URL=https://你的语音服务实际API根地址/v1
ASR_MODEL=该服务实际转写模型ID
ASR_API_KEY=仅在服务器填写
```

**当前线上配置（2026-09-30 起）**：香港 GPU 服务器网络故障，改用腾讯云一句话识别（`SentenceRecognition`，英文引擎 `16k_en`、中文 `16k_zh`），课程服务器实测每句 0.11–0.16 秒，8 个测试词句全对；本机 Vosk 小模型只做兜底。

```ini
ASR_BACKEND=tencent
TENCENT_SECRET_ID=AKID…（仅在服务器填写）
TENCENT_SECRET_KEY=仅在服务器填写
ASR_FALLBACK=vosk
ASR_TIMEOUT=3
ASR_RETRY_AFTER=60
ASR_MIN_RMS=200
VOSK_EN_PATH=/opt/english-class/models/vosk-model-small-en-us-0.15
```

- 需要在腾讯云控制台开通「语音识别」；按调用量计费（有每月免费额度，超出后付费或购买资源包），欠费或额度耗尽时本轮自动改用本机 Vosk。
- 建议用只授权语音识别（QcloudASRFullAccess）的子账号密钥，不用主账号密钥。
- 静音/噪声仍先经 `ASR_MIN_RMS` 拦截，不送腾讯云、不计费。学生录音会传到腾讯云转文字。
- 香港 Qwen3-ASR 恢复后想切回：`ASR_BACKEND=http`，其余 `ASR_BASE_URL`/`ASR_MODEL`/`ASR_LANGUAGE_MAP` 保留原值即可。

**此前配置（2026-09-29）**：英文和中文识别都走香港 GPU 服务器上的 Qwen3-ASR（`http://<香港ASR的Tailscale地址>:3102/v1`，仅 Tailscale 内网，无公网），每句约 0.2 秒；本机 Vosk 小模型只做兜底。

```ini
ASR_BACKEND=http
ASR_BASE_URL=http://<香港ASR的Tailscale地址>:3102/v1
ASR_MODEL=Qwen/Qwen3-ASR-1.7B
ASR_API_KEY=
ASR_LANGUAGE_MAP=en:English,zh:Chinese
ASR_FALLBACK=vosk
ASR_TIMEOUT=3
ASR_RETRY_AFTER=60
ASR_MIN_RMS=200
VOSK_EN_PATH=/opt/english-class/models/vosk-model-small-en-us-0.15
```

- 该服务的 language 必须是 `English`/`Chinese`，传 `en`/`zh` 会返回 502，所以要配 `ASR_LANGUAGE_MAP`。
- 云端模型对静音、持续噪声会编出 "Okay." "I'm sorry."；`ASR_MIN_RMS` 先判断有没有人声，没有就按"没听清"处理（不降级、不送云端）。
- 云端失败或超过 `ASR_TIMEOUT` 秒，本轮改用本机 Vosk，之后 `ASR_RETRY_AFTER` 秒内直接走本机，不让每轮都等超时。
- 服务不需要密钥时 `ASR_API_KEY` 留空即可。学生录音会传到香港服务器转文字。

该模式要求服务支持 `POST /audio/transcriptions`，multipart 上传 WAV，返回包含 `text` 的 JSON。不要把 DeepSeek 文本对话接口填到 ASR 地址，它并不是本适配器的录音转写接口。没有返回置信度的服务会保留 `confidence=null`，程序不伪造识别分数。

### 4.3 语音合成

默认延续原 aibot 使用的 Edge TTS 方式：

```ini
TTS_BACKEND=edge
TTS_VOICE_EN=en-US-JennyNeural
TTS_VOICE_ZH=zh-CN-XiaoxiaoNeural
```

网络或该通道不可用时，可以配置兼容 `POST /audio/speech` 的服务：

```ini
TTS_BACKEND=http
TTS_BASE_URL=https://你的语音合成服务实际API根地址/v1
TTS_MODEL=该服务实际模型ID
TTS_API_KEY=仅在服务器填写
TTS_VOICE=该服务支持的音色ID
```

默认 Edge 路径区分中英文音色；兼容 HTTP 路径使用所选通用音色，须支持中英朗读。公共层将音频统一为 WAV，树莓派用 `aplay` 播放。

填写完成后：

```bash
sudo systemctl restart english-public
sudo journalctl -u english-public -n 50 --no-pager
```

不要把包含凭证的完整配置文件、终端截图贴到公开群或仓库。

## 5. 创建第一个学生

### 5.1 有可用 HTTPS 域名

假设你已经有自己的域名与证书。下面的 `class.your-domain.tld` **只是占位示例，不是本项目提供的真实域名**：

```bash
cd /opt/english-class
sudo bash scripts/create_student.sh \
  s001 9101 \
  https://class.your-domain.tld \
  https://class.your-domain.tld/students/s001
```

创建结果：

```text
/opt/english-class/students/s001/       本人的脑端代码与提示词
/etc/english-class/students/s001.env  本人的服务配置
/root/english-class-students/s001/    导出给本人使用的连接文件
```

导出目录内有三个用途不同的配置：

| 文件 | 放到哪里 | 注意 |
|---|---|---|
| `brain.env` | 已自动安装到服务器学生配置目录 | 含本人脑端凭证，不放小程序 |
| `pi.env` | 只给本人的树莓派 | 含本人 EDGE_TOKEN |
| `english-env.local.js` | 本人小程序 `utils/` 目录 | 只含家长端课堂凭证，不能伪造进度写入 |

三个凭证由本地程序随机生成，交付源码没有预先设置大家共用的口令。自动安装的学生ID使用2—24位小写字母、数字、下划线或短横线，字母开头，避免带前缀后的Linux用户名超长。创建同名学生、已分配端口或已存在导出目录时会停止，不覆盖旧内容。

检查本人的脑端：

```bash
sudo systemctl status english-brain@s001 --no-pager
curl -fsS http://127.0.0.1:9101/health
```

### 5.2 只有服务器 IP，先做文字验证

不必先处理小程序手机预览。可以只在服务器本机创建和测试：

```bash
cd /opt/english-class
sudo bash scripts/create_student.sh \
  s001 9101 http://127.0.0.1:18090 http://127.0.0.1:9101
```

此处的 `127.0.0.1` 只对服务器自己有意义，**不能原样复制到家长手机或家里的树莓派后期待它连接云服务器**。

生成文件后执行第 6 节的文字测试。之后准备好域名，只需更改导出的 `pi.env` 的 `BRAIN_URL` 和小程序的 `baseUrl`，不必重新创建学生、更换凭证或清空进度。

### 5.3 反向代理

公共层与学生脑端默认只监听服务器的 `127.0.0.1`，不应直接向互联网开放 18090 或所有学生端口。

> 公共层默认端口为 **18090**（部署服务器上 18080 已被其他生产服务占用）。改端口只需改 `/etc/english-class/public.env` 的 `PUBLIC_PORT` 和 nginx `/api/` 的 `proxy_pass`；安装器和 `create_student.sh` 会从 `public.env` 读取该端口。

在你已经配置好证书的 Nginx HTTPS `server {}` 中，参照 `deploy/nginx-locations.conf.example` 加入：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:18090;
    proxy_set_header Host $host;
    proxy_read_timeout 120s;
}
location /students/s001/ {
    proxy_pass http://127.0.0.1:9101/;
    proxy_set_header Host $host;
    proxy_read_timeout 180s;
    client_max_body_size 2m;
}
location /internal/ { return 404; }
```

第一个 `proxy_pass` 保留 `/api/`；第二个结尾的 `/` 用于去掉 `/students/s001/` 前缀，这个差别不能省略。不要把老师的 `/internal/` 模型适配接口代理到公网。

检查后再重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

每增加一位学生，增加一个不同 `/students/s002/` 到对应端口的映射即可。若现有网站已经占用 `/api/`，使用独立子域名，避免覆盖原站路由。

## 6. 先做不依赖耳麦的文字测试

在服务器上复制本人的 Pi 连接文件作为**只用于服务器测试**的配置，不修改准备发给实际树莓派的原文件：

```bash
sudo cp /root/english-class-students/s001/pi.env \
  /root/english-class-students/s001/pi-local.env
sudo nano /root/english-class-students/s001/pi-local.env
```

在这份副本中改两行，其余凭证保持不变：

```ini
BRAIN_URL=http://127.0.0.1:9101
ALLOW_INSECURE_HTTP=1
```

运行：

```bash
cd /opt/english-class
sudo .venv/bin/python -m pi.english_voice \
  --env /root/english-class-students/s001/pi-local.env \
  --text --no-audio
```

依次输入：

```text
/start
（根据程序显示的英语词，输入真实中文意思）
（后续按提示输入英文单词）
（进入情境后，输入自己的回答）
/repeat
/stop
/quit
```

不要固定照抄 apple，因为你导入的年级词库可能先出现 hello、hi 或其他词。程序必须使用实际取出的词。

这一测试验证真实模型调用、练习控制与进度写入，不验证声音识别和播放。缺少模型密钥或上游异常时应显示错误，不会偷偷使用示例对话。

## 7. 在微信开发者工具中运行

### 7.1 最快测试：独立两个页面

把导出的 `english-env.local.js` 安全复制到你的电脑，再覆盖：

```text
english-class-assistant/miniprogram/utils/english-env.local.js
```

微信开发者工具选择「导入项目」，项目目录选择 `miniprogram`。使用你自己的合法 AppID 和已授权的开发微信号；包里的 `touristappid` 仅是避免冒用真实 AppID 的占位，不能替代真实手机预览所需条件。

配置小程序后台 `request` 合法域名为你的公共 HTTPS 域名。在正式手机网络条件下测试，不把开发者工具中临时关闭域名校验当成最终部署办法。

首次打开配置页会读取公共服务。也可以展开页面底部的「课堂连接设置」，输入公共服务根地址、学生 ID 和家长课堂凭证。地址只填根地址，不加 `/api/config`，也不填 `/students/s001`。

没有 `english-env.local.js` 时，小程序会读取仓库自带的 `utils/english-env.example.js`（全部为空），配置页显示「还没有连接课堂」提示并自动展开课堂连接设置，不会发出请求；测试和构建也不依赖本地文件。

自带大模型放在配置页最下方「高级设置」里，默认收起，单独保存；换接口地址时必须重新填写 API Key，保存前会按课程判题格式做一次 20 秒内的测试调用。

页面会把手动填写的连接保存在本地。之后更换 `english-env.local.js` 但页面仍连接旧账号时，修改课堂连接设置，或在开发者工具清除该小程序缓存。

测试：修改年级／学期／练习组 → 保存 → 在文字终端重新 `/start` → 检查新范围生效 → 完成几次练习 → 打开结果页刷新。

### 7.2 合入现有 WordMaster_SZ

你可以先测试独立两页，再生成包含原背词功能的新工程。原始目录不会被修改：

```bash
cd /你的实际路径/english-class-assistant
python3 scripts/build_miniprogram.py \
  --source /你的实际路径/WordMaster_SZ \
  --output /你的实际路径/WordMaster_SZ_EnglishClass_s001 \
  --connection /你的实际路径/s001/english-env.local.js
```

`--output` 必须是原项目以外的**全新目录**。工具保留原 `app.js`、原页面、词库和 tabBar，增加两个英语页面，并在原个人中心增加入口。新的启动页为英语配置页，页面也提供返回原小程序入口。

缺少原项目时，可另行从 GitHub 下载你的原仓库；也可运行 `python3 scripts/prepare_sources.py --all` 拉取本包锁定的两个上游仓库到 `sources/`，再以 `sources/WordMaster_SZ` 作为 `--source`。这一步需要 GitHub 网络，且不是服务器核心功能启动的必需步骤。

每个学生用自己本地工程、自己的配置文件预览。开发微信号要有开发所需权限；体验成员与开发权限不是同一回事。开课前用真实账号验证扫码流程。不要让所有学生反复覆盖唯一的正式发布版本；统一发布或体验版由老师最后选择／合并。

## 8. 树莓派安装与原 aibot 共存

将完整源码包和本人的 `pi.env` 复制到树莓派。默认不需要电脑对树莓派开入站端口，插件只主动访问本人的云端脑端。

### 8.1 先检查 USB 耳麦

```bash
arecord -l
aplay -l
```

尽量使用 ALSA 的稳定声卡名，而不是可能改变的数字序号。实际声卡 ID 以你的命令输出为准。例如显示 `CARD=Audio` 时，可在 `pi.env` 里填写：

```ini
CAPTURE_DEVICE=plughw:CARD=Audio,DEV=0
PLAYBACK_DEVICE=plughw:CARD=Audio,DEV=0
```

录音默认 `auto` 会寻找 USB 声卡；播放默认 `default` 不保证一定是 USB 耳机，首次测试建议明确设置。耳麦或实体静音键未开启时，软件不能替代检查。

### 8.2 安装插件

```bash
cd /你的实际路径/english-class-assistant
sudo bash scripts/install_pi.sh --env /你的实际路径/s001/pi.env
```

如果原 aibot 已有中文 Vosk 模型，可直接复用一份：

```bash
sudo bash scripts/install_pi.sh \
  --env /你的实际路径/s001/pi.env \
  --model /你的原中文模型目录/vosk-model-small-cn-0.22
```

模型目录要包含 `am/final.mdl`。安装器将模型复制到新目录，便于新服务读取，不移动原模型。

### 8.3 明确切换麦克风使用者

安装完成后不会自动抢麦克风。确认云端已经通过文字测试、Pi 地址和声卡配置正确，再执行：

```bash
sudo python3 /opt/english-class-edge/scripts/course_mode.py on
sudo journalctl -u english-edge -f
```

说：

> 小爱同学，开始今天的英语练习。

插件开启后进入课程模式，不提供原通用机器人的全部闲聊／外设功能。原 `nox-body`、`nox-bridge` 等服务和代码保持原样，但它们可能仍使用音频输出；测试时不要同时向原机器人发送播报请求。

恢复原机器人：

```bash
sudo python3 /opt/english-class-edge/scripts/course_mode.py off
```

该开关仅针对原项目标准名称 `nox-voice.service`。如果你在生产环境给语音服务改了名字，需要老师先手动确认实际麦克风进程，不能让两个录音循环同时抢设备。

### 8.4 实际语音规则

本地中文识别负责唤醒、暂停、结束、重复等控制；进入练习后，录音按当前轮次送到公共层的中文或英文识别器。默认“听词说意思”允许中文回答，所以该阶段预期中文；后续主动说词和情境预期英文。

播放器播报期间不把扬声器回声计为学生回答，结束后短暂留出保护时间再听。孩子要等机器人问完再回答；这是顺序听说，不是已经通过远场双向全双工认证的产品。USB 耳麦更适合先验证。中文唤醒词仍可用于打断播放，暂停／结束可用于结束当前活动。

没有可靠听清时，记录没听清并保留原题，同时简短重问当前词。跟读示范不直接升级为会说。

提示语按“每节课首次完整、之后精简”播报：开场白、第一道听词题（“这个英语词是什么意思？”）、第一道说词题（“……，用英语怎么说？”）、第一次没听清、第一次跟读都完整讲；之后只念词或中文意思，反馈缩成“对！”或“意思是……”。孩子说“再说一次”会重播当前题的完整问法（不重播开场白）。重新开始练习时恢复完整讲解。服务错误不伪造答对或假装已完成；播报失败时会提示说“再说一次”，重播当前题目，而不是重复提交上一道答案。

沉默与续学：同一题20秒没人说话会简短重问一次，40秒再问一次（每题最多2次）；3分钟都没人说话，播报“先休息一下。下次说‘开始英语练习’，接着学。”并暂停。孩子主动说“结束”也会保存进度。下次说“开始英语练习”时先说“接着上次继续。”，从同一批词、同一道题继续，并重新完整讲解一次。断点保存7天，存放在 `/var/lib/english-class-brain/<sid>/resume.json`（服务单元的 `StateDirectory`）；家长在小程序改了学习配置、进入对话阶段或整节课完成时断点自动作废。想让孩子从头开始，可删除该文件。

`MIC_GAIN`（0.25—8）和 `VAD_THRESHOLD`（50—10000）只用于麦克风输入和说话结束检测。默认值不能保证适合所有耳麦；先看真实录音和环境，再由老师小幅调整。不要让学生在课上临时调试识别引擎。

## 9. 增加其他学生与课堂开发方式

```bash
cd /opt/english-class
sudo bash scripts/create_student.sh \
  s002 9102 \
  https://class.your-domain.tld \
  https://class.your-domain.tld/students/s002
```

给 s002 加对应反向代理，把 s002 的连接文件只交给 s002，不复制 s001 的文件。公共服务器的模型密钥共用，但数据库权限按学生凭证检查，聊天状态按脑端进程分开。

安装器创建的是运行服务的无登录系统用户，不是面向学生的远程桌面或编程平台。学生可以在本机用 AI 修改脑端和小程序，老师将修改后的 `engine.py`、`prompts/student.md` 等部署到该学生目录，再重启对应服务：

```bash
sudo systemctl restart english-brain@s001
```

修改公共模板不会自动覆盖已经创建的每位学生副本，这样避免老师升级把学生作品抹掉。学生已有不同代码时应分别比较和合并。

注意：脑端服务实际运行的是 `/opt/english-class/students/<sid>/english_class/`（工作目录内的副本），只改 `/opt/english-class/english_class/` 不会生效。更新某个学生时，先备份其副本，再复制文件并 `chown english-<sid>`，最后重启 `english-brain@<sid>`。

建议学生优先修改：`engine.py`（陪练流程）、`prompts/student.md`（情境偏好）、两个小程序页面。公共数据库、凭证分配和模型服务先由老师维护。

## 10. 完整演示检查

先选择原词库确实有内容的年级和学期，使用整个学期或一个练习组。配置页保存后，重新开始一轮，观察选词和难度变化。

做几次正确回答、一次真正错误的回答、一次跟读帮助，再检查小程序记录。系统没听清时只增加累计次数，不把状态降低。跟读后的词不应因此从“听懂了”跳成“会说了”。

默认每轮最多选 3 个词，然后完成 4／6／8 次情境回应（对应三档），也受 5／10／15 分钟上限限制。**设置的是最长练习时间，不保证自动填满该分钟数**；完成小目标就可以提前结束。

状态按已达到的最高档保存，不是长期记忆曲线评估。现有背词进度不会自动换算为听说进度。下次优先选择当前范围中未达到状态 2 的词，再兼顾较早练习的词。

结果页显示“今天练过”与“当前状态”；累计没听清次数明确为累计，不能当成今天错题数。服务重启后，逐词保存的进度仍在；当前未完成会话不恢复，重新开始一轮即可。

## 11. 不使用系统安装器：手工运行

适合先在 Mac 或普通 Linux 本机验证文字与小程序接口。安装 Python 3.11+；测试语音转换需要 ffmpeg，只有 Vosk/Edge 路径才需要对应依赖。

```bash
cd /你的实际路径/english-class-assistant
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
python3 scripts/prepare_sources.py --dictionary /你的路径/WordMaster_SZ/utils/fullDictionary.js
.venv/bin/python -m english_class.cli init
.venv/bin/python -m english_class.cli add-student \
  --id s001 --port 9101 --output output/s001 \
  --external-api-url http://127.0.0.1:18090 \
  --brain-url http://127.0.0.1:9101
```

新建 `public-local.env`，不要直接复制服务器环境文件中的绝对路径：

```ini
DATABASE_PATH=var/class.sqlite3
DICTIONARY_PATH=data/dictionary.json
CLASS_TIMEZONE=Asia/Shanghai
PUBLIC_HOST=127.0.0.1
PUBLIC_PORT=18090
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=你的实际模型ID
LLM_API_KEY=在本机填写
ASR_BACKEND=vosk
VOSK_EN_PATH=models/vosk-model-small-en-us-0.15
VOSK_ZH_PATH=models/vosk-model-small-cn-0.22
TTS_BACKEND=edge
```

三个终端都先进入同一项目根目录，分别运行：

```bash
# 终端1：公共层
.venv/bin/python -m english_class.run public --env public-local.env

# 终端2：本人的脑端
.venv/bin/python -m english_class.run brain --env output/s001/brain.env

# 终端3：先编辑output/s001/pi.env，将ALLOW_INSECURE_HTTP设为1，仅回环测试
.venv/bin/python -m pi.english_voice --env output/s001/pi.env --text --no-audio
```

`--text --no-audio` 不需要安装 Vosk，也不需要真实耳麦，但仍需要真实文本模型。后来验证语音再安装 `requirements-voice.txt` 和模型文件。

在开发者工具模拟器中用本机 `http://127.0.0.1:18090` 调试时，需要临时启用本地 HTTP 测试：`english-env.local.js` 的 `allowHttpForLan: true`，并仅在本机开发阶段使用开发工具的域名调试选项。真实手机上的 localhost 是手机自身，正式预览仍应换成可达的 HTTPS 服务。

## 12. 排错、维护和恢复

| 现象 | 先检查 |
|---|---|
| 公共服务无法启动 | `journalctl -u english-public`；正式词库是否已导入；数据库路径是否可写 |
| 401 | 是否把家长、脑端、Pi 的凭证混用了；是否还在读取小程序旧缓存 |
| 403 | `student_id` 是否与凭证属于同一学生；家长凭证不能写进度或调模型 |
| 422 | 年级／学期是否有词；练习组是否存在；字段类型是否符合约定 |
| 503 / 模型错误 | 模型根地址、真实 ID、密钥、JSON 模式和关闭思考参数是否受支持 |
| 文字正常、语音识别失败 | 公共层 ASR 配置，模型目录权限，实际传入 WAV；不要只检查树莓派唤醒模型 |
| 听到“播报没有完成” | 公共层 TTS 通道、ffmpeg、Pi 的 `PLAYBACK_DEVICE` 和USB耳麦 |
| 手机请求失败 | HTTPS 证书、微信合法域名、开发权限、学生连接文件、代理路径 |
| 云端能访问、本地Pi失败 | `BRAIN_URL` 是否仍是127.0.0.1；HTTPS路径是否为本人的 `/students/s001` |
| 改代码不生效 | 是否改了公共模板而不是该学生目录；对应脑端服务是否重启 |
| 麦克风被占用 | 原语音服务名称是否为标准nox-voice；是否另开了arecord/其他录音程序 |

常用日志：

```bash
sudo journalctl -u english-public -n 80 --no-pager
sudo journalctl -u english-brain@s001 -n 80 --no-pager
# 在树莓派上：
sudo journalctl -u english-edge -n 80 --no-pager
```

升级前分别备份代码、配置和数据。数据库备份建议使用 Python sqlite3 的 backup API，而不是只复制一个正在写入的数据库文件：

```bash
# 服务器上以root执行；备份文件也按凭证文件保管
sudo /opt/english-class/.venv/bin/python - <<'PY'
import sqlite3, datetime, os
source='/var/lib/english-class/class.sqlite3'
backup='/root/english-class-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3'
with sqlite3.connect(source) as src, sqlite3.connect(backup) as dst:
    src.backup(dst)
os.chmod(backup,0o600)
print(backup)
PY
```

本安装器不做自动覆盖式升级。修订代码先放全新目录测试，确认后由老师逐份合并，保留学生已有提示词与页面，不删除 `/var/lib/english-class`。

只停止本项目服务器服务时，使用 `systemctl stop english-brain@s001 english-public`；不要停止原 aibot 的服务。树莓派退出课程模式用前述 `course_mode.py off`。

## 13. 交付验证边界

本包在当前开发环境完成 Python、JavaScript 逻辑测试、真实本地 HTTP 链路测试、测试音频 WAV/ffmpeg 转换检查、语法检查和压缩包完整性检查；具体命令与数量见 `TEST_REPORT.md`。

这里没有连接你的真实模型账号，没有在树莓派4B、真实儿童声音、USB耳麦、Nginx/systemd目标主机或微信开发者工具上实测。测试中用到的替身只存在 `tests/`，不会在运行服务失败时接管正式回答。

请把第 6、7、8、10 节作为你下载后的逐步测试顺序。出现问题时，保留不含密钥的错误日志、对应学生 ID、发生步骤和实际现象，便于定位。
