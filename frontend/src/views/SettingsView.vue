<template>
  <div class="settings-view">
    <h2>设置</h2>

    <div class="settings-section">
      <h3>AI 模型配置</h3>
      <div class="setting-row">
        <span class="setting-label">API Provider</span>
        <select v-model="settings.api_provider" class="select">
          <option value="openai">OpenAI</option>
          <option value="azure">Azure OpenAI</option>
          <option value="custom">自定义</option>
        </select>
      </div>
      <div class="setting-row">
        <span class="setting-label">API Key</span>
        <input v-model="settings.api_key" type="password" class="input" placeholder="sk-..." />
      </div>
      <div class="setting-row">
        <span class="setting-label">模型</span>
        <input v-model="settings.model" class="input" placeholder="gpt-4o" />
      </div>
      <div class="setting-row">
        <span class="setting-label">API Base</span>
        <input v-model="settings.api_base" class="input" placeholder="https://api.openai.com/v1" />
      </div>
      <div class="setting-actions">
        <button class="btn" @click="saveSettings" :disabled="saving">保存</button>
        <button class="btn btn-ghost" @click="testConnection">测试连接</button>
      </div>
      <div class="test-result" v-if="testResult" :class="testResult.ok ? 'ok' : 'fail'">
        {{ testResult.message }}
      </div>
    </div>

    <div class="settings-section">
      <h3>数据源配置</h3>
      <div class="setting-row">
        <span class="setting-label">主数据源</span>
        <select v-model="settings.primary_datasource" class="select">
          <option value="akshare">AKShare</option>
          <option value="baostock">Baostock</option>
        </select>
      </div>
      <div class="setting-row">
        <span class="setting-label">备数据源</span>
        <select v-model="settings.backup_datasource" class="select">
          <option value="baostock">Baostock</option>
          <option value="akshare">AKShare</option>
        </select>
      </div>
    </div>

    <div class="settings-section">
      <h3>U1 默认参数</h3>
      <div class="setting-row">
        <span class="setting-label">买入价计算方式</span>
        <select v-model="settings.default_buy_price" class="select">
          <option value="MA5">MA5（5日均价）</option>
          <option value="close">收盘价</option>
        </select>
      </div>
      <div class="setting-row">
        <span class="setting-label">持有交易日数</span>
        <input v-model.number="settings.default_hold_days" type="number" min="1" max="30" class="input-small" />
      </div>
      <div class="setting-row">
        <span class="setting-label">盈利目标</span>
        <div class="input-group">
          <input v-model.number="settings.default_profit_pct" type="number" min="0.1" step="0.1" class="input-small" />
          <span class="unit">%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as api from '@/utils/api'

const settings = ref({
  api_provider: 'openai',
  api_key: '',
  model: 'gpt-4o',
  api_base: 'https://api.openai.com/v1',
  primary_datasource: 'akshare',
  backup_datasource: 'baostock',
  default_buy_price: 'MA5',
  default_hold_days: 5,
  default_profit_pct: 2.0
})

const saving = ref(false)
const testResult = ref(null)

onMounted(async () => {
  try {
    const all = await api.getSettings()
    if (all) settings.value = { ...settings.value, ...all }
  } catch (e) { console.error(e) }
})

async function saveSettings() {
  saving.value = true
  try {
    for (const [key, val] of Object.entries(settings.value)) {
      await api.setSetting(key, String(val))
    }
  } catch (e) { console.error(e) } finally { saving.value = false }
}

async function testConnection() {
  testResult.value = null
  try {
    await api.testConnection({ api_key: settings.value.api_key, api_base: settings.value.api_base, model: settings.value.model })
    testResult.value = { ok: true, message: '连接成功 ✓' }
  } catch (e) {
    testResult.value = { ok: false, message: `连接失败: ${e}` }
  }
}
</script>

<style scoped>
.settings-view { height: 100%; overflow-y: auto; padding: 24px; max-width: 560px; }
h2 { color: #e0e0e0; font-size: 20px; margin-bottom: 24px; }
.settings-section { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.settings-section h3 { font-size: 14px; color: #e0e0e0; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #0f3460; }
.setting-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.setting-label { font-size: 13px; color: #888; }
.select, .input, .input-small { padding: 7px 10px; background: #1a1a2e; border: 1px solid #0f3460; color: #e0e0e0; border-radius: 4px; font-size: 13px; box-sizing: border-box; }
.input { width: 260px; }
.input-small { width: 80px; }
.input-group { display: flex; align-items: center; gap: 6px; }
.unit { font-size: 13px; color: #888; }
.setting-actions { display: flex; gap: 10px; margin-top: 16px; }
.test-result { margin-top: 10px; font-size: 13px; padding: 8px 12px; border-radius: 4px; }
.test-result.ok { background: rgba(38, 166, 154, 0.15); color: #26a69a; }
.test-result.fail { background: rgba(233, 69, 96, 0.15); color: #e94560; }
.btn { padding: 7px 20px; background: #e94560; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-ghost { background: transparent; color: #888; border: 1px solid #0f3460; }
.btn:disabled { background: #555; cursor: not-allowed; }
</style>