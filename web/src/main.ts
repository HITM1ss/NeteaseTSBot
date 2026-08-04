import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'
import { logger } from './utils/logger'
import { loadAppBranding } from './appConfig'
import { initializeTheme } from './theme'

// 初始化日志
logger.info('TSBot Web application starting...')
initializeTheme()

loadAppBranding().finally(async () => {
  const application = createApp(App).use(router)
  await router.isReady()
  application.mount('#app')
})
