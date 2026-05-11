import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import RobotControl from './views/RobotControl.vue'
import Tasks from './views/Tasks.vue'
import Sampler from './views/Sampler.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/robot', component: RobotControl },
    { path: '/tasks', component: Tasks },
    { path: '/sampler', component: Sampler },
  ],
})