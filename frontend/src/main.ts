import { createApp } from 'vue'
import { registerSW } from 'virtual:pwa-register'
import App from './app/App.vue'
import { router } from './router'
import './styles/main.scss'

registerSW({ immediate: true })

createApp(App).use(router).mount('#app')
