function statusText(row) {
  if (row.status === 2) return '会说了'
  if (row.status === 1) return '听懂了'
  return row.last_practiced_date ? '继续练习' : '没练过'
}
function buildReport(payload) {
  if (!payload || !Array.isArray(payload.words) || typeof payload.today !== 'string') throw new Error('进度数据格式不正确')
  const decorate = row => ({ ...row, stateText: statusText(row), unclearText: `系统累计没听清 ${row.unclear_count || 0} 次` })
  const allWords = payload.words.map(decorate)
  const todayWords = allWords.filter(row => row.last_practiced_date === payload.today)
  return { today: payload.today, todayWords, allWords, speakingCount: todayWords.filter(x => x.status === 2).length,
    listeningCount: todayWords.filter(x => x.status === 1).length, practicingCount: todayWords.filter(x => x.status === 0).length }
}
function validateConnection(c) {
  if (!c || !/^https:\/\/[^\s/?#]+(?:\/[^\s?#]*)?\/?$/.test(c.baseUrl)) {
    if (!(c && c.allowHttpForLan && /^http:\/\/[^\s/?#]+(?:\/[^\s?#]*)?\/?$/.test(c.baseUrl))) throw new Error('请填写HTTPS公共服务地址；局域网HTTP测试须由老师明确开启')
  }
  if (!/^[a-z][a-z0-9_-]{1,31}$/.test(c.studentId || '')) throw new Error('学生ID格式不正确')
  if (typeof c.token !== 'string' || c.token.trim().length < 16 || /PUT_|REPLACE|YOUR_/.test(c.token)) throw new Error('请填写老师分配的本人课堂凭证')
  return c
}
module.exports = { statusText, buildReport, validateConnection }
