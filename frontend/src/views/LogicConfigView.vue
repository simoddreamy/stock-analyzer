<template>
  <div class="logic-config-view">
    <div class="page-header">
      <h2>组合逻辑配置</h2>
    </div>

    <div class="two-panel">
      <!-- ==================== Part 1: 指标参数配置 ==================== -->
      <div class="panel panel-left">
        <div class="panel-header">
          <h3>指标参数库</h3>
          <button class="btn btn-small" @click="showAddIndicator = true">+ 新增指标</button>
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
              <span class="ind-name">{{ ind.name }}</span>
              <span class="ind-category">{{ ind.category }}</span>
            </div>
            <div class="ind-params" v-if="ind.param_config">
              <span v-for="(v, k) in ind.param_config" :key="k" class="param-tag">
                {{ k }}: [{{ v.min }}, {{ v.max }}]
              </span>
            </div>
            <div class="ind-desc" v-if="ind.description">{{ ind.description }}</div>
            <div class="card-actions">
              <button class="btn btn-tiny" @click.stop="editIndicator(ind)">编辑</button>
              <button class="btn btn-tiny btn-danger" @click.stop="delIndicator(ind.id)">删除</button>
            </div>
          </div>
        </div>
        <div class="empty-hint" v-else>暂无指标配置，点击上方按钮添加</div>

        <!-- 新增/编辑指标 Modal -->
        <div class="modal" v-if="showAddIndicator || editingIndicator" @click.self="closeIndicatorModal">
          <div class="modal-content">
            <h3>{{ editingIndicator ? '编辑指标' : '新增指标' }}</h3>

            <div class="field">
              <label>指标名称</label>
              <input v-model="indForm.name" class="input" placeholder="如: RSI, MACD, VOL_RATIO" />
            </div>

            <div class="field">
              <label>分类</label>
              <select v-model="indForm.category" class="select">
                <option value="custom">自定义</option>
                <option value="momentum">动量类</option>
                <option value="volume">成交量类</option>
                <option value="volatility">波动率类</option>
                <option value="trend">趋势类</option>
              </select>
            </div>

            <div class="field">
              <label>描述说明</label>
              <input v-model="indForm.description" class="input" placeholder="选填" />
            </div>

            <div class="field">
              <label>参数范围配置</label>
              <div class="param-config-list">
                <div v-for="(param, pIdx) in indForm.paramConfigList" :key="pIdx" class="param-row">
                  <input v-model="param.name" class="input input-small" placeholder="参数名" />
                  <input v-model.number="param.min" type="number" class="input input-tiny" placeholder="最小" step="0.01" />
                  <input v-model.number="param.max" type="number" class="input input-tiny" placeholder="最大" step="0.01" />
                  <button class="btn btn-tiny btn-danger" @click="removeParam(pIdx)">×</button>
                </div>
                <button class="btn btn-tiny" @click="addParam">+ 添加参数</button>
              </div>
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
          <h3>指标公式组合</h3>
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

            <div class="field">
              <label>公式名称</label>
              <input v-model="fmForm.name" class="input" placeholder="如: RSI成交量共振, 突破策略" />
            </div>

            <div class="field">
              <label>引用指标</label>
              <div class="indicator-picker">
                <div
                  v-for="ind in indicators"
                  :key="ind.id"
                  class="ind-pick-item"
                  :class="{ selected: fmForm.indicatorRefs.includes(ind.id) }"
                  @click="toggleIndicatorRef(ind.id)"
                >
                  {{ ind.name }}
                </div>
              </div>
              <div class="empty-hint" v-if="indicators.length === 0">请先在左侧添加指标</div>
            </div>

            <div class="field">
              <label>公式表达式</label>
              <div class="expr-builder">
                <div class="expr-hint">
                  从已选指标中选择或手动输入表达式<br />
                  示例: <code>RSI_6 &gt; 0.5 AND VOL_RATIO &gt; 1.2</code>
                </div>
                <textarea v-model="fmForm.formula_expr" class="textarea" rows="3"
                  placeholder="如: RSI_6 > 0.5 AND VOL_RATIO > 1.2"></textarea>
                <div class="quick-ops">
                  <button class="btn btn-tiny" @click="insertOp(' AND ')">AND</button>
                  <button class="btn btn-tiny" @click="insertOp(' OR ')">OR</button>
                  <button class="btn btn-tiny" @click="insertOp(' > ')">&gt;</button>
                  <button class="btn btn-tiny" @click="insertOp(' < ')">&lt;</button>
                  <button class="btn btn-tiny" @click="insertOp(' >= ')">&gt;=</button>
                  <button class="btn btn-tiny" @click="insertOp(' <= ')">&lt;=</button>
                  <button class="btn btn-tiny" @click="insertOp(' + ')">+</button>
                  <button class="btn btn-tiny" @click="insertOp(' - ')">-</button>
                  <button class="btn btn-tiny" @click="insertOp(' * ')">*</button>
                  <button class="btn btn-tiny" @click="insertOp(' / ')">/</button>
                </div>
              </div>
            </div>

            <div class="field">
              <label>逻辑说明</label>
              <input v-model="fmForm.logic_desc" class="input" placeholder="选填，说明此公式的逻辑" />
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
import { ref, onMounted } from 'vue'
import * as api from '@/utils/api'

const indicators = ref([])
const formulas = ref([])
const selectedIndicator = ref(null)
const selectedFormula = ref(null)

// Indicator modal state
const showAddIndicator = ref(false)
const editingIndicator = ref(null)
const indForm = ref({ name: '', category: 'custom', description: '', paramConfigList: [{ name: '', min: 0, max: 100 }] })
const indError = ref('')

// Formula modal state
const showAddFormula = ref(false)
const editingFormula = ref(null)
const fmForm = ref({ name: '', formula_expr: '', logic_desc: '', indicatorRefs: [] })
const fmError = ref('')

onMounted(async () => {
  await loadAll()
})

async function loadAll() {
  try {
    indicators.value = await api.listIndicators()
    formulas.value = await api.listFormulaCombinations()
  } catch (e) {
    console.error('Failed to load:', e)
  }
}

function selectIndicator(ind) {
  selectedIndicator.value = ind
}

function selectFormula(fm) {
  selectedFormula.value = fm
}

function getIndicatorName(id) {
  const ind = indicators.value.find(i => i.id === id)
  return ind ? ind.name : `指标${id}`
}

// ----- Indicator CRUD -----
function editIndicator(ind) {
  editingIndicator.value = ind
  // param_config is a dict like {period: {min:5, max:20}}
  // convert to paramConfigList for the form
  const list = []
  if (ind.param_config) {
    for (const [k, v] of Object.entries(ind.param_config)) {
      list.push({ name: k, min: v.min, max: v.max })
    }
  }
  if (list.length === 0) list.push({ name: '', min: 0, max: 100 })
  indForm.value = { name: ind.name, category: ind.category || 'custom', description: ind.description || '', paramConfigList: list }
}

function closeIndicatorModal() {
  showAddIndicator.value = false
  editingIndicator.value = null
  indForm.value = { name: '', category: 'custom', description: '', paramConfigList: [{ name: '', min: 0, max: 100 }] }
  indError.value = ''
}

function addParam() {
  indForm.value.paramConfigList.push({ name: '', min: 0, max: 100 })
}

function removeParam(idx) {
  indForm.value.paramConfigList.splice(idx, 1)
}

async function saveIndicator() {
  indError.value = ''
  if (!indForm.value.name.trim()) {
    indError.value = '请填写指标名称'
    return
  }
  // Build param_config dict from paramConfigList
  const param_config = {}
  for (const p of indForm.value.paramConfigList) {
    if (p.name.trim()) {
      param_config[p.name.trim()] = { min: p.min, max: p.max }
    }
  }
  const payload = {
    name: indForm.value.name.trim(),
    category: indForm.value.category,
    description: indForm.value.description.trim(),
    param_config: param_config
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
  if (!confirm('确认删除此指标配置？')) return
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
  fmForm.value = {
    name: fm.name,
    formula_expr: fm.formula_expr,
    logic_desc: fm.logic_desc || '',
    indicatorRefs: [...(fm.indicator_refs || [])]
  }
}

function closeFormulaModal() {
  showAddFormula.value = false
  editingFormula.value = null
  fmForm.value = { name: '', formula_expr: '', logic_desc: '', indicatorRefs: [] }
  fmError.value = ''
}

function toggleIndicatorRef(id) {
  const idx = fmForm.value.indicatorRefs.indexOf(id)
  if (idx >= 0) {
    fmForm.value.indicatorRefs.splice(idx, 1)
  } else {
    fmForm.value.indicatorRefs.push(id)
  }
}

function insertOp(op) {
  fmForm.value.formula_expr += op
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
  try {
    const payload = {
      name: fmForm.value.name.trim(),
      formula_expr: fmForm.value.formula_expr.trim(),
      logic_desc: fmForm.value.logic_desc.trim(),
      indicator_refs: fmForm.value.indicatorRefs
    }
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

.ind-name, .fm-name {
  font-weight: 600;
  font-size: 14px;
}

.ind-category {
  font-size: 11px;
  color: #888;
  background: #f0f0f0;
  padding: 1px 6px;
  border-radius: 10px;
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
  max-width: 480px;
}

.modal-wide {
  max-width: 600px;
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

.param-config-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.indicator-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}

.ind-pick-item {
  padding: 4px 12px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 16px;
  cursor: pointer;
  font-size: 13px;
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
</style>
