// 仓库自带的空连接模板，可以公开。真实连接放在同目录 english-env.local.js（不提交），
// 由 create_student 生成；也可以不放文件，直接在「课堂连接设置」里填写。
// 这里永远不能写大模型/语音服务密钥。
module.exports = { baseUrl: '', studentId: '', token: '', allowHttpForLan: false }
