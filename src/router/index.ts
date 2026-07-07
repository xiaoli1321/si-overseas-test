import { createRouter, createWebHistory } from 'vue-router';
import LoginView from '@/views/LoginView.vue';
import AgentChatView from '@/views/AgentChatView.vue';
import DeviceListView from '@/views/DeviceListView.vue';
import FaultQueryView from '@/views/FaultQueryView.vue';
import MultiDetectView from '@/views/MultiDetectView.vue';
import DetectFlowView from '@/views/DetectFlowView.vue';
import DetectRecordsView from '@/views/DetectRecordsView.vue';
import ThresholdsView from '@/views/ThresholdsView.vue';
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'login', component: LoginView },
    { path: '/chat', name: 'chat', component: AgentChatView },
    { path: '/detect', redirect: '/chat' },
    { path: '/fault-query/:categoryKey', name: 'fault-query', component: FaultQueryView, props: true },
    { path: '/multi-detect/:batchId', name: 'multi-detect', component: MultiDetectView, props: true },
    { path: '/detect-devices', name: 'detect-devices', component: DeviceListView },
    { path: '/detect/:sn', name: 'detect', component: DetectFlowView, props: true },
    { path: '/records', name: 'records', component: DetectRecordsView },
    { path: '/thresholds', name: 'thresholds', component: ThresholdsView },
  ],
});

export default router;
