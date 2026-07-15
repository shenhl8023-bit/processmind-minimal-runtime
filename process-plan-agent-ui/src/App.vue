<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import { computed, onMounted, ref } from 'vue'
import ModelSettingsDrawer from '@/components/settings/ModelSettingsDrawer.vue'
import {
  resolveCurrentProjectId,
} from '@/composables/useCurrentProject'
import { workflowRouteLoaders } from '@/router'

const route = useRoute()
const activeIndex = computed(() => route.path)
const settingsVisible = ref(false)

const workflowSteps = [
  { path: '/upload', number: 1 },
  { path: '/extract', number: 2 },
  { path: '/analysis', number: 3 },
  { path: '/finalize', number: 4 },
  { path: '/generate', number: 5 },
] as const

const currentStepIndex = computed(() => {
  const index = workflowSteps.findIndex(step => activeIndex.value.startsWith(step.path))
  return index >= 0 ? index : 0
})

const hasProjectContext = computed(() => {
  return Boolean(resolveCurrentProjectId(String(route.query.project_id || '')))
})

const stepStatus = (stepNumber: number) => {
  const index = stepNumber - 1
  if (index === currentStepIndex.value) return 'active'
  if (index < currentStepIndex.value) return 'completed'
  if (!hasProjectContext.value) return 'locked'
  return 'available'
}

const stepIsCompleted = (stepNumber: number) => stepStatus(stepNumber) === 'completed'

const openSettings = () => {
  settingsVisible.value = true
}

onMounted(() => {
  if (typeof window === 'undefined') return
  const prefetchWorkflowViews = () => {
    workflowRouteLoaders.forEach((loader) => {
      void loader()
    })
  }
  const idleWindow = window as Window & {
    requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number
  }
  if (idleWindow.requestIdleCallback) {
    idleWindow.requestIdleCallback(prefetchWorkflowViews, { timeout: 2000 })
    return
  }
  window.setTimeout(prefetchWorkflowViews, 800)
})

</script>

<template>
  <div class="app-shell">
    <!-- Top Navigation Bar -->
    <header class="top-bar">
      <div class="brand">
        <div class="brand-icon">⚙</div>
        <div class="brand-text">
          <span class="brand-name">ProcessMind</span>
          <span class="brand-slogan">典型工艺规程智能体</span>
        </div>
      </div>

      <nav class="step-indicator" aria-label="Workflow steps">
        <div :class="['step', stepStatus(1)]" :aria-current="stepStatus(1) === 'active' ? 'step' : undefined">
          <div class="step-dot">1</div>
          <span>上传资料</span>
        </div>
        <div class="step-line" :class="{ completed: stepIsCompleted(1) }" aria-hidden="true"></div>
        <div :class="['step', stepStatus(2)]" :aria-current="stepStatus(2) === 'active' ? 'step' : undefined">
          <div class="step-dot">2</div>
          <span>路线归并</span>
        </div>
        <div class="step-line" :class="{ completed: stepIsCompleted(2) }" aria-hidden="true"></div>
        <div :class="['step', stepStatus(3)]" :aria-current="stepStatus(3) === 'active' ? 'step' : undefined">
          <div class="step-dot">3</div>
          <span>规则分析</span>
        </div>
        <div class="step-line" :class="{ completed: stepIsCompleted(3) }" aria-hidden="true"></div>
        <div :class="['step', stepStatus(4)]" :aria-current="stepStatus(4) === 'active' ? 'step' : undefined">
          <div class="step-dot">4</div>
          <span>规则定稿</span>
        </div>
        <div class="step-line" :class="{ completed: stepIsCompleted(4) }" aria-hidden="true"></div>
        <div :class="['step', stepStatus(5)]" :aria-current="stepStatus(5) === 'active' ? 'step' : undefined">
          <div class="step-dot">5</div>
          <span>路线生成</span>
        </div>
      </nav>

      <div class="top-bar-right">
        <button
          class="asset-entry"
          @click="openSettings"
        >
          模型设置
        </button>
      </div>
    </header>

    <ModelSettingsDrawer v-model="settingsVisible" />

    <!-- Main Content Area -->
    <main class="main-area">
      <RouterView v-slot="{ Component, route: viewRoute }">
        <KeepAlive
          include="UploadView,ExtractView,AnalysisView,FinalizeView,GenerateView"
          :max="5"
        >
          <component :is="Component" :key="viewRoute.name || viewRoute.path" />
        </KeepAlive>
      </RouterView>
    </main>

    <!-- Footer -->
    <footer class="footer">
      ProcessMind · 典型工艺规程智能体 · © 2026 · v1.0.0
    </footer>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --bg-primary: #f8fafc; /* Softer slate background, less sterile than pure white/f7 */
  --bg-card: #ffffff;
  --border-light: #e2e8f0; /* Softer slate border */
  --text-primary: #0f172a; /* Deeper slate text */
  --text-secondary: #475569;
  --text-muted: #94a3b8;
  --accent: #4f46e5; /* Modern, deeper indigo */
  --accent-light: #e0e7ff;
  --accent-hover: #4338ca;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --radius-sm: 8px; /* Slightly rounder */
  --radius-md: 12px;
  --radius-lg: 16px;
  --shadow-sm: 0 2px 4px -1px rgba(0,0,0,0.04), 0 1px 2px -1px rgba(0,0,0,0.03); /* Richer subtle shadow */
  --shadow-md: 0 4px 12px -2px rgba(0,0,0,0.06), 0 2px 6px -1px rgba(0,0,0,0.04); /* Deeper hover shadow */
  --shadow-lg: 0 12px 32px -4px rgba(0,0,0,0.1), 0 8px 16px -4px rgba(0,0,0,0.06); /* Heavy lift shadow */
  --transition: all 0.2s ease;
  /* 主内容区与底部导航共用，保证「进入下一步」按钮右缘与上方卡片对齐 */
  --page-max-width: 1280px;
  --page-padding-x: 24px;
}

html {
  /* 预留滚动条槽，避免 fixed 底栏与文档流主内容因滚动条宽度错位 */
  scrollbar-gutter: stable;
}

html, body {
  height: 100%;
  overflow-x: hidden;
  /* Inter 负责拉丁字符和数字，PingFang SC 优先渲染汉字（macOS 原生，与 Inter 字重感知最接近）
     Noto Sans SC 作为跨平台兜底，Noto 比 PingFang 字冠更大但两者感知接近 */
  font-family: 'Inter', 'PingFang SC', 'Noto Sans SC', -apple-system, BlinkMacSystemFont,
    'Helvetica Neue', Arial, sans-serif;
  font-feature-settings: 'kern' 1, 'liga' 1;
  background: var(--bg-primary);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

#app {
  height: 100%;
}

.app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* ===== Top Bar ===== */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
  position: sticky;
  top: 0;
  z-index: 100;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-icon {
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, var(--accent), #818cf8);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #fff;
}

.brand-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.brand-slogan {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: 6px;
  font-weight: 400;
}

.nav-links {
  display: flex;
  gap: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border-radius: 40px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: default;
  transition: var(--transition);
  user-select: none;
  text-decoration: none;
}

.nav-item:hover {
  background: var(--accent-light);
  color: var(--accent);
}

.nav-item.active {
  background: var(--accent);
  color: #fff;
}

.nav-icon {
  font-size: 16px;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 8px;
}

.asset-entry {
  margin-left: auto;
  border: 1px solid var(--border-light);
  background: var(--bg-card);
  color: var(--text-secondary);
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
}

.asset-entry:hover {
  background: var(--accent-light);
  color: var(--accent);
  border-color: rgba(91, 106, 191, 0.22);
}

.asset-entry.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.user-name {
  font-size: 14px;
  color: var(--text-secondary);
  padding: 6px 16px;
  border: 1px solid var(--border-light);
  border-radius: 40px;
}

/* ===== Step Indicator (inside top-bar) ===== */
.step-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: default;
  flex-shrink: 0;
  user-select: none;
  transition: var(--transition);
}

.step.active {
  color: var(--accent);
  font-weight: 600;
}

.step.completed {
  color: var(--success);
}

.step.available {
  color: var(--text-secondary);
}

.step.locked {
  color: var(--text-muted);
  opacity: 0.6;
}

.step-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  transition: var(--transition);
}

.step.active .step-dot {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.step.completed .step-dot {
  background: var(--success);
  border-color: var(--success);
  color: #fff;
}

.step.locked .step-dot {
  border-style: dashed;
}

.step-line {
  width: 36px;
  height: 1px;
  background: var(--border-light);
  border-radius: 1px;
}

.step-line.completed {
  background: var(--success);
}

/* ===== Main Content ===== */
.main-area {
  flex: 1;
  padding: 14px var(--page-padding-x) 56px;
  max-width: var(--page-max-width);
  width: 100%;
  min-width: 0;
  margin: 0 auto;
  overflow-x: hidden;
}

/* ===== Footer ===== */
.footer {
  text-align: center;
  padding: 6px;
  font-size: 11px;
  color: var(--text-muted);
  border-top: 1px solid var(--border-light);
  background: var(--bg-card);
}

/* ===== Shared Card Styles ===== */
.card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  padding: 16px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s ease;
}

.card:hover {
  box-shadow: var(--shadow-md);
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  letter-spacing: -0.005em;
}

/* ===== Shared Button Styles ===== */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: var(--transition);
}

.btn:disabled, .btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
  pointer-events: none;
}

.btn-primary {
  background: var(--accent);
  color: #fff;
}

.btn-primary:hover {
  background: var(--accent-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-outline {
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
}

.btn-outline:hover {
  background: var(--accent-light);
}

.btn-success {
  background: var(--success);
  color: #fff;
}

.btn-success:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

/* ===== Shared Tag Styles ===== */
.tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 40px;
  font-size: 12px;
  font-weight: 500;
}

.tag-info { background: #f1f5f9; color: #475569; } /* slate-100 / slate-600 */
.tag-success { background: #d1fae5; color: #059669; } /* emerald-100 / emerald-600 */
.tag-warning { background: #fef3c7; color: #d97706; } /* amber-100 / amber-600 */
.tag-danger { background: #fee2e2; color: #dc2626; } /* red-100 / red-600 */
.tag-accent { background: var(--accent-light); color: var(--accent); }

/* Keep the workflow usable on narrow screens without shrinking labels into
   unreadable controls. The step row becomes an independently scrollable rail
   so the page itself never gains a horizontal scrollbar. */
@media (max-width: 900px) {
  :root {
    --page-padding-x: 16px;
  }

  .top-bar {
    height: auto;
    min-height: 48px;
    padding: 8px var(--page-padding-x) 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    row-gap: 8px;
  }

  .brand {
    min-width: 0;
  }

  .brand-slogan {
    display: none;
  }

  .step-indicator {
    grid-column: 1 / -1;
    width: 100%;
    min-width: 0;
    overflow-x: auto;
    overflow-y: hidden;
    justify-content: flex-start;
    gap: 8px;
    padding: 2px 2px 9px;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }

  .step-indicator::-webkit-scrollbar {
    display: none;
  }

  .step-line {
    flex: 0 0 24px;
  }

  .main-area {
    padding: 12px var(--page-padding-x) 88px;
  }
}

@media (max-width: 520px) {
  :root {
    --page-padding-x: 12px;
  }

  .top-bar {
    padding-left: var(--page-padding-x);
    padding-right: var(--page-padding-x);
  }

  .brand-name {
    font-size: 13px;
  }

  .asset-entry {
    padding: 5px 10px;
    font-size: 11px;
  }

  .step-indicator {
    margin-inline: -2px;
    padding-inline: 2px;
  }

  .main-area {
    padding-inline: var(--page-padding-x);
  }

  .footer {
    padding-inline: var(--page-padding-x);
    line-height: 1.4;
  }
}
</style>
