# 来源与依赖说明

本包新增源码为英语课程扩展；没有将原仓库内容伪装成已经重写或已部署。安装过程可导入原词库，或下载锁定的原仓库供合并／对照。

- aibot：`https://github.com/watsonbkeel/aibot`，锁定 `cd5b34c446d5134c6346f290f7513380edba84a5`。复用身体／脑端架构、中文唤醒习惯、USB设备基线与Edge/Piper路径的设计；新插件独立运行，另提供旧文本桥兼容工具。
- WordMaster_SZ：`https://github.com/watsonbkeel/WordMaster_SZ`，锁定 `4701d5bc72097c8851b180bf6025fb8b9db12ae4`。唯一正式词库来源为其`utils/fullDictionary.js`或用户提供的本地同类文件；不编造教材单元。
- 原词库Git blob：`ea9b65ea1c1ae6e4b871bbd27f8d46796097d8cc`。联网导入验证此值，本地导入记录实际值。
- DeepSeek请求格式：`https://api-docs.deepseek.com/api/create-chat-completion/` 与 `https://api-docs.deepseek.com/guides/thinking_mode/`。运行时模型ID以你实际接口为准，关闭思考在代码中显式发送。
- Vosk模型：`https://alphacephei.com/vosk/models`。模型权重需另下，遵守各模型自己的许可证；默认英文small-en-us-0.15、中文small-cn-0.22。
- 微信网络接口参考：`https://developers.weixin.qq.com/miniprogram/dev/framework/ability/network.html`。真实AppID、成员权限和手机网络在你的账号中验证；本环境未运行微信开发者工具。

上游下载后的LICENSE文件应随原项目副本保留。小程序合并工具会保留原工程的LICENSE；本包LICENSE仅覆盖本次新增源码。第三方依赖和模型遵从各自许可证。
