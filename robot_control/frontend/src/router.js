import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Commands from './views/Commands.vue'
import ArmControl from './views/ArmControl.vue'
import Navigation from './views/Navigation.vue'
import Ros2Nodes from './views/Ros2Nodes.vue'
import Logs from './views/Logs.vue'
import WorkflowEditor from './views/WorkflowEditor.vue'
import CameraView from './views/CameraView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/commands', component: Commands },
    { path: '/arm', component: ArmControl },
    { path: '/navigation', component: Navigation },
    { path: '/ros2', component: Ros2Nodes },
    { path: '/logs', component: Logs },
    { path: '/workflow', component: WorkflowEditor },
    { path: '/camera', component: CameraView },
  ],
})
