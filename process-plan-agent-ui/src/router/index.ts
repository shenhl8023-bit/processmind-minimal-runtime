import { createRouter, createWebHistory } from 'vue-router'

const loadUploadView = () => import('@/views/UploadView.vue')
const loadExtractView = () => import('@/views/ExtractView.vue')
const loadAnalysisView = () => import('@/views/AnalysisView.vue')
const loadFinalizeView = () => import('@/views/FinalizeView.vue')
const loadGenerateView = () => import('@/views/GenerateView.vue')
const loadSettingsView = () => import('@/views/SettingsView.vue')

export const workflowRouteLoaders = [
  loadUploadView,
  loadExtractView,
  loadAnalysisView,
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
    }
  ]
})

export default router
