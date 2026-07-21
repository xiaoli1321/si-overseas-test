import { createRouter, createWebHistory } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import LoginView from '@/views/LoginView.vue';
import AgentChatView from '@/views/AgentChatView.vue';
import DeviceListView from '@/views/DeviceListView.vue';
import FaultQueryView from '@/views/FaultQueryView.vue';
import MultiDetectView from '@/views/MultiDetectView.vue';
import DetectFlowView from '@/views/DetectFlowView.vue';
import DetectRecordsView from '@/views/DetectRecordsView.vue';
import ThresholdsView from '@/views/ThresholdsView.vue';
import AccountCenterView from '@/views/AccountCenterView.vue';
import DashboardView from '@/views/DashboardView.vue';
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'login', component: LoginView },
    { path: '/chat', name: 'chat', component: AgentChatView },
    { path: '/detect', redirect: '/chat' },
    { path: '/fault-query/:categoryKey', name: 'fault-query', component: FaultQueryView, props: true },
    { path: '/multi-detect/:batchId', name: 'multi-detect', component: MultiDetectView, props: true },
    { path: '/detect-devices', name: 'detect-devices', component: DeviceListView },
    { path: '/detect/:sn([a-zA-Z0-9]{10,30})/new', name: 'detect-new', component: DetectFlowView, props: route => ({ sn: String(route.params.sn) }) },
    { path: '/detect/:sn([a-zA-Z0-9]{10,30})/records/:recordId', name: 'detect-record', component: DetectFlowView, props: route => ({ sn: String(route.params.sn) }) },
    { path: '/detect/:sn([a-zA-Z0-9]{10,30})', name: 'detect', component: DetectFlowView, props: true },
    { path: '/records', name: 'records', component: DetectRecordsView },
    { path: '/thresholds', name: 'thresholds', component: ThresholdsView },
    { path: '/accounts', name: 'accounts', component: AccountCenterView },
    { path: '/dashboard', name: 'dashboard', component: DashboardView },
    { path: '/:pathMatch(.*)*', name: 'not-found', redirect: '/chat' },
  ],
});

router.beforeEach((to, _from, next) => {
  const store = useDemoStore();
  const isLoggedIn = store.currentUser.value !== '';
  if (to.name === 'login') {
    next();
  } else if (!isLoggedIn) {
    next({ name: 'login' });
  } else {
    next();
  }
});

export default router;
