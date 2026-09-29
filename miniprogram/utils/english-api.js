const { validateConnection } = require('./english-view')
const STORAGE_KEY = 'englishClassConnectionV1'
// 仓库只带空模板；本人的 english-env.local.js 可以没有（全新副本、测试环境），此时显示“未配置”。
let initial = Object.assign({}, require('./english-env.example'))
try { initial = Object.assign(initial, require('./english-env.local')) } catch (e) { /* 未放置本地连接文件 */ }
function connection() { return Object.assign({}, initial, wx.getStorageSync(STORAGE_KEY) || {}) }
function isConfigured(c) { return Boolean(c && c.baseUrl && c.studentId && c.token) }
function saveConnection(c) { validateConnection(c); wx.setStorageSync(STORAGE_KEY, c) }
function call(method, path, data, params = {}, timeout = 15000) {
  return new Promise((resolve, reject) => {
    let c
    try { c = validateConnection(connection()) } catch (e) { reject(e); return }
    const query = Object.assign({ student_id: c.studentId }, params)
    const qs = Object.keys(query).map(k => `${encodeURIComponent(k)}=${encodeURIComponent(query[k])}`).join('&')
    wx.request({
      url: c.baseUrl.replace(/\/$/, '') + path + '?' + qs, method, data, timeout,
      header: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + c.token },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) { resolve(res.data); return }
        const detail = res.data && res.data.detail
        reject(new Error(typeof detail === 'string' ? detail : `服务器返回 ${res.statusCode}，请检查配置`))
      },
      fail() { reject(new Error('没有连接到公共服务。请检查地址、HTTPS合法域名和网络。')) }
    })
  })
}
module.exports = {
  connection, saveConnection, isConfigured,
  config: () => call('GET', '/api/config'),
  saveConfig: cfg => call('PUT', '/api/config', cfg),
  words: cfg => call('GET', '/api/words', undefined, { grade: cfg.grade, semester: cfg.semester, unit: cfg.unit }),
  progress: () => call('GET', '/api/progress'),
  llm: () => call('GET', '/api/llm'),
  // 保存自带模型要先测试调用一次（服务器最多等 20 秒），这里给 30 秒。
  saveLlm: body => call('PUT', '/api/llm', body, {}, 30000),
  clearLlm: () => call('DELETE', '/api/llm')
}
