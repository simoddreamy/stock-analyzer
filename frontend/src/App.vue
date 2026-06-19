<template>
  <div class="app">
    <!-- 顶部导航栏 -->
    <header class="nav">
      <div class="nav-brand">Stock Analyzer</div>
      <nav class="nav-links">
        <router-link to="/stocks" class="nav-link" :class="{ active: $route.path === '/stocks' }">
          股票窗口
        </router-link>
        <router-link to="/explore" class="nav-link" :class="{ active: $route.path === '/explore' }">
          {{ exploreNavText }}
        </router-link>
        <router-link to="/logic-config" class="nav-link" :class="{ active: $route.path === '/logic-config' }">
          组合逻辑
        </router-link>
        <router-link to="/settings" class="nav-link" :class="{ active: $route.path === '/settings' }">
          设置
        </router-link>
      </nav>
    </header>

    <!-- 主体内容 -->
    <main class="main">
      <router-view />
    </main>

    <!-- 统一状态栏（始终显示，作为状态中心） -->
    <footer class="status-bar">
      <!-- 探索状态区 -->
      <div class="status-section status-explore">
        <template v-if="exploreActive">
          <span class="status-icon spin">⟳</span>
          <span class="status-text status-running">探索中 {{ exploreCode }}</span>
          <span class="status-detail">⏱ {{ formatTime(exploreElapsed) }} / 10:00</span>
          <span class="status-detail">{{ exploreCandidates }} 个候选</span>
          <span v-if="currentCandidates.length" class="candidates-row">
            <span v-for="(c, idx) in currentCandidates" :key="idx" class="cand-tag">
              <span class="cand-name">{{ shortFormula(c.formula) }}</span>
              <span class="cand-metric" v-if="c.precision !== undefined">
                P{{ (c.precision * 100).toFixed(0) }}% C{{ c.coverage ?? '-' }}
              </span>
              <span class="cand-metric cand-pending" v-else>…</span>
            </span>
          </span>
          <button class="btn-stop-sm" @click="stopExplore">终止</button>
        </template>
        <template v-else-if="exploreResult">
          <span class="status-icon">{{ exploreResult.icon }}</span>
          <span class="status-text" :class="exploreResult.type === 'timeout' ? 'status-warn' : 'status-ok'">
            {{ exploreResult.msg }}
          </span>
          <span class="status-detail" v-if="exploreResult.candidates">
            {{ exploreCode }} · {{ exploreResult.candidates }} 个候选
          </span>
          <span class="status-detail" v-if="exploreResult.best">
            · 最优精度 {{ (exploreResult.best.precision * 100).toFixed(1) }}%
          </span>
        </template>
        <template v-else>
          <span class="status-placeholder">无活跃探索</span>
        </template>
      </div>

      <!-- 同步状态区 -->
      <div class="status-right">
        <div class="status-section">
          <template v-if="syncing">
            <span class="status-icon spin">⟳</span>
            <span class="status-text status-running">同步中...</span>
          </template>
          <template v-else-if="syncResult">
            <span class="status-icon" :class="syncResult.ok ? 'status-ok-icon' : 'status-err-icon'">
              {{ syncResult.ok ? '✓' : '✗' }}
            </span>
            <span class="status-text" :class="syncResult.ok ? 'status-ok' : 'status-err'">
              {{ syncResult.msg }}
            </span>
            <span class="status-detail" v-if="syncResult.added">+{{ syncResult.added }} 只</span>
            <span class="status-detail" v-if="syncResult.updated">· 更新 {{ syncResult.updated }} 只</span>
          </template>
          <template v-else>
            <span class="status-placeholder">未执行同步</span>
          </template>
        </div>

        <button class="sync-btn" @click="handleSync" :disabled="syncing">
          {{ syncing ? '同步中...' : '数据同步' }}
        </button>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import * as api from '@/utils/api'

const syncing = ref(false)
const syncResult = ref(null)   // { ok, msg, added, updated } | null

// 探索全局状态
const exploreActive = ref(false)
const exploreCode = ref('')
const exploreElapsed = ref(0)
const exploreCandidates = ref(0)
const exploreResult = ref(null)   // { icon, msg, candidates, type, best } | null
const currentCandidates = ref([])  // 本轮正在评估的候选 [{formula, logic, precision?, coverage?}]
let _exploreTimer = null

onMounted(async () => {
  await refreshExploreStatus()
  _exploreTimer = setInterval(refreshExploreStatus, 3000)
})

onUnmounted(() => {
  if (_exploreTimer) clearInterval(_exploreTimer)
})

// 导航栏文字
const exploreNavText = computed(() => {
  if (exploreActive.value) return '🔴 探索中'
  if (exploreResult.value) return exploreResult.value.navText || '探索配置'
  return '探索配置'
})

async function refreshExploreStatus() {
  try {
    const st = await api.getExploreStatus()
    if (st.status === 'running' || st.status === 'paused') {
      exploreActive.value = true
      exploreCode.value = st.code
      exploreCandidates.value = st.candidates_explored
      currentCandidates.value = st.current_candidates || []
      if (!exploreTimerStart) {
        exploreTimerStart = Date.now() - st.elapsed * 1000
      }
    } else {
      const wasActive = exploreActive.value
      exploreActive.value = false
      exploreTimerStart = null
      if (wasActive && st.status !== 'idle') {
        const best = st.best_candidate
        let type = 'completed'
        let icon = '✓'
        let msg = '探索完成'
        if (st.status === 'timeout') { type = 'timeout'; icon = '⏱'; msg = '探索超时' }
        else if (st.status === 'stopped') { type = 'stopped'; icon = '✗'; msg = '探索已终止' }
        exploreResult.value = {
          icon, msg, type,
          candidates: st.candidates_explored,
          best: best ? { precision: best.precision } : null,
          navText: `${icon} ${msg}`
        }
      }
    }
  } catch (e) {}
}

let exploreTimerStart = null

setInterval(() => {
  if (exploreActive.value && exploreTimerStart) {
    exploreElapsed.value = Math.floor((Date.now() - exploreTimerStart) / 1000)
  }
}, 1000)

async function handleSync() {
  if (syncing.value) return
  syncing.value = true
  syncResult.value = null
  try {
    const result = await api.syncAll()
    const added = result.added || 0
    const updated = result.updated || 0
    syncResult.value = {
      ok: true,
      msg: `已同步 ${result.synced_at}`,
      added,
      updated
    }
  } catch (e) {
    syncResult.value = { ok: false, msg: String(e).substring(0, 50) }
  } finally {
    syncing.value = false
  }
}

async function stopExplore() {
  try {
    await api.stopExploration()
    exploreActive.value = false
    exploreTimerStart = null
  } catch (e) {}
}

function shortFormula(expr) {
  if (!expr) return '?'
  // 简化公式显示，去掉系数，如 "0.5*RSI_6 + 0.5*VOL_RATIO > 0.7" → "RSI_6 + VOL_RATIO > 0.7"
  return expr.replace(/\d+\.\d+\*|\d+\*/g, '').substring(0, 30)
}

function formatTime(s) {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #1a1a2e; color: #e0e0e0; font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; font-size: 14px; overflow: hidden; }
.app { display: flex; flex-direction: column; height: 100vh; }
.nav { display: flex; align-items: center; padding: 0 20px; height: 48px; background: #16213e; border-bottom: 1px solid #0f3460; flex-shrink: 0; }
.nav-brand { font-size: 16px; font-weight: bold; color: #e94560; margin-right: 40px; }
.nav-links { display: flex; gap: 8px; }
.nav-link { padding: 6px 16px; color: #a0a0a0; text-decoration: none; border-radius: 4px; transition: all 0.2s; }
.nav-link:hover { color: #e0e0e0; }
.nav-link.active { color: #e94560; background: #0f3460; }

.main { flex: 1; overflow: hidden; }

/* 统一状态栏 */
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 40px;
  background: #16213e;
  border-top: 1px solid #0f3460;
  flex-shrink: 0;
  gap: 12px;
}

.status-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-icon { font-size: 14px; flex-shrink: 0; }
.status-icon.spin { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

.status-text { font-size: 13px; color: #e0e0e0; }
.status-detail { font-size: 12px; color: #888; }
.status-placeholder { font-size: 12px; color: #555; }

/* 状态颜色 */
.status-running { color: #e94560; }
.status-ok { color: #26a69a; }
.status-warn { color: #f39c12; }
.status-err { color: #e74c3c; }
.candidates-row {
  display: flex;
  gap: 6px;
  overflow: hidden;
  flex: 1;
}

.cand-tag {
  display: flex;
  align-items: center;
  gap: 3px;
  background: #1a2a4a;
  border: 1px solid #2a3a6a;
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 11px;
  white-space: nowrap;
}

.cand-name { color: #a0c0ff; }
.cand-metric { color: #80e0c0; }
.cand-pending { color: #666; }

.status-explore {
  border-right: 1px solid #0f3460;
  padding-right: 16px;
  flex: 1;
  min-width: 0;
}

.sync-btn {
  padding: 3px 12px;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
}
.sync-btn:hover { background: #d63850; }
.sync-btn:disabled { background: #555; cursor: not-allowed; }

.btn-stop-sm {
  padding: 2px 10px;
  background: #c0392b;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
</style>