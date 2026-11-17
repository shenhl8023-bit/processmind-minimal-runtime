<script setup lang="ts">
import { RouterView, useRoute, useRouter } from 'vue-router'
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message/style/css'
import ModelSettingsDrawer from '@/components/settings/ModelSettingsDrawer.vue'
import {
  resolveCurrentProjectId,
} from '@/composables/useCurrentProject'
import {
  refreshWorkflowNavigation,
  workflowBlockedNotice,
  workflowNavigationProgress,
} from '@/composables/workflowNavigation'
import { workflowResetSignal } from '@/composables/workflowResetState'
import { workflowRouteLoaders } from '@/router'
import { knowledgeLibraryEnabled, productAccess, templateMappingVisible } from '@/composables/productStatus'
import { refreshProductStatus } from '@/api/productStatus'
import { availableWorkflowStep, getWorkflowSteps } from '@/composables/workflowSteps'

const route = useRoute()
const router = useRouter()
const activeIndex = computed(() => route.path)
const settingsVisible = ref(false)

const workflowSteps = computed(() => getWorkflowSteps(templateMappingVisible.value))
const isWorkflowPage = computed(() => workflowSteps.value.some(step => activeIndex.value === step.path))

const currentStepIndex = computed(() => {
  const index = workflowSteps.value.findIndex(step => activeIndex.value.startsWith(step.path))
  return index >= 0 ? index : null
})

const currentProjectId = computed(() => {
  const id = resolveCurrentProjectId(String(route.query.project_id || ''))
  return id ? Number(id) : null
})

const hasProjectContext = computed(() => {
  return currentProjectId.value !== null
})

const currentWorkflowProgress = computed(() =>
  workflowNavigationProgress.value?.project_id === currentProjectId.value
    ? workflowNavigationProgress.value
    : null,
)
const maxAvailableStep = computed(() => currentWorkflowProgress.value?.max_available_step || 1)

watch([currentProjectId, productAccess], ([projectId, access]) => {
  if (projectId === null || access !== 'ready') {
    workflowNavigationProgress.value = null
    return
  }
  if (workflowNavigationProgress.value?.project_id !== projectId) {
    workflowNavigationProgress.value = null
  }
  void refreshWorkflowNavigation(projectId).catch(() => {
    if (currentProjectId.value === projectId) workflowNavigationProgress.value = null
  })
}, { immediate: true })

watch(workflowResetSignal, (signal) => {
  if (productAccess.value !== 'ready') return
  if (signal?.projectId !== currentProjectId.value || currentProjectId.value === null) return
  const completedSteps = Math.min(
    workflowNavigationProgress.value?.project_id === signal.projectId
      ? workflowNavigationProgress.value.completed_steps
      : signal.fromStep - 1,
    signal.fromStep - 1,
  )
  workflowNavigationProgress.value = {
    project_id: signal.projectId,
    completed_steps: completedSteps,
    max_available_step: Math.min(6, completedSteps + 1),
    workflow_revision: signal.workflowRevision,
  }
  void refreshWorkflowNavigation(currentProjectId.value).catch(() => {
    if ((workflowNavigationProgress.value?.workflow_revision || 0) < signal.workflowRevision) {
      workflowNavigationProgress.value = null
    }
  })
})

watch(workflowBlockedNotice, (message) => {
  if (!message || productAccess.value !== 'ready') return
  ElMessage.warning(message)
  workflowBlockedNotice.value = ''
}, { immediate: true })

const stepStatus = (stepNumber: number) => {
  const index = stepNumber - 1
  const step = workflowSteps.value[index]
  if (!step) return 'locked'
  if (currentStepIndex.value !== null) {
    if (index === currentStepIndex.value) return 'active'
  }
  if (step.internalStep <= (currentWorkflowProgress.value?.completed_steps || 0)) return 'completed'
  if (step.internalStep <= maxAvailableStep.value && (stepNumber === 1 || hasProjectContext.value)) return 'available'
  return 'locked'
}

const stepIsCompleted = (stepNumber: number) => stepStatus(stepNumber) === 'completed'

function navigateToStep(stepNumber: number) {
  if (productAccess.value !== 'ready') return
  const status = stepStatus(stepNumber)
  if (status === 'active') return
  if (status === 'locked') {
    const requiredStep = availableWorkflowStep(maxAvailableStep.value, templateMappingVisible.value)
    ElMessage.warning(`请先完成【${requiredStep?.label || '当前步骤'}】，再进入后续步骤。`)
    return
  }
  const step = workflowSteps.value[stepNumber - 1]
  if (!step) return
  router.push({
    path: step.path,
    query: route.query.project_id ? { project_id: route.query.project_id } : {},
  })
}

const openSettings = () => {
  if (productAccess.value !== 'ready') return
  settingsVisible.value = true
}

const openKnowledge = () => {
  if (productAccess.value !== 'ready' || !knowledgeLibraryEnabled.value) return
  router.push({
    path: '/knowledge',
    query: route.query.project_id ? { project_id: route.query.project_id } : {},
  })
}

onMounted(() => {
  if (typeof window === 'undefined' || productAccess.value !== 'ready') return
  const prefetchWorkflowViews = () => {
    if (productAccess.value !== 'ready') return
    workflowRouteLoaders.filter((_, index) => templateMappingVisible.value || index !== 5).forEach((loader) => {
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

watch(productAccess, access => {
  if (access === 'ready') return
  settingsVisible.value = false
  ElMessage.closeAll()
  ElMessageBox.close()
}, { flush: 'sync' })

</script>

<template>
  <main v-if="productAccess !== 'ready'" class="product-access-screen" role="alert" aria-live="polite">
    <section class="product-access-card">
      <span class="product-access-brand">ProcessMind</span>
      <template v-if="productAccess === 'expired'">
        <h1>试用已到期</h1>
        <p>试用已到期，请联系供应方。</p>
      </template>
      <template v-else-if="productAccess === 'error'">
        <h1>无法确认产品状态</h1>
        <p>请确认本地服务正在运行，然后重试。</p>
        <button type="button" class="btn btn-primary" @click="refreshProductStatus">重试</button>
      </template>
      <template v-else>
        <h1>正在确认产品状态</h1>
        <p>请稍候…</p>
      </template>
    </section>
  </main>
  <div v-else class="app-shell" :class="{ 'knowledge-shell': activeIndex === '/knowledge', 'workflow-shell': isWorkflowPage }">
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
        <template v-for="(step, i) in workflowSteps" :key="step.number">
          <div
            :class="['step', stepStatus(step.number)]"
            :aria-current="stepStatus(step.number) === 'active' ? 'step' : undefined"
            :role="['completed','available'].includes(stepStatus(step.number)) ? 'button' : undefined"
            :tabindex="['completed','available'].includes(stepStatus(step.number)) ? 0 : undefined"
            :title="stepStatus(step.number) === 'completed' ? `返回${step.label}` : stepStatus(step.number) === 'available' ? `前往${step.label}` : undefined"
            @click="navigateToStep(step.number)"
            @keydown.enter="navigateToStep(step.number)"
          >
            <div class="step-dot">{{ step.number }}</div>
            <span>{{ step.label }}</span>
          </div>
          <div v-if="i < workflowSteps.length - 1" class="step-line" :class="{ completed: stepIsCompleted(step.number) }" aria-hidden="true"></div>
        </template>
      </nav>

      <div class="top-bar-right">
        <button
          v-if="activeIndex === '/knowledge'"
          class="asset-entry"
          type="button"
          title="返回第一步：上传资料"
          @click="navigateToStep(1)"
        >
          返回第一步
        </button>
        <button
          v-else-if="knowledgeLibraryEnabled"
          class="asset-entry knowledge-entry"
          type="button"
          @click="openKnowledge"
        >
          工艺知识库
        </button>
        <button
          class="asset-entry"
          @click="openSettings"
        >
          模型设置
        </button>
      </div>
    </header>

    <ModelSettingsDrawer v-model="settingsVisible" :project-id="currentProjectId" />

    <!-- Main Content Area -->
    <main class="main-area">
      <RouterView v-slot="{ Component, route: viewRoute }">
        <KeepAlive
          include="UploadView,ExtractView,AnalysisView,TemplateMappingView,FinalizeView,GenerateView,KnowledgeView"
          :max="7"
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
