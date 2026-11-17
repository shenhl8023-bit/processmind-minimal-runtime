import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index'
import { refreshProductStatus, startProductStatusSync } from './api/productStatus'
import './styles/visual-tokens.css'
import './styles/global.css'
import './styles/workflow-page-header.css'

async function bootstrap() {
  await refreshProductStatus()
  const app = createApp(App)
  app.use(router)
  app.mount('#app')
  startProductStatusSync()
}

void bootstrap()
