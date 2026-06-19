<template>
  <div class="explore-view">
    <div class="explore-header">
      <h2>探索配置</h2>
      <button class="btn btn-small" @click="showHistory = !showHistory" style="margin-left: auto;">
        {{ showHistory ? '← 返回' : '📋 历史报告' }}
      </button>
    </div>

    <!-- 历史报告列表 -->
    <div v-if="showHistory && !selectedReport" class="reports-list">
      <div class="reports-title">探索历史报告</div>
      <div v-if="reportsLoading" class="no-result">加载中...</div>
      <div v-else-if="reports.length === 0" class="no-result">暂无历史报告</div>
      <div v-for="r in reports" :key="r.id" class="report-card" @click="selectReport(r)">
        <div class="report-card-header">
          <span class="report-code">{{ r.code }}</span>
          <span class="report-status" :class="'status-' + r.status">{{ r.status }}</span>
        </div>
        <div class="report-meta">
          {{ r.iterations }} 次迭代 · {{ r.candidates_total }} 个候选公式 · {{ r.best_precision !== null ? (r.best_precision * 100).toFixed(1) + '%' : '—' }} 精度
        </div>
        <div class="report-meta">{{ r.final_message || '' }}</div>
        <div class="report-date">{{ r.created_at }}</div>
      </div>
    </div>

    <!-- 历史报告详情 -->
    <div v-else-if="showHistory && selectedReport" class="report-detail">
      <button class="btn btn-small" @click="selectedReport = null" style="margin-bottom: 12px">← 返回列表</button>
      <div class="result-info">
        <div class="result-title">{{ selectedReport.code }} — {{ selectedReport.status }}</div>
        <div class="result-meta">
          {{ selectedReport.iterations }} 次迭代 · {{ selectedReport.candidates_total }} 个候选公式
        </div>
        <div class="result-meta" v-if="selectedReport.total_seconds">
          耗时 {{ Math.floor(selectedReport.total_seconds / 60) }} 分 {{ selectedReport.total_seconds % 60 }} 秒
        </div>
        <div class="result-meta">{{ selectedReport.created_at }}</div>
        <div class="result-meta" v-if="selectedReport.final_message" style="margin-top: 8px; color: #e0e0e0">
          {{ selectedReport.final_message }}
        </div>
      </div>
      <div v-if="selectedReport.best_formula" class="candidates-list">
        <div class="candidates-title">最优公式:</div>
        <div class="candidate-card">
          <div class="candidate-expr">{{ selectedReport.best_formula }}</div>
          <div class="candidate-meta">
            精度 {{ selectedReport.best_precision !== null ? (selectedReport.best_precision * 100).toFixed(1) + '%' : '—' }}%
            | 覆盖 {{ selectedReport.best_coverage }} 个买点
          </div>
        </div>
      </div>
      <div v-else class="no-result">无最优公式</div>
    </div>

    <!-- 配置表单 -->
    <div class="explore-form" v-if="!showProgress">
      <div class="form-section">
        <label class="form-label">股票代码</label>
        <div class="mode-toggle">
          <label class="radio-label">
            <input type="radio" v-model="mode" value="single" /> 单只股票
          </label>
          <label class="radio-label">
            <input type="radio" v-model="mode" value="batch" /> 批量（多行输入）
          </label>
        </div>
        <input v-if="mode === 'single'" v-model="stockCode" placeholder="股票代码，如 000001" class="input" />
        <textarea v-else v-model="stockCodesText" placeholder="股票代码，每行一个&#10;例如:&#10;000001&#10;000002&#10;002001" class="textarea"></textarea>
      </div>

      <div class="form-section">
        <label class="form-label">U1买点标准配置</label>
        <div class="form-row">
          <span class="form-hint">买入价计算方式</span>
          <select v-model="u1Config.buy_price" class="select">
            <option value="MA5">MA5（5日均价）</option>
            <option value="close">收盘价</option>
          </select>
        </div>
        <div class="form-row">
          <span class="form-hint">持有交易日数</span>
          <input v-model.number="u1Config.hold_days" type="number" min="1" max="30" class="input-small" />
        </div>
        <div class="form-row">
          <span class="form-hint">盈利目标</span>
          <div class="input-group">
            <input v-model.number="u1Config.profit_pct" type="number" min="0.1" step="0.1" class="input-small" />
            <span class="unit">%</span>
          </div>
        </div>
      </div>

      <button class="btn btn-large" @click="startExplore" :disabled="!canStart || starting">
        {{ starting ? '启动中...' : '开始探索' }}
      </button>
      <div class="form-error" v-if="formError">{{ formError }}</div>
    </div>

    <!-- 探索结果页面（探索结束后显示，可重新开始） -->
    <div class="explore-result" v-else>
      <div class="result-info">
        <div class="result-title" v-if="exploreStatus === 'timeout'">⏱ 探索超时（10分钟）</div>
        <div class="result-title" v-else-if="exploreStatus === 'completed'">✓ 探索完成</div>
        <div class="result-title" v-else>✗ 探索终止</div>
        <div class="result-meta">已探索 {{ candidatesExplored }} 个候选公式</div>
      </div>

      <div class="candidates-list" v-if="bestCandidate">
        <div class="candidates-title">最优公式:</div>
        <div class="candidate-card">
          <div class="candidate-expr">{{ bestCandidate.formula_expr }}</div>
          <div class="candidate-meta">
            精度 {{ (bestCandidate.precision * 100).toFixed(1) }}% |
            覆盖 {{ bestCandidate.coverage_count }} 个买点
          </div>
          <div class="candidate-logic">{{ bestCandidate.logic_desc }}</div>
        </div>
      </div>
      <div v-else class="no-result">未找到符合条件的公式</div>

      <button class="btn btn-large" @click="resetForm" style="margin-top: 16px">重新探索</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import * as api from '@/utils/api'

const showHistory = ref(false)
const reports = ref([])
const reportsLoading = ref(false)
const selectedReport = ref(null)

async function loadReports() {
  reportsLoading.value = true
  try {
    reports.value = await api.getExploreReports()
  } catch (e) {
    reports.value = []
  } finally {
    reportsLoading.value = false
  }
}

async function selectReport(r) {
  try {
    selectedReport.value = await api.getExploreReport(r.id)
  } catch (e) {
    selectedReport.value = r
  }
}

// Watch showHistory to load reports when opened
import { watch } from 'vue'
watch(showHistory, (val) => {
  if (val && reports.value.length === 0) loadReports()
})

const mode = ref('single')
const stockCode = ref('')
const stockCodesText = ref('')
const u1Config = ref({ hold_days: 5, profit_pct: 2.0, buy_price: 'MA5' })
const formError = ref('')
const starting = ref(false)

// 显示进度还是结果（由App.vue的exploreActive控制，不再自己管理）
const showProgress = ref(false)  // 由App控制，这里仅用于本地结果展示
const exploreStatus = ref('')
const candidatesExplored = ref(0)
const bestCandidate = ref(null)

const canStart = computed(() => {
  if (mode.value === 'single') return stockCode.value.trim().length === 6
  return stockCodesText.value.trim().length > 0
})

async function startExplore() {
  formError.value = ''
  let settings
  try { settings = await api.getSettings() } catch (e) {}
  const apiKey = settings?.api_key || ''
  const apiBase = settings?.api_base || 'https://api.openai.com/v1'
  const model = settings?.model || 'gpt-4o'
  if (!apiKey) { formError.value = '请先在设置页面配置API Key'; return }

  const codes = mode.value === 'single'
    ? [stockCode.value.trim()]
    : stockCodesText.value.split('\n').map(c => c.trim()).filter(c => c)

  starting.value = true
  try {
    await api.startExploration({ codes, u1_config: u1Config.value, mode: mode.value, api_key: apiKey, api_base: apiBase, model })
  } catch (e) {
    formError.value = String(e)
  } finally {
    starting.value = false
  }
}

function resetForm() {
  showProgress.value = false
  exploreStatus.value = ''
  candidatesExplored.value = 0
  bestCandidate.value = null
}
</script>

<style scoped>
.explore-view { height: 100%; overflow-y: auto; padding: 24px; }
.explore-header { margin-bottom: 24px; }
.explore-header h2 { color: #e0e0e0; font-size: 20px; }
.explore-form { max-width: 480px; }
.form-section { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.form-label { display: block; font-size: 14px; color: #e0e0e0; margin-bottom: 12px; }
.mode-toggle { display: flex; gap: 20px; margin-bottom: 12px; }
.radio-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #a0a0a0; cursor: pointer; }
.form-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.form-hint { font-size: 13px; color: #888; }
.form-row .select, .form-row .input-small { padding: 6px 10px; background: #1a1a2e; border: 1px solid #0f3460; color: #e0e0e0; border-radius: 4px; font-size: 13px; }
.input-small { width: 80px; }
.input-group { display: flex; align-items: center; gap: 6px; }
.unit { font-size: 13px; color: #888; }
.btn-large { width: 100%; padding: 12px; font-size: 16px; background: #e94560; color: white; border: none; border-radius: 6px; cursor: pointer; }
.btn-large:hover { background: #d63850; }
.btn-large:disabled { background: #555; cursor: not-allowed; }
.form-error { margin-top: 12px; color: #e94560; font-size: 13px; }
.explore-result { max-width: 600px; }
.result-info { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.result-title { font-size: 18px; color: #e0e0e0; margin-bottom: 8px; }
.result-meta { font-size: 13px; color: #888; }
.candidates-list { margin-bottom: 16px; }
.candidates-title { font-size: 14px; color: #888; margin-bottom: 12px; }
.candidate-card { background: #1f2a47; border: 1px solid #0f3460; border-radius: 8px; padding: 16px; }
.candidate-expr { font-size: 15px; color: #e94560; margin-bottom: 6px; }
.candidate-meta { font-size: 12px; color: #888; margin-bottom: 4px; }
.candidate-logic { font-size: 12px; color: #a0a0a0; }
.no-result { color: #888; font-size: 14px; padding: 20px; text-align: center; }
.btn { padding: 8px 24px; background: #e94560; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
.input, .textarea { width: 100%; padding: 10px 12px; background: #1a1a2e; border: 1px solid #0f3460; color: #e0e0e0; border-radius: 4px; margin-top: 8px; font-size: 14px; box-sizing: border-box; }
.textarea { height: 120px; resize: none; }
.reports-list { max-width: 600px; }
.reports-title { font-size: 16px; color: #e0e0e0; margin-bottom: 16px; }
.report-card { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 16px; margin-bottom: 12px; cursor: pointer; transition: background 0.15s; }
.report-card:hover { background: #1f2b4a; }
.report-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.report-code { font-size: 16px; color: #e0e0e0; font-weight: 600; }
.report-status { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.status-completed { background: rgba(38,166,154,0.3); color: #26a69a; }
.status-timeout { background: rgba(255,193,7,0.2); color: #ffc107; }
.status-stopped { background: rgba(239,83,80,0.2); color: #ef5350; }
.report-meta { font-size: 13px; color: #888; margin-bottom: 4px; }
.report-date { font-size: 12px; color: #555; margin-top: 4px; }
.report-detail { max-width: 600px; }
.btn-small { padding: 6px 16px; font-size: 13px; }
</style>