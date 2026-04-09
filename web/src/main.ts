import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'
import { logger } from './utils/logger'
import { applyAppBranding } from './appConfig'

// 初始化日志
logger.info('TSBot Web application starting...')
applyAppBranding()

createApp(App).use(router).mount('#app')
