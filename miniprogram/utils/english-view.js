function statusText(row) {
  if (row.status === 2) return '会说了'
  if (row.status === 1) return '听懂了'
  return row.last_practiced_date ? '继续练习' : '没练过'
}
function evidenceText(row) {
  // 旧记录没有这些字段时不显示，避免把“没有数据”说成“0 次”。
  if (!row.used_word_count && !row.imitated_count) return ''
  // 两个计数是独立累计的（跟读时说出目标词两边都会加1），不是“其中”关系，分开写。
  const own = `说出目标词 ${row.used_word_count || 0} 次`
  return row.imitated_count ? `${own}；跟读/模仿 ${row.imitated_count} 次（跟读不算会说）` : own
}
function buildReport(payload) {
  if (!payload || !Array.isArray(payload.words) || typeof payload.today !== 'string') throw new Error('进度数据格式不正确')
  const decorate = row => ({ ...row, stateText: statusText(row), unclearText: `系统累计没听清 ${row.unclear_count || 0} 次`, evidenceText: evidenceText(row) })
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
