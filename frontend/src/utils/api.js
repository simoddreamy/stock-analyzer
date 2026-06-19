const API = '/api'

async function req(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export const listStocks    = ()       => req('/stocks/list')
export const listStocksWithOpportunities = (startDate, endDate) => {
  const params = new URLSearchParams()
  if (startDate) params.append('start_date', startDate)
  if (endDate) params.append('end_date', endDate)
  const qs = params.toString()
  return req('/stocks/with-opportunities' + (qs ? '?' + qs : ''))
}
export const addStock      = (code)   => req('/stocks/add', { method: 'POST', body: JSON.stringify({ code }) })
export const deleteStock   = (code)   => req(`/stocks/${code}`, { method: 'DELETE' })
export const importStocks  = (codes)  => req('/stocks/import', { method: 'POST', body: JSON.stringify({ codes }) })
export const syncStock    = (code)   => req('/data/sync-stock', { method: 'POST', body: JSON.stringify({ code, source: 'akshare' }) })
export const syncAll      = ()       => req('/data/sync-all', { method: 'POST' })
export const getKline     = (code)   => req(`/kline/${code}`)
export const getFormulas  = (code)   => req(`/formulas/${code}`)
export const getU1BuyPoints = (code) => req(`/formulas/${code}/u1`)
export const getOpportunityPoints = (code) => req(`/formulas/${code}/opportunity`)
export const updateOpportunitiesSingle = (code) => req(`/formulas/${code}/update-opportunities`, { method: 'POST' })
export const startExploration = (payload) => req('/explore', { method: 'POST', body: JSON.stringify(payload) })
export const pauseExploration = ()   => req('/explore/pause', { method: 'POST' })
export const stopExploration = ()   => req('/explore/stop', { method: 'POST' })
export const getExploreStatus = ()  => req('/explore/status')
export const getExploreReports  = (code) => code ? req('/explore/reports?code=' + code) : req('/explore/reports')
export const getExploreReport   = (id) => req(`/explore/reports/${id}`)
export const overrideFormula    = (code, payload) => req(`/formulas/${code}/override`, { method: 'POST', body: JSON.stringify(payload) })
export const getFormulaOverride = (code) => req(`/formulas/${code}/override`)
export const getSettings  = ()       => req('/settings')
export const setSetting = (key, value) => req(`/settings/${key}`, { method: 'POST', body: JSON.stringify({ value }) })
export const testConnection = (payload) => req('/settings/test-connection', { method: 'POST', body: JSON.stringify(payload) })