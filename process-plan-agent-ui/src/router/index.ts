import { createRouter, createWebHistory } from 'vue-router'
import { guardWorkflowRoute } from '@/composables/workflowNavigation'

const loadUploadView = () => import('@/views/UploadView.vue')
const loadExtractView = () => import('@/views/ExtractView.vue')
const loadAnalysisView = () => import('@/views/AnalysisView.vue')
const loadTemplateMappingView = () => import('@/views/TemplateMappingView.vue')
const loadFinalizeView = () => import('@/views/FinalizeView.vue')
const loadGenerateView = () => import('@/views/GenerateView.vue')
const loadSettingsView = () => import('@/views/SettingsView.vue')
const loadKnowledgeView = () => import('@/views/KnowledgeView.vue')

export const workflowRouteLoaders = [
  loadUploadView,
  loadExtractView,
  loadAnalysisView,
  loadTemplateMappingView,
  loadFinalizeView,
  loadGenerateView,
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      redirect: '/upload'
    },
    {
      path: '/upload',
      name: 'upload',
      component: loadUploadView
    },
    {
      path: '/extract',
      name: 'extract',
      component: loadExtractView
    },
    {
      path: '/analysis',
      name: 'analysis',
      component: loadAnalysisView
    },
    { path: '/template-mapping', name: 'template-mapping', component: loadTemplateMappingView },
    {
      path: '/finalize',
      name: 'finalize',
      component: loadFinalizeView
    },
    {
      path: '/generate',
      name: 'generate',
      component: loadGenerateView
    },
    {
      path: '/settings',
      name: 'settings',
      component: loadSettingsView
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: loadKnowledgeView
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/upload'
    },
  ]
})

router.beforeEach(guardWorkflowRoute)

export default router
