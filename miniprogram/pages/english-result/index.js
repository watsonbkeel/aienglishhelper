const api = require('../../utils/english-api')
const { buildReport } = require('../../utils/english-view')
Page({
  data: { loading: false, error: '', loaded: false, today: '', todayWords: [], allWords: [], speakingCount: 0, listeningCount: 0, practicingCount: 0, showAll: false },
  onLoad() { this._generation = 0 },
  onShow() { this.refresh() },
  onHide() { this._generation = (this._generation || 0) + 1 },
  onUnload() { this._generation = (this._generation || 0) + 1 },
  async refresh() {
    const n = ++this._generation
    this.setData({ loading: true, error: '', loaded: false })
    try {
      const result = buildReport(await api.progress())
      if (n === this._generation) this.setData(Object.assign({}, result, { loaded: true }))
    } catch (e) { if (n === this._generation) this.setData({ error: e.message }) }
    finally { if (n === this._generation) this.setData({ loading: false }); wx.stopPullDownRefresh() }
  },
  onPullDownRefresh() { this.refresh() },
  onToggleAll() { this.setData({ showAll: !this.data.showAll }) },
  onConfig() { wx.navigateBack({ fail: () => wx.reLaunch({ url: '/pages/english-config/index' }) }) }
})
