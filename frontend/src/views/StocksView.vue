<template>
  <div class="stocks-view">
    <aside class="sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">我的股票</span>
      </div>
      <div class="sidebar-actions">
        <button class="btn btn-small" @click="showAdd = true">+ 添加股票</button>
        <button class="btn btn-small" @click="showImport = true">批量导入</button>
        <button class="btn btn-small btn-danger" @click="deleteSelected" :disabled="!selectedCode">删除</button>
      </div>
      <div class="opp-filter">
        <div class="opp-filter-title">机会点筛选</div>
        <div class="opp-filter-row">
          <input v-model="oppFilterStart" type="date" class="date-input" placeholder="开始日期" />
          <span class="date-sep">~</span>
          <input v-model="oppFilterEnd" type="date" class="date-input" placeholder="结束日期" />
        </div>
        <div class="opp-filter-row">
          <button class="btn btn-small" @click="applyOppFilter" :disabled="oppLoading">筛选</button>
          <button class="btn btn-small btn-ghost" @click="clearOppFilter" :disabled="oppLoading">清除</button>
          <span v-if="oppLoading" class="opp-loading">加载中...</span>
          <span v-if="oppFilterResultMsg" class="opp-count">{{ oppFilterResultMsg }}</span>
        </div>
      </div>
      <div class="stock-list" v-if="displayStocks.length > 0">
        <div
          v-for="s in displayStocks"
          :key="s.code"
          class="stock-item"
          :class="{ selected: s.code === selectedCode, 'has-opp': s.has_opportunities }"
          @click="selectStock(s.code)"
        >
          <span class="stock-dot" :class="{ 'has-opp-dot': s.has_opportunities }"></span>
          <span class="stock-code">{{ s.code }}</span>
          <span class="stock-name">{{ s.name || '' }}</span>
          <span v-if="s.opp_count > 0" class="stock-opp-badge">{{ s.opp_count }}</span>
        </div>
      </div>
      <div class="empty-hint" v-else-if="!oppLoading">点击上方按钮添加股票</div>
      <div class="empty-hint" v-else>加载中...</div>

      <div class="modal" v-if="showAdd" @click.self="showAdd = false">
        <div class="modal-content">
          <h3>添加股票</h3>
          <input v-model="addCode" placeholder="输入股票代码，如 000001" class="input" @keyup.enter="addStock" />
          <div class="modal-actions">
            <button class="btn" @click="addStock">添加</button>
            <button class="btn btn-ghost" @click="showAdd = false">取消</button>
          </div>
          <div class="error" v-if="addError">{{ addError }}</div>
        </div>
      </div>

      <div class="modal" v-if="showImport" @click.self="showImport = false">
        <div class="modal-content">
          <h3>批量导入股票</h3>
          <p class="hint">每行一个代码，支持沪深A股，如 000001</p>
          <textarea v-model="importText" placeholder="000001&#10;000002&#10;002001" class="textarea"></textarea>
          <div class="modal-actions">
            <button class="btn" @click="importStocks">导入</button>
            <button class="btn btn-ghost" @click="showImport = false">取消</button>
          </div>
          <div class="import-result" v-if="importResult">
            <span class="success">成功添加: {{ importResult.added.length }}</span>
            <span class="fail" v-if="importResult.failed.length"> 失败: {{ importResult.failed.join(', ') }}</span>
          </div>
        </div>
      </div>

      <div class="modal" v-if="showOverride" @click.self="showOverride = false">
        <div class="modal-content">
          <h3>手动公式覆盖 - {{ selectedCode }}</h3>
          <p class="hint">设置后优先于AI探索的公式，覆盖将立即生效并参与后续探索迭代</p>
          <div class="override-fields">
            <label class="label">公式表达式</label>
            <input v-model="overrideExpr" placeholder="如: 0.5*RSI_6 + 0.5*VOL_RATIO > 0.7" class="input" />
            <label class="label">逻辑说明（选填）</label>
            <input v-model="overrideLogic" placeholder="如: RSI和成交量共振" class="input" />
          </div>
          <div class="modal-actions">
            <button class="btn" @click="saveOverride">保存</button>
            <button class="btn btn-ghost" @click="showOverride = false">取消</button>
          </div>
          <div class="error" v-if="overrideError">{{ overrideError }}</div>
        </div>
      </div>
    </aside>

    <section class="result-panel">
      <div v-if="!selectedCode" class="empty-panel">
        <p>从左侧列表选择一支股票开始分析</p>
      </div>
      <div v-else class="stock-result">
        <div class="result-header">
          <span class="stock-title">{{ selectedCode }} {{ selectedName }}</span>
          <button class="btn" @click="updateStock" :disabled="updating">
            {{ updating ? '更新中...' : '更新数据' }}
          </button>
          <span v-if="syncOppMsg" class="sync-opp-msg">{{ syncOppMsg }}</span>
          <button class="btn" @click="toggleHistory" :disabled="!selectedCode">
            {{ showHistory ? '收起历史报告' : '历史报告' }}
          </button>
        </div>

        <div v-if="showHistory" class="history-section">
          <div v-if="historyLoading" class="history-hint">加载中...</div>
          <div v-else-if="historyReports.length === 0" class="history-hint">暂无历史报告</div>
          <div v-for="r in historyReports" :key="r.id" class="history-card">
            <div class="history-card-header">
              <span class="history-status" :class="'status-' + r.status">{{ r.status }}</span>
              <span class="history-meta">{{ r.iterations }} 轮 · {{ r.candidates_total }} 候选</span>
            </div>
            <div v-if="r.best_formula" class="history-formula">{{ r.best_formula }}</div>
            <div class="history-meta">
              精度: {{ r.best_precision !== null ? (r.best_precision * 100).toFixed(1) + '%' : '无' }}
              · {{ r.final_message || '' }}
            </div>
            <div class="history-date">{{ r.created_at }}</div>
          </div>
        </div>

        <div class="formula-section" v-if="formulas.length > 0">
          <div class="formula-card">
            <div class="formula-expr">{{ formulas[0].formula_expr }}</div>
            <div class="formula-stages">
              <span>段1: {{ (formulas[0].a1 * 100).toFixed(0) }}%</span>
              <span>段2: {{ (formulas[0].a2 * 100).toFixed(0) }}%</span>
              <span>段3: {{ (formulas[0].a3 * 100).toFixed(0) }}%</span>
            </div>
            <button class="btn btn-small btn-override" @click="openOverride">手动覆盖</button>
          </div>
        </div>
        <div class="no-formula" v-else>
          <p>该股暂无买点公式，请先探索或手动设置</p>
          <button class="btn btn-small btn-override" @click="openOverride">手动覆盖</button>
        </div>

        <div class="chart-toolbar">
          <button class="toggle-btn" :class="{ active: showU1 }" @click="toggleU1">
            U1买点<span class="dot red-dot">·</span>
          </button>
          <button class="toggle-btn" :class="{ active: showOpp }" @click="toggleOpp" :disabled="!hasFormula">
            机会点<span class="dot blue-dot">·</span>
          </button>
          <button class="toggle-btn btn-opp-update" :disabled="!hasFormula || updatingOpps" @click="updateOpportunities">
            {{ updatingOpps ? '更新中...' : '更新机会点' }}
          </button>
        </div>

        <div class="chart-container">
          <div ref="chartRef" class="chart"></div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import * as api from '@/utils/api'
import * as echarts from 'echarts'

const stocks = ref([])
const selectedCode = ref('')
const selectedName = ref('')
const formulas = ref([])
const displayStocks = ref([])
const isFiltered = ref(false)
const oppFilterStart = ref('')
const oppFilterEnd = ref('')
const oppLoading = ref(false)
const oppFilterResultMsg = ref('')

const klineData = ref([])
const u1Dates = ref(new Set())
const oppDates = ref(new Set())
const hasFormula = ref(false)

const showU1 = ref(false)
const showOpp = ref(false)

const showAdd = ref(false)
const showImport = ref(false)
const showHistory = ref(false)
const historyReports = ref([])
const historyLoading = ref(false)
const showOverride = ref(false)
const addCode = ref('')
const addError = ref('')
const overrideExpr = ref('')
const overrideLogic = ref('')
const overrideError = ref('')
const importText = ref('')
const importResult = ref(null)
const updatingOpps = ref(false)
const updating = ref(false)
const syncOppMsg = ref('')

async function loadHistory() {
  historyLoading.value = true
  try {
    historyReports.value = await api.getExploreReports(selectedCode.value)
  } catch (e) { historyReports.value = [] }
  finally { historyLoading.value = false }
}

function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) loadHistory()
}
const chartRef = ref(null)
let chart = null
let chartZoomStart = null
let chartZoomEnd = null

let _stockPollTimer = null

onMounted(() => {
  loadStocks()
  _stockPollTimer = setInterval(loadStocks, 30000)
})

onUnmounted(() => {
  if (_stockPollTimer) clearInterval(_stockPollTimer)
})

async function loadStocks() {
  try {
    stocks.value = await api.listStocks()
    if (!isFiltered.value) {
      displayStocks.value = [...stocks.value]
    }
  } catch (e) { console.error(e) }
}

async function applyOppFilter() {
  oppLoading.value = true
  oppFilterResultMsg.value = ''
  try {
    const result = await api.listStocksWithOpportunities(oppFilterStart.value || undefined, oppFilterEnd.value || undefined)
    displayStocks.value = result
    isFiltered.value = true
    const hasFilter = oppFilterStart.value || oppFilterEnd.value
    const totalOpp = result.reduce((sum, s) => sum + (s.opp_count || 0), 0)
    oppFilterResultMsg.value = hasFilter
      ? `${result.length} 支 / ${totalOpp} 点`
      : `${result.length} 支`
  } catch (e) { console.error(e) } finally { oppLoading.value = false }
}

async function clearOppFilter() {
  oppFilterStart.value = ''
  oppFilterEnd.value = ''
  oppFilterResultMsg.value = ''
  isFiltered.value = false
  displayStocks.value = [...stocks.value]
}

async function selectStock(code) {
  selectedCode.value = code
  const s = stocks.value.find(x => x.code === code)
  selectedName.value = s ? (s.name || '') : ''
  await loadFormulas(code)
  await loadKlineData(code)
  await loadOpportunityPoints(code)
  await nextTick()
  renderChart()
}

async function addStock() {
  addError.value = ''
  try {
    const result = await api.addStock(addCode.value)
    if (result.status === 'added' || result.status === 'already_exists') {
      showAdd.value = false; addCode.value = ''
      await loadStocks()
      isFiltered.value = false
      if (result.status === 'added') selectStock(result.code)
    } else { addError.value = result.status }
  } catch (e) { addError.value = String(e) }
}

async function importStocks() {
  const codes = importText.value.split('\n').map(c => c.trim()).filter(c => c)
  if (!codes.length) return
  try {
    importResult.value = await api.importStocks(codes)
    showImport.value = false; importText.value = ''
    await loadStocks()
    isFiltered.value = false
  } catch (e) { console.error(e) }
}

async function deleteSelected() {
  if (!selectedCode.value) return
  await api.deleteStock(selectedCode.value)
  selectedCode.value = ''; selectedName.value = ''
  formulas.value = []; klineData.value = []
  u1Dates.value = new Set(); oppDates.value = new Set(); hasFormula.value = false
  await loadStocks()
  isFiltered.value = false
}

async function updateStock() {
  if (!selectedCode.value) return
  updating.value = true
  syncOppMsg.value = ''
  try {
    const result = await api.syncStock(selectedCode.value)
    if (result.opportunity_updated && result.opp_result) {
      const r = result.opp_result
      if (r.count !== undefined) {
        syncOppMsg.value = `机会点已更新: ${r.count} 个 (a1=${(r.a1*100).toFixed(0)}% a2=${(r.a2*100).toFixed(0)}% a3=${(r.a3*100).toFixed(0)}%)`
      }
    }
    await loadKlineData(selectedCode.value)
    if (showOpp.value) { await loadOpportunityPoints(selectedCode.value) }
    await loadFormulas(selectedCode.value)
    renderChart()
  } catch (e) { console.error(e) } finally { updating.value = false }
}

async function loadFormulas(code) {
  try {
    formulas.value = await api.getFormulas(code)
    hasFormula.value = formulas.value.length > 0
  } catch (e) { formulas.value = []; hasFormula.value = false }
}

async function loadKlineData(code) {
  try {
    klineData.value = await api.getKline(code)
    const u1 = await api.getU1BuyPoints(code)
    u1Dates.value = new Set(u1.u1_dates || [])
  } catch (e) { klineData.value = []; u1Dates.value = new Set() }
}

async function loadOpportunityPoints(code) {
  try {
    const opp = await api.getOpportunityPoints(code)
    oppDates.value = new Set(opp.opp_dates || [])
  } catch (e) { oppDates.value = new Set() }
}

function toggleU1() {
  showU1.value = !showU1.value
  renderChart()
}

function toggleOpp() {
  showOpp.value = !showOpp.value
  renderChart()
}

async function updateOpportunities() {
  if (!selectedCode.value || !hasFormula.value || updatingOpps.value) return
  updatingOpps.value = true
  try {
    const res = await api.updateOpportunitiesSingle(selectedCode.value)
    await loadOpportunityPoints(selectedCode.value)
    const fresh = await api.getFormulas(selectedCode.value)
    formulas.value = fresh
    hasFormula.value = fresh.length > 0
    if (showOpp.value) renderChart()
  } catch (e) { console.error(e) } finally { updatingOpps.value = false }
}

function openOverride() {
  overrideExpr.value = formulas.value.length > 0 ? formulas.value[0].formula_expr : ''
  overrideLogic.value = formulas.value.length > 0 ? (formulas.value[0].logic_desc || '') : ''
  overrideError.value = ''
  showOverride.value = true
}

async function saveOverride() {
  overrideError.value = ''
  if (!overrideExpr.value.trim()) { overrideError.value = '请输入公式表达式'; return }
  try {
    await api.overrideFormula(selectedCode.value, {
      formula_expr: overrideExpr.value.trim(),
      logic_desc: overrideLogic.value.trim()
    })
    showOverride.value = false
    await loadFormulas(selectedCode.value)
    if (showOpp.value) { await loadOpportunityPoints(selectedCode.value); renderChart() }
  } catch (e) { overrideError.value = String(e).substring(0, 100) }
}

function calcLast40DaysStart(dates) {
  if (!dates || dates.length < 2) return 0
  // Always show the last 40 candles, regardless of total data length
  if (dates.length <= 40) return 0
  return Math.round(((dates.length - 40) / (dates.length - 1)) * 100)
}

function getMarkPoints() {
  const u1Mark = []
  const oppMark = []
  klineData.value.forEach((d, i) => {
    if (showU1.value && u1Dates.value.has(d.date)) {
      u1Mark.push({ coord: [i, d.low], itemStyle: { color: '#ef5350' } })
    }
    if (showOpp.value && hasFormula.value && oppDates.value.has(d.date)) {
      oppMark.push({ coord: [i, d.high], itemStyle: { color: '#2196f3' } })
    }
  })
  const markPoints = []
  if (u1Mark.length > 0) {
    markPoints.push({ name: 'U1买点', type: 'scatter', data: u1Mark, symbol: 'triangle', symbolSize: 6, label: { show: false }, tooltip: { formatter: 'U1买点' } })
  }
  if (oppMark.length > 0) {
    markPoints.push({ name: '机会点', type: 'scatter', data: oppMark, symbol: 'triangle', symbolSize: 6, label: { show: false }, tooltip: { formatter: '机会点' } })
  }
  return markPoints
}

function renderChart() {
  if (!chartRef.value) { return }
  if (!klineData.value.length) { return }
  const data = klineData.value.map(d => [d.open, d.close, d.low, d.high])
  const dates = klineData.value.map(d => d.date)
  // Always recalculate zoom when data changes (new stock selected)
  const zoomStart = calcLast40DaysStart(dates)
  chartZoomStart = zoomStart
  chartZoomEnd = 100
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('dataZoom', function() {
      const opt = chart.getOption()
      chartZoomStart = opt.dataZoom[0].start
      chartZoomEnd = opt.dataZoom[0].end
    })
  }
  const ma5Data = []
  for (let i = 0; i < klineData.value.length; i++) {
    if (i < 4) { ma5Data.push(null); continue }
    let sum = 0
    for (let j = 0; j < 5; j++) sum += klineData.value[i - j].close
    ma5Data.push(sum / 5)
  }
  const markPoints = getMarkPoints()
  const option = {
    backgroundColor: '#1a1a2e',
    textStyle: { color: '#a0a0a0' },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: '#555' } },
      formatter: function(params) {
        if (!params || params.length === 0) return ''
        const cand = params.find(p => p.seriesType === 'candlestick')
        if (!cand) return ''
        const d = klineData.value[cand.dataIndex]
        const u1Mark = showU1.value && u1Dates.value.has(d.date)
        const oppMark = showOpp.value && hasFormula.value && oppDates.value.has(d.date)
        let marks = ''
        if (u1Mark) marks += '<span style="color:#ef5350">U1买点</span> '
        if (oppMark) marks += '<span style="color:#2196f3">机会点</span>'
        const ma5 = ma5Data[cand.dataIndex]
        return `<strong>${d.date}</strong><br/>`
          + `开盘: ${d.open.toFixed(2)} &nbsp; 收盘: ${d.close.toFixed(2)}<br/>`
          + `最高: ${d.high.toFixed(2)} &nbsp; 最低: ${d.low.toFixed(2)}<br/>`
          + (ma5 !== null ? `5日均线: <span style="color:#ffd700">${ma5.toFixed(2)}</span><br/>` : '')
          + `成交量: ${d.volume.toFixed(2)}${marks}`
      }
    },
    legend: { show: false },
    grid: [
      { left: 60, right: 20, top: 20, height: '60%' },
      { left: 60, right: 20, top: '72%', height: '20%' }
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, boundaryGap: false },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: false }
    ],
    yAxis: [
      { scale: true, gridIndex: 0 },
      { scale: true, gridIndex: 1 }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: chartZoomStart, end: chartZoomEnd },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 20, borderColor: '#0f3460', backgroundColor: '#16213e', fillerColor: 'rgba(233,69,96,0.2)', handleStyle: { color: '#e94560' }, textStyle: { color: '#888' }, start: chartZoomStart, end: chartZoomEnd }
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' },
        markPoint: markPoints.length > 0 ? { animation: false, data: markPoints.reduce((acc, mp) => acc.concat(mp.data), []) } : undefined
      },
      {
        name: '成交量',
        type: 'bar',
        data: klineData.value.map(d => ({ value: d.volume, itemStyle: { color: d.close >= d.open ? 'rgba(239,83,80,0.5)' : 'rgba(38,166,154,0.5)' } })),
        xAxisIndex: 1,
        yAxisIndex: 1
      },
      {
        name: 'MA5',
        type: 'line',
        data: ma5Data,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: false,
        lineStyle: { color: '#ffd700', width: 1 },
        itemStyle: { color: '#ffd700' },
        symbol: 'none'
      }
    ]
  }
  chart.setOption(option, true)
}
</script>

<style scoped>
.stocks-view { display: flex; height: 100%; }
.sidebar { width: 220px; background: #16213e; border-right: 1px solid #0f3460; display: flex; flex-direction: column; flex-shrink: 0; }
.sidebar-header { padding: 12px 16px; border-bottom: 1px solid #0f3460; }
.sidebar-title { font-size: 13px; color: #888; }
.sidebar-actions { display: flex; gap: 6px; padding: 10px 12px; border-bottom: 1px solid #0f3460; }
.stock-list { flex: 1; overflow-y: auto; }
.stock-item { padding: 8px 12px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background 0.15s; }
.stock-item:hover { background: #1f2b4a; }
.stock-item.selected { background: #1f2b4a; border-left: 2px solid #e94560; }
.stock-dot { width: 6px; height: 6px; border-radius: 50%; background: #e94560; flex-shrink: 0; }
.stock-code { font-size: 13px; color: #a0a0a0; }
.stock-name { font-size: 12px; color: #555; margin-left: auto; }
.empty-hint { padding: 20px 12px; color: #555; font-size: 13px; text-align: center; }
.opp-filter { padding: 10px 12px; border-bottom: 1px solid #0f3460; background: #1a2540; flex-shrink: 0; }
.opp-filter-title { font-size: 11px; color: #666; margin-bottom: 6px; }
.opp-filter-row { display: flex; align-items: center; gap: 4px; margin-bottom: 6px; }
.date-input { background: #0f3460; border: 1px solid #1f2b4a; color: #e0e0e0; padding: 3px 6px; border-radius: 3px; font-size: 11px; width: 100px; }
.date-sep { color: #555; font-size: 11px; }
.opp-loading { font-size: 11px; color: #888; }
.opp-count { font-size: 11px; color: #26a69a; margin-left: 4px; }
.stock-opp-badge { font-size: 10px; background: rgba(33,150,243,0.25); color: #2196f3; border-radius: 8px; padding: 1px 5px; margin-left: auto; }
.has-opp-dot { background: #2196f3; }
.stock-item.has-opp { border-left: 2px solid rgba(33,150,243,0.5); }
.sync-opp-msg { font-size: 12px; color: #26a69a; margin-left: 8px; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-content { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 24px; width: 340px; max-width: 90vw; }
.modal-content h3 { margin: 0 0 16px; color: #e0e0e0; font-size: 15px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.result-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.empty-panel { flex: 1; display: flex; align-items: center; justify-content: center; color: #555; }
.stock-result { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.result-header { padding: 10px 16px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #0f3460; flex-shrink: 0; }
.stock-title { font-size: 15px; color: #e0e0e0; font-weight: 600; }
.formula-section { padding: 10px 16px; border-bottom: 1px solid #0f3460; flex-shrink: 0; }
.formula-card { background: #1f2b4a; border-radius: 6px; padding: 10px 14px; }
.formula-expr { font-size: 13px; color: #e94560; font-family: monospace; margin-bottom: 6px; }
.formula-stages { display: flex; gap: 12px; font-size: 12px; color: #888; }
.no-formula { padding: 8px 16px; font-size: 13px; color: #555; border-bottom: 1px solid #0f3460; flex-shrink: 0; }
.chart-toolbar { display: flex; gap: 8px; padding: 10px 16px; border-bottom: 1px solid #0f3460; flex-shrink: 0; }
.toggle-btn { background: #1f2b4a; border: 1px solid #0f3460; color: #a0a0a0; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; transition: all 0.15s; display: flex; align-items: center; gap: 4px; }
.toggle-btn:hover { background: #2a3a5c; }
.toggle-btn.active { background: #2a3a5c; border-color: #e94560; color: #e0e0e0; }
.toggle-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.dot { font-size: 11px; }
.red-dot { color: #ef5350; }
.blue-dot { color: #2196f3; }
.btn-opp-update { color: #888; }
.btn-opp-update:disabled { opacity: 0.4; cursor: not-allowed; }
.chart-container { flex: 1; min-height: 0; padding: 8px; display: flex; flex-direction: column; }
.chart { flex: 1; min-height: 0; }
.btn { background: #e94560; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; transition: opacity 0.15s; }
.btn:hover { opacity: 0.85; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-small { background: #1f2b4a; color: #a0a0a0; border: 1px solid #0f3460; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.btn-small:hover { background: #2a3a5c; }
.btn-ghost { background: transparent; color: #888; border: 1px solid #0f3460; }
.btn-danger { color: #e94560; border-color: #e94560; }
.input { width: 100%; background: #0f3460; border: 1px solid #1f2b4a; color: #e0e0e0; padding: 8px 10px; border-radius: 4px; font-size: 13px; box-sizing: border-box; }
.textarea { width: 100%; background: #0f3460; border: 1px solid #1f2b4a; color: #e0e0e0; padding: 8px 10px; border-radius: 4px; font-size: 13px; resize: vertical; min-height: 80px; box-sizing: border-box; }
.error { margin-top: 8px; color: #e94560; font-size: 12px; }
.success { color: #26a69a; font-size: 13px; }
.fail { color: #e94560; font-size: 13px; margin-left: 8px; }
.hint { font-size: 12px; color: #555; margin-bottom: 8px; }
.override-fields { display: flex; flex-direction: column; gap: 8px; }
.label { font-size: 12px; color: #888; margin-bottom: -4px; }
.btn-override { margin-top: 6px; background: #0f3460; border: 1px solid #1f3a6a; color: #a0a0a0; }
.btn-override:hover { background: #1f3a6a; color: #e0e0e0; }
.history-section { padding: 10px 16px; border-bottom: 1px solid #0f3460; flex-shrink: 0; max-height: 220px; overflow-y: auto; }
.history-hint { color: #555; font-size: 13px; padding: 8px 0; }
.history-card { background: #1f2a47; border: 1px solid #0f3460; border-radius: 6px; padding: 12px; margin-bottom: 8px; }
.history-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.history-status { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.status-completed { background: rgba(38,166,154,0.3); color: #26a69a; }
.status-timeout { background: rgba(255,193,7,0.2); color: #ffc107; }
.status-stopped { background: rgba(239,83,80,0.2); color: #ef5350; }
.history-meta { font-size: 12px; color: #888; }
.history-formula { font-size: 13px; color: #e94560; margin-bottom: 4px; word-break: break-all; }
.history-date { font-size: 11px; color: #555; margin-top: 4px; }
</style>
