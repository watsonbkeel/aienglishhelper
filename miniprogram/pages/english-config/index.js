const api = require('../../utils/english-api')
const origin = require('../../utils/english-origin')
const DIFFICULTIES = ['basic', 'standard', 'challenge']
Page({
  data: {
    title: '为自己做一个英语练习工具', connection: {}, connectionOpen: false, unconfigured: false, ready: false, loading: false, saving: false, error: '',
    form: { grade: 1, semester: 1, unit: 0, duration_minutes: 10, chinese_help: true, difficulty: 'basic', practice_words: 3 },
    grades: ['一年级', '二年级', '三年级', '四年级', '五年级', '六年级', '初一', '初二', '初三', '高一', '高二', '高三'], semesters: ['上学期', '下学期'],
    durations: [5, 10, 15, 20, 30], wordCounts: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], difficulties: ['起步：短问题，允许单词回答', '巩固：尝试简单完整句', '挑战：增加简短追问'],
    llm: { mode: 'platform' }, advancedOpen: false, llmForm: { base_url: '', model: '', api_key: '' }, llmBusy: false, llmError: '',
    groups: [], groupIndex: 0, durationIndex: 1, wordCountIndex: 2, difficultyIndex: 0, wordPreview: '', originHome: origin.home
  },
  onLoad() { this._generation = 0; this.setData({ connection: api.connection() }) },
  onShow() { this.loadSaved() },
  onHide() { this._generation = (this._generation || 0) + 1; this.setData({ loading: false, saving: false }) },
  onUnload() { this._generation = (this._generation || 0) + 1 },
  async loadSaved() {
    const n = ++this._generation
    if (!api.isConfigured(api.connection())) {
      // 还没有课堂连接：不发请求、不报错，直接引导填写。
      this.setData({ unconfigured: true, connectionOpen: true, ready: false, loading: false, error: '' })
      return
    }
    this.setData({ loading: true, error: '', ready: false, unconfigured: false })
    try {
      const form = await api.config()
      const catalog = await api.words(form)
      if (n !== this._generation) return
      this.showForm(form, catalog)
      this.setData({ connection: api.connection(), ready: true })
      this.loadLlm(n)
    } catch (e) { if (n === this._generation) this.setData({ error: e.message, connectionOpen: true }) }
    finally { if (n === this._generation) this.setData({ loading: false }) }
  },
  showForm(form, catalog) {
    this.setData({ form, groups: catalog.units,
      groupIndex: Math.max(0, catalog.units.findIndex(x => x.value === form.unit)),
      durationIndex: this.data.durations.indexOf(form.duration_minutes), wordCountIndex: Math.max(0, this.data.wordCounts.indexOf(form.practice_words || 3)), difficultyIndex: DIFFICULTIES.indexOf(form.difficulty),
      wordPreview: catalog.words.slice(0, 12).map(x => x.word).join(' · ') })
  },
  async changeRange(patch) {
    const form = Object.assign({}, this.data.form, patch)
    const n = ++this._generation
    this.setData({ form, loading: true, error: '', ready: false })
    try {
      const catalog = await api.words(form)
      if (n !== this._generation) return
      this.showForm(form, catalog); this.setData({ ready: true })
    } catch (e) { if (n === this._generation) this.setData({ error: e.message }) }
    finally { if (n === this._generation) this.setData({ loading: false }) }
  },
  onGrade(e) { this.changeRange({ grade: Number(e.detail.value) + 1, unit: 0 }) },
  onSemester(e) { this.changeRange({ semester: Number(e.detail.value) + 1, unit: 0 }) },
  onGroup(e) { const group = this.data.groups[Number(e.detail.value)]; if (group) this.changeRange({ unit: group.value }) },
  onDuration(e) { const i = Number(e.detail.value); this.setData({ 'form.duration_minutes': this.data.durations[i], durationIndex: i }) },
  onWordCount(e) { const i = Number(e.detail.value); this.setData({ 'form.practice_words': this.data.wordCounts[i], wordCountIndex: i }) },
  onDifficulty(e) { const i = Number(e.detail.value); this.setData({ 'form.difficulty': DIFFICULTIES[i], difficultyIndex: i }) },
  onChinese(e) { this.setData({ 'form.chinese_help': Boolean(e.detail.value) }) },
  async onSave() {
    if (this.data.loading || this.data.saving || !this.data.ready) return
    const n = this._generation
    this.setData({ saving: true, error: '' })
    try {
      const saved = await api.saveConfig(this.data.form)
      if (n !== this._generation) return
      this.setData({ form: saved }); wx.showToast({ title: '已保存，下次练习生效', icon: 'none' })
    } catch (e) { if (n === this._generation) this.setData({ error: e.message }) }
    finally { if (n === this._generation) this.setData({ saving: false }) }
  },
  async loadLlm(n) {
    try {
      const llm = await api.llm()
      if (n !== this._generation) return
      this.setData({ llm, llmError: '', llmForm: { base_url: llm.base_url || '', model: llm.model || '', api_key: '' } })
    } catch (e) { if (n === this._generation) this.setData({ llmError: e.message }) }
  },
  onLlmInput(e) { const field = e.currentTarget.dataset.field; if (['base_url', 'model', 'api_key'].includes(field)) this.setData({ [`llmForm.${field}`]: e.detail.value.trim() }) },
  async onSaveLlm() {
    if (this.data.llmBusy) return
    const f = this.data.llmForm
    if (!f.base_url || !f.model || (!f.api_key && this.data.llm.mode !== 'custom')) { this.setData({ llmError: '请填写接口地址、模型名和 API Key' }); return }
    this.setData({ llmBusy: true, llmError: '' })
    try {
      // API Key 只提交给服务器保存，不写入手机本地存储，页面也不回显明文。
      const llm = await api.saveLlm({ base_url: f.base_url, model: f.model, api_key: f.api_key || null })
      this.setData({ llm, 'llmForm.api_key': '' }); wx.showToast({ title: '测试通过，已改用自己的模型', icon: 'none' })
    } catch (e) { this.setData({ llmError: e.message }) }
    finally { this.setData({ llmBusy: false }) }
  },
  async onClearLlm() {
    if (this.data.llmBusy) return
    this.setData({ llmBusy: true, llmError: '' })
    try { const llm = await api.clearLlm(); this.setData({ llm, llmForm: { base_url: '', model: '', api_key: '' } }); wx.showToast({ title: '已改用平台模型', icon: 'none' }) }
    catch (e) { this.setData({ llmError: e.message }) }
    finally { this.setData({ llmBusy: false }) }
  },
  onToggleAdvanced() { this.setData({ advancedOpen: !this.data.advancedOpen }) },
  onConnectionInput(e) { const field = e.currentTarget.dataset.field; if (['baseUrl', 'studentId', 'token'].includes(field)) this.setData({ [`connection.${field}`]: e.detail.value.trim() }) },
  onToggleConnection() { this.setData({ connectionOpen: !this.data.connectionOpen }) },
  onSaveConnection() {
    try { api.saveConnection(this.data.connection); this.loadSaved() } catch (e) { this.setData({ error: e.message }) }
  },
  onResult() { wx.navigateTo({ url: '/pages/english-result/index' }) },
  onOriginal() {
    if (!origin.home) return
    if (origin.isTab) wx.switchTab({ url: '/' + origin.home })
    else wx.navigateTo({ url: '/' + origin.home })
  }
})
