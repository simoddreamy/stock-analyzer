<template>
  <div class="backtest-view">
    <div class="page-header">
      <h2>回测分析</h2>
    </div>

    <div class="backtest-container">
      <!-- ==================== 左侧：配置面板 ==================== -->
      <div class="config-panel">
        <div class="panel-section">
          <h3>回测配置</h3>

          <!-- 股票选择 -->
          <div class="field">
            <label>股票</label>
            <select v-model="config.stock_code" class="select">
              <option value="">-- 选择股票 --</option>
              <option v-for="s in stocks" :key="s.code" :value="s.code">
                {{ s.code }} {{ s.name }}
              </option>
            </select>
          </div>

          <!-- 公式选择 -->
          <div class="field">
            <label>公式组合</label>
            <select v-model="config.formula_id" class="select">
              <option value="">-- 选择公式 --</option>
              <option v-for="f in formulas" :key="f.id" :value="f.id">
                [{{ f.sequence_number }}] {{ f.name }}
              </option>
            </select>
          </div>

          <!-- 日期范围 -->
          <div class="field">
            <label>回测区间</label>
            <div class="date-range">
              <input type="date" v-model="config.start_date" class="input date-input" />
              <span class="date-sep">至</span>
              <input type="date" v-model="config.end_date" class="input date-input" />
            </div>
          </div>

          <!-- 初始资金 -->
          <div class="field">
            <label>初始资金（元）</label>
            <input type="number" v-model.number="config.initial_capital" class="input" min="10000" step="10000" />
          </div>

          <!-- 仓位配置 -->
          <div class="field">
            <label>买入方式</label>
            <div class="position-config">
              <select v-model="config.position_type" class="select">
                <option value="percent_capital">按资金比例</option>
                <option value="fixed_amount">固定金额</option>
              </select>
              <input type="number" v-model.number="config.position_value" class="input input-small"
                :min="1" :max="config.position_type === 'percent_capital' ? 100 : 999999" />
              <span class="unit">{{ config.position_type === 'percent_capital' ? '%' : '元' }}</span>
            </div>
          </div>

          <!-- 入场价格类型 -->
          <div class="field">
            <label>买入价格（次日）</label>
            <select v-model="config.entry_price_type" class="select">
              <option value="open">开盘价</option>
              <option value="close">收盘价</option>
              <option value="avg">均价（最高+最低/2）</option>
            </select>
          </div>
        </div>

        <div class="panel-section">
          <h3>止损止盈规则</h3>

          <!-- 止损 -->
          <div class="field">
            <label>止损规则</label>
            <div class="sl-tp-row">
              <select v-model="config.stop_loss_type" class="select">
                <option value="percent">百分比</option>
                <option value="fixed">固定金额</option>
              </select>
              <input type="number" v-model.number="config.stop_loss_value" class="input input-small" step="0.5" />
              <span class="unit">{{ config.stop_loss_type === 'percent' ? '%' : '元' }}</span>
            </div>
          </div>

          <!-- 止盈 -->
          <div class="field">
            <label>止盈规则</label>
            <div class="sl-tp-row">
              <select v-model="config.take_profit_type" class="select">
                <option value="percent">百分比</option>
                <option value="fixed">固定金额</option>
              </select>
              <input type="number" v-model.number="config.take_profit_value" class="input input-small" step="0.5" />
              <span class="unit">{{ config.take_profit_type === 'percent' ? '%' : '元' }}</span>
            </div>
          </div>
        </div>

        <div class="panel-section">
          <button class="btn btn-run" @click="runBacktest" :disabled="running">
            {{ running ? '回测中...' : '开始回测' }}
          </button>
          <div class="error" v-if="runError">{{ runError }}</div>
        </div>
      </div>

      <!-- ==================== 右侧：结果面板 ==================== -->
      <div class="result-panel">
        <!-- 无结果提示 -->
        <div class="empty-result" v-if="!result">
          <p>配置参数后点击「开始回测」查看结果</p>
        </div>

        <!-- 回测结果 -->
        <div class="result-content" v-else>
          <!-- 统计摘要 -->
          <div class="stats-summary">
            <div class="stat-card">
              <div class="stat-label">总收益率</div>
              <div class="stat-value" :class="{ positive: result.total_return > 0, negative: result.total_return < 0 }">
                {{ result.total_return > 0 ? '+' : '' }}{{ result.total_return }}%
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-label">交易次数</div>
              <div class="stat-value">{{ result.total_trades }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">胜率</div>
              <div class="stat-value">{{ result.win_rate }}%</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">最大回撤</div>
              <div class="stat-value negative">{{ result.max_drawdown }}%</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">夏普比率</div>
              <div class="stat-value">{{ result.sharpe_ratio }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">盈亏比</div>
              <div class="stat-value">{{ result.profit_factor }}</div>
            </div>
          </div>

          <!-- Equity Curve Chart -->
          <div class="chart-section">
            <h3>资金曲线</h3>
            <div ref="equityChartRef" class="echart-container"></div>
          </div>

          <!-- K-line Chart with Buy/Sell markers -->
          <div class="chart-section">
            <h3>K线走势（买卖点标记）</h3>
            <div ref="klineChartRef" class="echart-container"></div>
          </div>

          <!-- Trade Log -->
          <div class="trade-log-section">
            <h3>交易明细</h3>
            <div class="trade-table-wrapper">
              <table class="trade-table">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>买入日期</th>
                    <th>买入价格</th>
                    <th>卖出日期</th>
                    <th>卖出价格</th>
                    <th>持仓</th>
                    <th>盈亏（元）</th>
                    <th>收益率</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(trade, i) in result.trade_log" :key="i"
                      :class="{ win: trade.pnl > 0, loss: trade.pnl <= 0 }">
                    <td>{{ i + 1 }}</td>
                    <td>{{ trade.entry_date }}</td>
                    <td>{{ trade.entry_price }}</td>
                    <td>{{ trade.exit_date }}</td>
                    <td>{{ trade.exit_price }}</td>
                    <td>{{ trade.shares }}</td>
                    <td :class="{ positive: trade.pnl > 0, negative: trade.pnl < 0 }">
                      {{ trade.pnl > 0 ? '+' : '' }}{{ trade.pnl }}
                    </td>
                    <td :class="{ positive: trade.return_pct > 0, negative: trade.return_pct < 0 }">
                      {{ trade.return_pct > 0 ? '+' : '' }}{{ trade.return_pct }}%
                    </td>
                    <td>
                      <span v-if="trade.reason === 'stop_loss'" class="tag tag-loss">止损</span>
                      <span v-else-if="trade.reason === 'take_profit'" class="tag tag-profit">止盈</span>
                      <span v-else class="tag tag-close">平仓</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import * as api from '@/utils/api'
import * as echarts from 'echarts'

const stocks = ref([])
const formulas = ref([])
const running = ref(false)
const runError = ref('')
const result = ref(null)
const equityChartRef = ref(null)
const klineChartRef = ref(null)
let equityChart = null
let klineChart = null

// 回测配置
const config = ref({
  stock_code: '',
  formula_id: '',
  start_date: '2024-01-01',
  end_date: '2024-12-31',
  initial_capital: 100000,
  position_type: 'percent_capital',
  position_value: 10,
  entry_price_type: 'open',
  stop_loss_type: 'percent',
  stop_loss_value: -5,
  take_profit_type: 'percent',
  take_profit_value: 15
})

// K线数据
const klineData = ref([])

onMounted(async () => {
  await loadData()
})

async function loadData() {
  try {
    stocks.value = await api.listStocks()
    formulas.value = await api.listFormulaCombinations()

    // 设置默认日期为最近一年
    const today = new Date()
    const lastYear = new Date(today)
    lastYear.setFullYear(lastYear.getFullYear() - 1)
    config.value.end_date = today.toISOString().split('T')[0]
    config.value.start_date = lastYear.toISOString().split('T')[0]
  } catch (e) {
    console.error('Failed to load data:', e)
  }
}

async function runBacktest() {
  runError.value = ''
  result.value = null

  if (!config.value.stock_code) {
    runError.value = '请选择股票'
    return
  }
  if (!config.value.formula_id) {
    runError.value = '请选择公式'
    return
  }

  running.value = true

  try {
    // 加载K线数据
    const klineRes = await api.getKline(config.value.stock_code)
    klineData.value = klineRes.data || []

    // 运行回测
    const res = await api.runBacktest({
      formula_id: parseInt(config.value.formula_id),
      stock_code: config.value.stock_code,
      start_date: config.value.start_date,
      end_date: config.value.end_date,
      initial_capital: config.value.initial_capital,
      position_type: config.value.position_type,
      position_value: config.value.position_value,
      entry_price_type: config.value.entry_price_type,
      stop_loss_type: config.value.stop_loss_type,
      stop_loss_value: config.value.stop_loss_value,
      take_profit_type: config.value.take_profit_type,
      take_profit_value: config.value.take_profit_value
    })

    result.value = res

    // 渲染图表
    await nextTick()
    renderEquityChart()
    renderKlineChart()

  } catch (e) {
    runError.value = '回测失败: ' + (e.message || String(e))
    console.error('Backtest error:', e)
  } finally {
    running.value = false
  }
}

function renderEquityChart() {
  if (!equityChartRef.value || !result.value || !result.value.equity_curve) return

  if (!equityChart) {
    equityChart = echarts.init(equityChartRef.value)
  }

  const data = result.value.equity_curve.map(d => [d.date, d.equity])
  const initial = config.value.initial_capital

  const option = {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0]
        return `${p.value[0]}<br/>资金: ¥${p.value[1].toFixed(2)}`
      }
    },
    grid: { left: '60', right: '20', top: '20', bottom: '40' },
    xAxis: {
      type: 'category',
      data: result.value.equity_curve.map(d => d.date),
      axisLabel: { color: '#888', fontSize: 10, rotate: 45 }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#888', formatter: v => '¥' + (v / 10000).toFixed(0) + 'w' }
    },
    series: [{
      type: 'line',
      data: data,
      smooth: true,
      lineStyle: { color: '#e94560', width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(233,69,96,0.3)' },
            { offset: 1, color: 'rgba(233,69,96,0)' }
          ]
        }
      },
      markLine: {
        silent: true,
        data: [{ yAxis: initial, lineStyle: { color: '#555', type: 'dashed' }, label: { formatter: '初始资金', color: '#888' } }]
      }
    }]
  }

  equityChart.setOption(option)
}

function renderKlineChart() {
  if (!klineChartRef.value || klineData.value.length === 0) return

  if (!klineChart) {
    klineChart = echarts.init(klineChartRef.value)
  }

  // 过滤日期范围内的K线
  const startDate = config.value.start_date
  const endDate = config.value.end_date
  const filteredKline = klineData.value.filter(d => d.date >= startDate && d.date <= endDate)

  // 准备K线数据
  const dates = filteredKline.map(d => d.date)
  const ohlc = filteredKline.map(d => [d.open, d.close, d.low, d.high])
  const volumes = filteredKline.map(d => d.volume)

  // 准备买卖点标记
  const buyMarks = []
  const sellMarks = []
  if (result.value && result.value.trade_log) {
    for (const trade of result.value.trade_log) {
      // 找到对应的K线索引
      const entryIdx = dates.findIndex(d => d === trade.entry_date)
      const exitIdx = dates.findIndex(d => d === trade.exit_date)

      if (entryIdx >= 0) {
        const price = trade.entry_price
        buyMarks.push([entryIdx, price, '买入\n¥' + price])
      }
      if (exitIdx >= 0) {
        const price = trade.exit_price
        const color = trade.reason === 'stop_loss' ? '#ef5350' : (trade.reason === 'take_profit' ? '#26a69a' : '#888')
        sellMarks.push([exitIdx, price, trade.reason === 'stop_loss' ? '止损' : (trade.reason === 'take_profit' ? '止盈' : '平仓'), color])
      }
    }
  }

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params) => {
        const kline = params.find(p => p.seriesName === 'K线')
        if (!kline) return ''
        const d = kline.data
        return `${kline.axisValue}<br/>
          开盘: ¥${d[0]}<br/>
          收盘: ¥${d[1]}<br/>
          低: ¥${d[2]}<br/>
          高: ¥${d[3]}`
      }
    },
    legend: { show: false },
    grid: [
      { left: '60', right: '20', top: '20', height: '60%' },
      { left: '60', right: '20', top: '78%', height: '15%' }
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { color: '#888', fontSize: 10, rotate: 45 } }
    ],
    yAxis: [
      { scale: true, gridIndex: 0, axisLabel: { color: '#888' } },
      { scale: true, gridIndex: 1, axisLabel: { color: '#888', formatter: v => (v / 10000).toFixed(0) + 'w' } }
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: '#ef5350',      // 上涨-红
          color0: '#26a69a',     // 下跌-绿
          borderColor: '#ef5350',
          borderColor0: '#26a69a'
        }
      },
      {
        name: '成交量',
        type: 'bar',
        data: volumes,
        xAxisIndex: 1,
        yAxisIndex: 1,
        itemStyle: {
          color: params => {
            const i = params.dataIndex
            return ohlc[i] && ohlc[i][1] >= ohlc[i][0] ? '#ef5350' : '#26a69a'
          }
        }
      },
      {
        name: '买入',
        type: 'scatter',
        data: buyMarks,
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: 'triangle',
        symbolSize: 12,
        itemStyle: { color: '#2196f3' },
        label: {
          show: true,
          position: 'below',
          formatter: p => p.data[2],
          color: '#2196f3',
          fontSize: 10
        },
        z: 10
      },
      {
        name: '卖出',
        type: 'scatter',
        data: sellMarks.map(m => [m[0], m[1], m[2]]),
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: 'triangle',
        symbolSize: 12,
        itemStyle: {
          color: params => {
            const i = params.dataIndex
            return sellMarks[i] ? sellMarks[i][3] : '#888'
          }
        },
        label: {
          show: true,
          position: 'top',
          formatter: p => p.data[2],
          color: '#ef5350',
          fontSize: 10
        },
        z: 10
      }
    ]
  }

  klineChart.setOption(option)
}

// 监听窗口大小变化
window.addEventListener('resize', () => {
  if (equityChart) equityChart.resize()
  if (klineChart) klineChart.resize()
})
</script>

<style scoped>
.backtest-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0a0e1a;
  color: #e0e0e0;
}

.page-header {
  padding: 12px 20px;
  border-bottom: 1px solid #1a2544;
  flex-shrink: 0;
}

.page-header h2 {
  margin: 0;
  font-size: 16px;
  color: #e0e0e0;
}

.backtest-container {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* 配置面板 */
.config-panel {
  width: 280px;
  background: #111827;
  border-right: 1px solid #1a2544;
  overflow-y: auto;
  flex-shrink: 0;
}

.panel-section {
  padding: 16px;
  border-bottom: 1px solid #1a2544;
}

.panel-section h3 {
  margin: 0 0 12px;
  font-size: 13px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.field {
  margin-bottom: 12px;
}

.field label {
  display: block;
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
}

.select, .input {
  width: 100%;
  background: #0f3460;
  border: 1px solid #1f2b4a;
  color: #e0e0e0;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 13px;
  box-sizing: border-box;
}

.input-small {
  width: 70px;
}

.date-range {
  display: flex;
  align-items: center;
  gap: 4px;
}

.date-input {
  flex: 1;
}

.date-sep {
  color: #555;
  font-size: 12px;
}

.position-config {
  display: flex;
  align-items: center;
  gap: 6px;
}

.position-config .select {
  flex: 1;
}

.sl-tp-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sl-tp-row .select {
  width: 100px;
}

.unit {
  color: #888;
  font-size: 12px;
  width: 20px;
}

.btn-run {
  width: 100%;
  background: #e94560;
  color: #fff;
  border: none;
  padding: 10px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-run:hover:not(:disabled) {
  opacity: 0.85;
}

.btn-run:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  color: #ef5350;
  font-size: 12px;
  margin-top: 8px;
}

/* 结果面板 */
.result-panel {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.empty-result {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #555;
}

/* 统计卡片 */
.stats-summary {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: #111827;
  border: 1px solid #1a2544;
  border-radius: 8px;
  padding: 12px;
  text-align: center;
}

.stat-label {
  font-size: 11px;
  color: #888;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #e0e0e0;
}

.stat-value.positive { color: #ef5350; }
.stat-value.negative { color: #26a69a; }

.chart-section {
  margin-bottom: 20px;
}

.chart-section h3 {
  font-size: 13px;
  color: #888;
  margin-bottom: 10px;
}

.echart-container {
  width: 100%;
  height: 250px;
  background: #111827;
  border: 1px solid #1a2544;
  border-radius: 8px;
}

/* 交易明细 */
.trade-log-section {
  margin-bottom: 20px;
}

.trade-log-section h3 {
  font-size: 13px;
  color: #888;
  margin-bottom: 10px;
}

.trade-table-wrapper {
  overflow-x: auto;
  background: #111827;
  border: 1px solid #1a2544;
  border-radius: 8px;
}

.trade-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.trade-table th,
.trade-table td {
  padding: 8px 12px;
  text-align: center;
  border-bottom: 1px solid #1a2544;
}

.trade-table th {
  background: #0f1629;
  color: #888;
  font-weight: normal;
}

.trade-table tr:last-child td {
  border-bottom: none;
}

.trade-table tr.win td {
  background: rgba(38,166,154,0.1);
}

.trade-table tr.loss td {
  background: rgba(239,83,80,0.1);
}

.positive { color: #ef5350; }
.negative { color: #26a69a; }

.tag {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
}

.tag-loss { background: rgba(239,83,80,0.2); color: #ef5350; }
.tag-profit { background: rgba(38,166,154,0.2); color: #26a69a; }
.tag-close { background: rgba(136,136,136,0.2); color: #888; }
</style>
