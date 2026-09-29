const initial = require('./english-env.local')
const { validateConnection } = require('./english-view')
const STORAGE_KEY = 'englishClassConnectionV1'
function connection() { return Object.assign({}, initial, wx.getStorageSync(STORAGE_KEY) || {}) }
function saveConnection(c) { validateConnection(c); wx.setStorageSync(STORAGE_KEY, c) }
function call(method, path, data, params = {}) {
  return new Promise((resolve, reject) => {
    let c
    try { c = validateConnection(connection()) } catch (e) { reject(e); return }
    const query = Object.assign({ student_id: c.studentId }, params)
    const qs = Object.keys(query).map(k => `${encodeURIComponent(k)}=${encodeURIComponent(query[k])}`).join('&')
    wx.request({
      url: c.baseUrl.replace(/\/$/, '') + path + '?' + qs, method, data, timeout: 15000,
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
  connection, saveConnection,
  config: () => call('GET', '/api/config'),
  saveConfig: cfg => call('PUT', '/api/config', cfg),
  words: cfg => call('GET', '/api/words', undefined, { grade: cfg.grade, semester: cfg.semester, unit: cfg.unit }),
  progress: () => call('GET', '/api/progress'),
  llm: () => call('GET', '/api/llm'),
  saveLlm: body => call('PUT', '/api/llm', body),
  clearLlm: () => call('DELETE', '/api/llm')
}
