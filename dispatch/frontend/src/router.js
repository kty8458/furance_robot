import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Sampler from './views/Sampler.vue'
import TaskEditor from './views/TaskEditor.vue'
import TaskExecution from './views/TaskExecution.vue'
import Alarms from './views/Alarms.vue'
import Logs from './views/Logs.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/sampler', component: Sampler },
    { path: '/tasks/editor', component: TaskEditor },
    { path: '/tasks/execution', component: TaskExecution },
    { path: '/alarms', component: Alarms },
    { path: '/logs', component: Logs },
  ],
})
