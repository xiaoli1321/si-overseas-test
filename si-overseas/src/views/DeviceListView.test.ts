import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import DeviceListView from './DeviceListView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: { template: '<div>Chat</div>' } },
      { path: '/detect-devices', name: 'detect-devices', component: DeviceListView },
      { path: '/detect/:sn', name: 'detect', component: { template: '<div>Detect</div>' } },
    ],
  });
}

describe('DeviceListView', () => {
  afterEach(() => {
    useDemoStore().resetDemoState();
  });

  it('returns directly to Device Detection from fuzzy results', async () => {
    const router = makeRouter();
    await router.push({ name: 'detect-devices', query: { q: 'JND44' } });
    await router.isReady();

    const wrapper = mount(DeviceListView, {
      global: {
        plugins: [router],
      },
    });

    await wrapper.find('.devices-header .btn-secondary').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
  });

  it('returns from a single-device result back to chat with one click', async () => {
    const router = makeRouter();
    await router.push({ name: 'chat' });
    await router.push({ name: 'detect-devices', query: { q: 'JND44' } });
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Data accuracy', from: 'device-detect', q: 'JND44' },
    });
    await router.replace({ name: 'detect-devices', query: { q: 'JND44', fromDetect: '1' } });
    await router.isReady();

    const wrapper = mount(DeviceListView, {
      global: {
        plugins: [router],
      },
    });

    await wrapper.find('.devices-header .btn-secondary').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
  });

  it('paginates fuzzy results with five devices by default and a configurable page size', async () => {
    const router = makeRouter();
    await router.push({ name: 'detect-devices', query: { q: 'P22512128' } });
    await router.isReady();

    const wrapper = mount(DeviceListView, {
      global: {
        plugins: [router],
      },
    });

    expect(wrapper.findAll('.device-card')).toHaveLength(5);
    expect(wrapper.find('.pagination').text()).toContain('Showing 1-5');

    await wrapper.find('.page-btns button:last-child').trigger('click');
    await flushPromises();

    expect(wrapper.find('.pagination').text()).toContain('Showing 6-10');

    await wrapper.find('select[aria-label="Devices per page"]').setValue('10');
    await flushPromises();

    expect(wrapper.findAll('.device-card')).toHaveLength(10);
    expect(wrapper.find('.pagination').text()).toContain('Showing 1-10');
  });
});
