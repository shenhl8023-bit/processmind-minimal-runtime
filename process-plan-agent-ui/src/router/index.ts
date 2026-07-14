import { createRouter, createWebHistory } from 'vue-router'

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
      component: () => import('@/views/UploadView.vue')
    },
    {
      path: '/extract',
      name: 'extract',
      component: () => import('@/views/ExtractView.vue')
    },
    {
      path: '/analysis',
      name: 'analysis',
      component: () => import('@/views/AnalysisView.vue')
    },
    {
      path: '/finalize',
      name: 'finalize',
      component: () => import('@/views/FinalizeView.vue')
    },
    {
      path: '/generate',
      name: 'generate',
      component: () => import('@/views/GenerateView.vue')
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue')
    }
  ]
})

export default router
