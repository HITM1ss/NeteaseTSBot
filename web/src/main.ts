import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'
import { logger } from './utils/logger'
import { applyAppBranding } from './appConfig'
import { initializeTheme } from './theme'

// 初始化日志
logger.info('TSBot Web application starting...')
applyAppBranding()
initializeTheme()

createApp(App).use(router).mount('#app')
