<template>
  <div class="logic-config-view">
    <div class="page-header">
      <h2>组合逻辑配置</h2>
    </div>

    <div class="two-panel">
      <!-- ==================== Part 1: 预置条件（指标参数库）==================== -->
      <div class="panel panel-left">
        <div class="panel-header">
          <h3>预置条件库</h3>
          <button class="btn btn-small" @click="openAddIndicator">+ 新增预置条件</button>
        </div>

        <div class="indicator-list" v-if="indicators.length > 0">
          <div
            v-for="ind in indicators"
            :key="ind.id"
            class="indicator-card"
            :class="{ selected: selectedIndicator && selectedIndicator.id === ind.id }"
            @click="selectIndicator(ind)"
          >
            <div class="card-header">
              <span class="ind-seq">[{{ ind.sequence_number }}]</span>
              <span class="ind-name">{{ ind.name }}</span>
            </div>
            <div class="ind-params" v-if="ind.param_config">
              <!-- 显示指标名 + 阈值条件 -->
              <span class="param-tag condition-tag" v-if="ind.param_config.threshold">
                {{ ind.name }} {{ ind.param_config.threshold.op || '=' }} {{ ind.param_config.threshold.value }}
              </span>
              <!-- 显示参数值（排除threshold） -->
              <span v-for="(v, k) in ind.param_config" :key="k" class="param-tag" v-if="k !== 'threshold'">
                {{ k }}{{ typeof v === 'object' ? (v.op || '=') : '=' }}{{ typeof v === 'object' ? (v.min !== undefined ? v.min : v.value) : v }}
              </span>
            </div>
            <div class="ind-desc" v-if="ind.description">{{ ind.description }}</div>
            <div class="card-actions">
              <button class="btn btn-tiny" @click.stop="editIndicator(ind)">编辑</button>
              <button class="btn btn-tiny btn-danger" @click.stop="delIndicator(ind.id)">删除</button>
            </div>
          </div>
        </div>
        <div class="empty-hint" v-else>暂无预置条件，点击上方按钮添加</div>

        <!-- 新增/编辑预置条件 Modal -->
        <div class="modal" v-if="showIndicatorModal" @click.self="closeIndicatorModal">
          <div class="modal-content">
            <h3>{{ editingIndicator ? '编辑预置条件' : '新增预置条件' }}</h3>

            <!-- 指标下拉 -->
            <div class="field">
              <label>选择指标</label>
              <select v-model="indForm.builtinName" class="select" @change="onBuiltinSelected" :disabled="!!editingIndicator">
                <optgroup label="-- 均线类 MA --">
                  <option v-for="ind in builtinGroup('ma')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- RSI 类 --">
                  <option v-for="ind in builtinGroup('rsi')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- KDJ 类 --">
                  <option v-for="ind in builtinGroup('kdj')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- MACD 类 --">
                  <option v-for="ind in builtinGroup('macd')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- 布林带类 --">
                  <option v-for="ind in builtinGroup('boll')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- 波动率/ATR --">
                  <option v-for="ind in builtinGroup('atr')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- 成交量类 --">
                  <option v-for="ind in builtinGroup('vol')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- 动量/收益率 --">
                  <option v-for="ind in builtinGroup('return')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- 偏离度 --">
                  <option v-for="ind in builtinGroup('deviation')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- 布尔/关系 --">
                  <option v-for="ind in builtinGroup('bool')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
                <optgroup label="-- 其他 --">
                  <option v-for="ind in builtinGroup('other')" :key="ind.name" :value="ind.name">
                    {{ ind.name }} - {{ ind.desc.substring(0, 15) }}...
                  </option>
                </optgroup>
              </select>
            </div>

            <!-- 指标说明卡片 -->
            <div class="builtin-desc-card" v-if="indForm.selectedBuiltin">
              <div class="builtin-desc-title">{{ indForm.selectedBuiltin.name }} 指标说明</div>
              <div class="builtin-desc-text">{{ indForm.selectedBuiltin.desc }}</div>
            </div>

            <!-- 序号（可编辑） -->
            <div class="field">
              <label>序号（系统自动生成，可修改）</label>
              <input v-model="indForm.sequenceNumber" class="input" placeholder="如: I001（留空自动生成）" />
            </div>

            <!-- 指标名称（自动填充，只读） -->
            <div class="field">
              <label>指标名称</label>
              <input :value="indForm.name" class="input" disabled />
            </div>

            <!-- 描述说明（多行文本框） -->
            <div class="field">
              <label>描述说明（选填，描述此预置条件的用途）</label>
              <textarea v-model="indForm.description" class="textarea" rows="3"
                placeholder="例如：用于短线RSI超买策略，当RSI超过70时认为超买"></textarea>
            </div>

            <!-- 阈值条件配置 -->
            <div class="field" v-if="indForm.selectedBuiltin">
              <label>阈值条件（指标值与阈值的比较，如 RSI &gt; 30）</label>
              <div class="threshold-config">
                <span class="threshold-label">当</span>
                <span class="threshold-indicator">{{ indForm.name }}</span>
                <select v-model="indForm.thresholdOp" class="select op-select">
                  <option value=">">&gt;（大于）</option>
                  <option value="<">&lt;（小于）</option>
                  <option value=">=">&gt;=（大于等于）</option>
                  <option value="<=">&lt;=（小于等于）</option>
                  <option value="=">=（等于）</option>
                </select>
                <input v-model.number="indForm.thresholdValue" type="number" class="input input-tiny" step="1" placeholder="阈值" />
                <span class="threshold-label">时触发</span>
              </div>
            </div>

            <!-- 参数值配置 -->
            <div class="field" v-if="indForm.selectedBuiltin && indForm.paramConfigList && indForm.paramConfigList.length > 0">
              <label>参数值配置</label>
              <div class="param-config-list">
                <div v-for="(paramCfg, pName) in indForm.selectedBuiltin.params" :key="pName" class="param-row">
                  <span class="param-name">{{ pName }}</span>
                  <select
                    v-model="(indForm.paramConfigList[$index] || {}).op"
                    class="select op-select"
                  >
                    <option value=">">大于 (&gt;)</option>
                    <option value="<">小于 (&lt;)</option>
                    <option value=">=">大于等于 (&gt;=)</option>
                    <option value="<=">小于等于 (&lt;=)</option>
                    <option value="=">等于 (=)</option>
                  </select>
                  <input
                    v-model.number="(indForm.paramConfigList[$index] || {}).value"
                    type="number"
                    class="input input-tiny"
                    :min="paramCfg.min"
                    :max="paramCfg.max"
                    :step="paramCfg.step || 1"
                    placeholder="阈值"
                  />
                  <span class="param-hint">范围: [{{ paramCfg.min }}, {{ paramCfg.max }}]</span>
                </div>
              </div>
            </div>

            <!-- 无参数指标提示 -->
            <div class="param-tip" v-if="indForm.selectedBuiltin && Object.keys(indForm.selectedBuiltin.params || {}).length === 0">
              此指标为无参数指标（如布尔型、振幅等），无需配置参数
            </div>

            <div class="modal-actions">
              <button class="btn" @click="saveIndicator">{{ editingIndicator ? '保存修改' : '添加' }}</button>
              <button class="btn btn-ghost" @click="closeIndicatorModal">取消</button>
            </div>
            <div class="error" v-if="indError">{{ indError }}</div>
          </div>
        </div>
      </div>

      <!-- ==================== Part 2: 公式组合配置 ==================== -->
      <div class="panel panel-right">
        <div class="panel-header">
          <h3>公式组合库</h3>
          <button class="btn btn-small" @click="showAddFormula = true">+ 新增公式</button>
        </div>

        <div class="formula-list" v-if="formulas.length > 0">
          <div
            v-for="fm in formulas"
            :key="fm.id"
            class="formula-card"
            :class="{ selected: selectedFormula && selectedFormula.id === fm.id }"
            @click="selectFormula(fm)"
          >
            <div class="card-header">
              <span class="fm-seq">[{{ fm.sequence_number }}]</span>
              <span class="fm-name">{{ fm.name }}</span>
            </div>
            <div class="fm-expr">{{ fm.formula_expr }}</div>
            <div class="fm-desc" v-if="fm.logic_desc">{{ fm.logic_desc }}</div>
            <div class="fm-refs" v-if="fm.indicator_refs && fm.indicator_refs.length > 0">
              <span v-for="refId in fm.indicator_refs" :key="refId" class="ref-tag">
                {{ getIndicatorName(refId) }}
              </span>
            </div>
            <div class="card-actions">
              <button class="btn btn-tiny" @click="editFormula(fm)">编辑</button>
              <button class="btn btn-tiny btn-danger" @click="delFormula(fm.id)">删除</button>
            </div>
          </div>
        </div>
        <div class="empty-hint" v-else>暂无公式组合，点击上方按钮添加</div>

        <!-- 新增/编辑公式 Modal -->
        <div class="modal" v-if="showAddFormula || editingFormula" @click.self="closeFormulaModal">
          <div class="modal-content modal-wide">
            <h3>{{ editingFormula ? '编辑公式' : '新增公式组合' }}</h3>

            <!-- 序号 -->
            <div class="field">
              <label>序号（系统自动生成，可修改）</label>
              <input v-model="fmForm.sequenceNumber" class="input" placeholder="如: F001（留空自动生成）" />
            </div>

            <!-- 公式名称 -->
            <div class="field">
              <label>公式名称</label>
              <input v-model="fmForm.name" class="input" placeholder="如: RSI成交量共振, 突破策略" />
            </div>

            <!-- 引用预置条件 -->
            <div class="field">
              <label>引用预置条件（选中后自动生成表达式）</label>
              <div class="indicator-picker">
                <div
                  v-for="ind in indicators"
                  :key="ind.id"
                  class="ind-pick-item"
                  :class="{ selected: fmForm.indicatorRefs.includes(ind.id) }"
                  @click="toggleIndicatorRef(ind.id)"
                >
                  [{{ ind.sequence_number }}] {{ ind.name }}
                </div>
              </div>
              <div class="empty-hint" v-if="indicators.length === 0">请先在左侧添加预置条件</div>
            </div>

            <!-- 公式表达式（自动生成） -->
            <div class="field">
              <label>公式表达式（根据所选预置条件自动生成）</label>
              <div class="expr-builder">
                <div class="expr-hint">
                  表达式由所选预置条件的序号组成，使用 AND/OR/括号 连接<br />
                  示例: <code>I001 AND I002</code> 或 <code>I001 OR (I002 AND I003)</code>
                </div>
                <textarea v-model="fmForm.formula_expr" class="textarea" rows="3"
                  placeholder="从左侧选择预置条件后将自动生成"></textarea>
                <div class="quick-ops">
                  <button class="btn btn-tiny" @click="insertOp(' AND ')">AND</button>
                  <button class="btn btn-tiny" @click="insertOp(' OR ')">OR</button>
                  <button class="btn btn-tiny" @click="insertOp('(')">(</button>
                  <button class="btn btn-tiny" @click="insertOp(')')">)</button>
                  <button class="btn btn-tiny" @click="regenerateExpr" :disabled="fmForm.indicatorRefs.length === 0" title="从已选预置条件重新生成表达式">
                    重新生成
                  </button>
                </div>
              </div>
            </div>

            <!-- 逻辑描述（大模型自动生成） -->
            <div class="field">
              <label>逻辑描述（大模型自动生成）</label>
              <div class="logic-desc-row">
                <textarea v-model="fmForm.logicDesc" class="textarea" rows="2" readonly
                  placeholder="大模型将根据公式表达式和引用的预置条件自动生成描述"></textarea>
                <button class="btn btn-tiny" @click="regenerateDesc" :disabled="regenerating">
                  {{ regenerating ? '生成中...' : '重新生成' }}
                </button>
              </div>
            </div>

            <div class="modal-actions">
              <button class="btn" @click="saveFormula">{{ editingFormula ? '保存修改' : '添加' }}</button>
              <button class="btn btn-ghost" @click="closeFormulaModal">取消</button>
            </div>
            <div class="error" v-if="fmError">{{ fmError }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import * as api from '@/utils/api'

const indicators = ref([])
const formulas = ref([])
const builtinIndicators = ref([])
const selectedIndicator = ref(null)
const selectedFormula = ref(null)

// Indicator modal state
const showIndicatorModal = ref(false)
const editingIndicator = ref(null)
const indForm = ref({
  builtinName: '',
  sequenceNumber: '',
  name: '',
  selectedBuiltin: null,
  description: '',
  paramConfigList: []
})
const indError = ref('')

// Formula modal state
const showAddFormula = ref(false)
const editingFormula = ref(null)
const fmForm = ref({
  sequenceNumber: '',
  name: '',
  formula_expr: '',
  logicDesc: '',
  indicatorRefs: [],
  autoDesc: true
})
const fmError = ref('')
const regenerating = ref(false)

onMounted(async () => {
  await loadAll()
})

async function loadAll() {
  try {
    indicators.value = await api.listIndicators()
    formulas.value = await api.listFormulaCombinations()
    builtinIndicators.value = await api.getBuiltinIndicators()
  } catch (e) {
    console.error('Failed to load:', e)
  }
}

// ----- Builtin indicators grouping -----
const builtinGroups = {
  ma: ['MA5','MA10','MA20','MA30','MA60','MA90','MA120','MA250'],
  rsi: ['RSI_6','RSI_12','RSI_24'],
  kdj: ['KDJ_K','KDJ_D','KDJ_J'],
  macd: ['MACD_DIF','MACD_DEA','MACD_HIST'],
  boll: ['BOLL_U','BOLL_M','BOLL_L'],
  atr: ['ATR','ATR_7','ATR_21'],
  vol: ['VOL_RATIO','VOL_MA5','VOL_MA10'],
  return: ['RETURN','CLOSE_RATE_1','CLOSE_RATE_3','CLOSE_RATE_5'],
  deviation: ['MA20_DEVIATION','MA60_DEVIATION'],
  bool: ['MA5_GT_MA10','MA5_GT_MA20','MA10_GT_MA20','MA5_GT_MA60','MA20_GT_MA60','CLOSE_GT_MA5','CLOSE_GT_MA10','CLOSE_GT_MA20','CLOSE_GT_MA60'],
  other: ['AMPLITUDE']
}

function builtinGroup(group) {
  return builtinIndicators.value.filter(ind => builtinGroups[group]?.includes(ind.name))
}

// ----- Indicator form -----
function openAddIndicator() {
  editingIndicator.value = null
  indForm.value = {
    builtinName: '',
    sequenceNumber: '',
    name: '',
    selectedBuiltin: null,
    description: '',
    paramConfigList: [{ name: '', op: '=', value: 0 }],
    thresholdOp: '>',
    thresholdValue: 30
  }
  showIndicatorModal.value = true
}

function onBuiltinSelected() {
  const name = indForm.value.builtinName
  const bi = builtinIndicators.value.find(b => b.name === name)
  if (!bi) return

  indForm.value.selectedBuiltin = bi
  indForm.value.name = bi.name

  // Auto-fill param config from builtin params (single value, with operator)
  const params = bi.params || {}
  const list = []
  for (const [pName, pCfg] of Object.entries(params)) {
    list.push({
      name: pName,
      op: '=',
      value: pCfg.default !== undefined ? pCfg.default : (pCfg.min !== undefined ? pCfg.min : 0)
    })
  }
  indForm.value.paramConfigList = list
}

function selectIndicator(ind) {
  selectedIndicator.value = ind
}

function selectFormula(fm) {
  selectedFormula.value = fm
}

function getIndicatorName(id) {
  const ind = indicators.value.find(i => i.id === id)
  return ind ? `[${ind.sequence_number || ind.name}] ${ind.name}` : `指标${id}`
}

// ----- Indicator CRUD -----
function editIndicator(ind) {
  editingIndicator.value = ind
  indForm.value = {
    builtinName: ind.name,
    sequenceNumber: ind.sequence_number || '',
    name: ind.name,
    selectedBuiltin: builtinIndicators.value.find(b => b.name === ind.name) || null,
    description: ind.description || '',
    paramConfigList: [],
    thresholdOp: '>',
    thresholdValue: 30
  }
  // Fill param config (handle both old scalar format and new {op, value} format)
  // Skip 'threshold' key - handle it separately below
  if (ind.param_config) {
    const thresholdCfg = ind.param_config['threshold']
    if (thresholdCfg && typeof thresholdCfg === 'object') {
      indForm.value.thresholdOp = thresholdCfg.op || '>'
      indForm.value.thresholdValue = thresholdCfg.value !== undefined ? thresholdCfg.value : 0
    }

    for (const [k, v] of Object.entries(ind.param_config)) {
      if (k === 'threshold') continue  // skip, handled above
      let op = '='
      let value = 0
      if (typeof v === 'object') {
        op = v.op !== undefined ? v.op : '='
        value = v.value !== undefined ? v.value : (v.min !== undefined ? v.min : 0)
      } else {
        value = v
      }
      indForm.value.paramConfigList.push({ name: k, op, value })
    }
  }
  showIndicatorModal.value = true
}

function closeIndicatorModal() {
  showIndicatorModal.value = false
  editingIndicator.value = null
  indError.value = ''
}

async function saveIndicator() {
  indError.value = ''

  if (!indForm.value.name.trim()) {
    indError.value = '请选择指标'
    return
  }

  // Build param_config dict with {op, value} format
  const param_config = {}
  for (const p of indForm.value.paramConfigList) {
    if (p.name && p.name.trim()) {
      param_config[p.name.trim()] = { op: p.op || '=', value: p.value }
    }
  }

  // 添加阈值条件
  param_config['threshold'] = {
    op: indForm.value.thresholdOp || '>',
    value: indForm.value.thresholdValue || 0
  }

  const payload = {
    sequence_number: indForm.value.sequenceNumber.trim(),
    name: indForm.value.name.trim(),
    param_config: param_config,
    description: indForm.value.description.trim()
  }

  try {
    if (editingIndicator.value) {
      await api.updateIndicator(editingIndicator.value.id, payload)
    } else {
      await api.createIndicator(payload)
    }
    await loadAll()
    closeIndicatorModal()
  } catch (e) {
    indError.value = e.message || '保存失败'
  }
}

async function delIndicator(id) {
  if (!confirm('确认删除此预置条件？')) return
  try {
    await api.deleteIndicator(id)
    await loadAll()
    if (selectedIndicator.value && selectedIndicator.value.id === id) {
      selectedIndicator.value = null
    }
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

// ----- Formula CRUD -----
function editFormula(fm) {
  editingFormula.value = fm
  const refs = [...(fm.indicator_refs || [])]
  // Auto-generate expression from indicator refs (convert old format to new)
  let expr = ''
  if (refs.length > 0) {
    const seqs = refs.map(id => {
      const ind = indicators.value.find(i => i.id === id)
      return ind ? (ind.sequence_number || `I${ind.id}`) : `I${id}`
    })
    expr = seqs.join(' AND ')
  } else {
    expr = fm.formula_expr || ''
  }
  fmForm.value = {
    sequenceNumber: fm.sequence_number || '',
    name: fm.name,
    formula_expr: expr,
    logicDesc: fm.logic_desc || '',
    indicatorRefs: refs,
    autoDesc: false
  }
  showAddFormula.value = true
}

function closeFormulaModal() {
  showAddFormula.value = false
  editingFormula.value = null
  fmForm.value = { sequenceNumber: '', name: '', formula_expr: '', logicDesc: '', indicatorRefs: [], autoDesc: true }
  fmError.value = ''
}

function toggleIndicatorRef(id) {
  const idx = fmForm.value.indicatorRefs.indexOf(id)
  if (idx >= 0) {
    fmForm.value.indicatorRefs.splice(idx, 1)
  } else {
    fmForm.value.indicatorRefs.push(id)
  }
  // Auto-generate expression from selected indicators
  regenerateExpr()
}

function insertOp(op) {
  fmForm.value.formula_expr += op
}

// Auto-generate formula expression from selected indicator refs
function regenerateExpr() {
  const refs = fmForm.value.indicatorRefs
  if (refs.length === 0) {
    fmForm.value.formula_expr = ''
    return
  }
  // Build expression like "I001 AND I002 OR I003"
  const seqs = refs.map(id => {
    const ind = indicators.value.find(i => i.id === id)
    return ind ? ind.sequence_number || `I${ind.id}` : `I${id}`
  })
  // Default: join with AND
  fmForm.value.formula_expr = seqs.join(' AND ')
}

async function regenerateDesc() {
  if (!fmForm.value.formula_expr.trim()) {
    fmError.value = '请先填写公式表达式'
    return
  }
  regenerating.value = true
  fmError.value = ''
  try {
    // Create a temporary formula to get LLM description
    // Actually we need a dedicated endpoint for this
    // For now, just trigger regeneration via the API
    const payload = {
      sequence_number: fmForm.value.sequenceNumber,
      name: fmForm.value.name || '临时',
      formula_expr: fmForm.value.formula_expr,
      logic_desc: '',  // empty to trigger auto-generation
      indicator_refs: fmForm.value.indicatorRefs,
      auto_desc: true
    }
    // Create temporarily to get the description
    if (editingFormula.value) {
      // Update and regenerate
      const result = await api.updateFormulaCombination(editingFormula.value.id, { ...payload, auto_desc: true })
      fmForm.value.logicDesc = result.logic_desc || '生成失败'
    } else {
      // Create new with auto-desc
      const result = await api.createFormulaCombination(payload)
      fmForm.value.logicDesc = result.logic_desc || '生成失败'
    }
  } catch (e) {
    fmError.value = '生成描述失败: ' + (e.message || e)
  } finally {
    regenerating.value = false
  }
}

async function saveFormula() {
  fmError.value = ''
  if (!fmForm.value.name.trim()) {
    fmError.value = '请填写公式名称'
    return
  }
  if (!fmForm.value.formula_expr.trim()) {
    fmError.value = '请填写公式表达式'
    return
  }

  const payload = {
    sequence_number: fmForm.value.sequenceNumber.trim(),
    name: fmForm.value.name.trim(),
    formula_expr: fmForm.value.formula_expr.trim(),
    logic_desc: fmForm.value.logicDesc.trim(),
    indicator_refs: fmForm.value.indicatorRefs,
    auto_desc: !fmForm.value.logicDesc.trim()  // auto-generate if no manual description
  }

  try {
    if (editingFormula.value) {
      await api.updateFormulaCombination(editingFormula.value.id, payload)
    } else {
      await api.createFormulaCombination(payload)
    }
    await loadAll()
    closeFormulaModal()
  } catch (e) {
    fmError.value = e.message || '保存失败'
  }
}

async function delFormula(id) {
  if (!confirm('确认删除此公式组合？')) return
  try {
    await api.deleteFormulaCombination(id)
    await loadAll()
    if (selectedFormula.value && selectedFormula.value.id === id) {
      selectedFormula.value = null
    }
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}
</script>

<style scoped>
.logic-config-view {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.page-header {
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
}

.two-panel {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.panel {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-left {
  flex: 0 0 380px;
}

.panel-right {
  flex: 1;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
}

/* Lists */
.indicator-list, .formula-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.indicator-card, .formula-card {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  padding: 10px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.indicator-card:hover, .formula-card:hover {
  border-color: #4a9eff;
}

.indicator-card.selected, .formula-card.selected {
  border-color: #4a9eff;
  background: #f0f7ff;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.ind-seq, .fm-seq {
  font-size: 12px;
  font-weight: 700;
  color: #4a9eff;
  background: #e8f4ff;
  padding: 1px 6px;
  border-radius: 4px;
}

.ind-name, .fm-name {
  font-weight: 600;
  font-size: 14px;
}

.ind-params {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 4px;
}

.param-tag, .ref-tag {
  font-size: 11px;
  background: #e8f4ff;
  color: #2a7ae2;
  padding: 1px 6px;
  border-radius: 4px;
}

.ind-desc, .fm-desc {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
  line-height: 1.4;
}

.fm-expr {
  font-family: monospace;
  font-size: 12px;
  background: #f8f8f8;
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 4px;
  word-break: break-all;
}

.fm-refs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 4px;
}

.card-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
}

/* Modal */
.modal-content {
  max-width: 520px;
}

.modal-wide {
  max-width: 620px;
}

.field {
  margin-bottom: 12px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
  color: #333;
}

/* Builtin desc card */
.builtin-desc-card {
  background: #f0f7ff;
  border: 1px solid #cce4ff;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
}

.builtin-desc-title {
  font-weight: 600;
  font-size: 13px;
  color: #1a6fb3;
  margin-bottom: 4px;
}

.builtin-desc-text {
  font-size: 12px;
  color: #555;
  line-height: 1.5;
}

/* Param config */
.param-config-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.param-name {
  font-size: 12px;
  font-weight: 600;
  min-width: 60px;
  color: #333;
}

.param-sep {
  color: #999;
  font-size: 12px;
}

.param-hint {
  font-size: 11px;
  color: #888;
  margin-left: 4px;
}

.param-tip {
  font-size: 12px;
  color: #888;
  background: #f8f8f8;
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 12px;
}

.indicator-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}

.ind-pick-item {
  padding: 4px 10px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 16px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}

.ind-pick-item:hover {
  border-color: #4a9eff;
}

.ind-pick-item.selected {
  background: #4a9eff;
  color: white;
  border-color: #4a9eff;
}

.expr-builder {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.expr-hint {
  font-size: 12px;
  color: #888;
}

.quick-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.quick-ops .btn {
  font-family: monospace;
}

/* Logic desc row */
.logic-desc-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.logic-desc-row textarea {
  flex: 1;
  background: #f8f8f8;
}

.input-small {
  width: 120px;
}

.input-tiny {
  width: 70px;
}

.btn-tiny {
  padding: 2px 8px;
  font-size: 12px;
}

.error {
  color: #e53935;
  font-size: 13px;
  margin-top: 6px;
}

.empty-hint {
  color: #999;
  font-size: 13px;
  text-align: center;
  padding: 24px 0;
}

.modal-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

/* Disabled input style */
input:disabled, textarea:disabled {
  background: #f0f0f0;
  color: #666;
  cursor: not-allowed;
}

textarea {
  resize: vertical;
  font-family: inherit;
}

/* Threshold configuration */
.threshold-config {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #1a2a4a;
  border-radius: 6px;
  border: 1px solid #2a3a6a;
}

.threshold-label {
  color: #888;
  font-size: 13px;
}

.threshold-indicator {
  color: #e94560;
  font-weight: 600;
  font-size: 14px;
  padding: 2px 8px;
  background: rgba(233,69,96,0.15);
  border-radius: 4px;
}

.threshold-config .select {
  width: auto;
  min-width: 80px;
}

.threshold-config .input-tiny {
  width: 80px;
}

/* Condition tag in indicator card */
.condition-tag {
  background: rgba(233,69,96,0.2) !important;
  color: #e94560 !important;
  font-weight: 600;
}
</style>
