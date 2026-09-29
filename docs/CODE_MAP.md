# 代码结构与后续修改

公共层（老师）：`dictionary.py`读原词库；`store.py`保存配置与进度；`public_api.py`提供三类学习接口；`providers.py`调用真实模型、识别、合成；`provision.py/cli.py`创建学生凭证。

学生层：`engine.py`是完整听说流程；`client.py`只带本人凭证调用公共层；`brain_api.py`接自己的Pi和串行管理会话；`prompts/student.md`可改情境偏好。配置、级别规则和学习状态不由提示词任意覆盖。

终端：`pi/audio.py`负责PCM/WAV、说话结束检测、USB声卡发现与控制词；`pi/english_voice.py`实现唤醒、网络交互、播放、暂停与结束。

小程序：`pages/english-config`完整配置页；`pages/english-result`完整结果页；`utils/english-api.js`实际网络请求；`english-view.js`分离结果展示和连接校验，便于测试。

安装：`install_server.sh`只做首次独立安装；`create_student.sh`创建每人目录和服务；`install_pi.sh`独立装插件但不抢麦克风；`course_mode.py`负责显式、可恢复切换；`build_miniprogram.py`把两页追加到原小程序副本。

## 应保留的约束

不要用预期答案限定唯一识别输出，不要把跟读直接算独立会说，不要把没听清当答错，不要拿ASR文字推导精确发音分数。模型没有改配置／清库工具；公共API不能只凭请求里的student_id信任访问者。

`tests/test_http_integration.py`中的模型、转写、合成服务是本地测试替身，不是备用供应商，也不得导入正式服务中。原字典缺失必须显式报错，不从测试文件补一份冒充原词库。

以后继续开发先运行完整测试，再为要修改的行为补充测试。两端接口字段改变时同步修改文档、页面和集成测试，不只改Prompt。
