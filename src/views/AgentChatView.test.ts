import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useAgentChat } from '@/composables/useAgentChat';
import { useDemoStore } from '@/composables/useDemoStore';
import AgentChatView from './AgentChatView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: AgentChatView },
      { path: '/fault-query/:categoryKey', name: 'fault-query', component: { template: '<div>Fault Query</div>' } },
      { path: '/detect/:sn', name: 'detect', component: { template: '<div>Detect</div>' } },
    ],
  });
}

async function mountChat(query: Record<string, string> = {}) {
  const router = makeRouter();
  await router.push({ name: 'chat', query });
  await router.isReady();
  const wrapper = mount(AgentChatView, {
    global: {
      plugins: [router],
    },
  });
  return { router, wrapper };
}

async function submitAndFinishStreaming(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  await vi.runAllTimersAsync();
  await flushPromises();
}

describe('AgentChatView', () => {
  afterEach(() => {
    vi.useRealTimers();
    useDemoStore().resetDemoState();
    useAgentChat().clearHistory();
    window.localStorage.clear();
  });

  it('renders fault cards and a compact composer in the welcome state', async () => {
    const { wrapper } = await mountChat();

    expect(wrapper.find('.agent-chat-shell--welcome').exists()).toBe(true);
    expect(wrapper.findAll('[data-test="fault-entry-card"]')).toHaveLength(4);
    expect(wrapper.findAll('[data-test="fault-entry-card"]')[0].text()).toContain('Differences from BGM');
    expect(wrapper.findAll('[data-test="fault-entry-card"]')[0].text()).toContain('Jump and down data.');
    expect(wrapper.findAll('[data-test="fault-entry-card"]')[0].text()).toContain('Glucose data in a straight line');
    expect(wrapper.find('textarea[aria-label="Describe the case"]').attributes('placeholder')).toBe(
      "Describe your device issue, and I'll help identify the possible cause.",
    );
    expect(wrapper.find('input[aria-label="Upload fault images"]').exists()).toBe(false);
    expect(wrapper.find('.image-upload-btn').exists()).toBe(false);
    expect(wrapper.find('[data-test="chat-result-card"]').exists()).toBe(false);
  });

  it('opens the selected fault query page from a welcome fault card', async () => {
    const { router, wrapper } = await mountChat();

    await wrapper.findAll('[data-test="fault-entry-card"]').find(card => card.text().includes('Sensor falling off'))?.trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(router.currentRoute.value.params.categoryKey).toBe('sensor-falling-off');
  });

  it('recommends one fault card after a clear user description without running detect', async () => {
    vi.useFakeTimers();
    const { router, wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The glucose curve is flat and readings are inaccurate.');
    await submitAndFinishStreaming(wrapper);

    expect(wrapper.find('.agent-chat-shell--welcome').exists()).toBe(false);
    expect(wrapper.find('.agent-fault-entry-grid').exists()).toBe(false);
    expect(wrapper.find('[data-test="recommended-fault-card"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="recommended-fault-card"]').text()).toContain('Data accuracy');
    expect(wrapper.find('[data-test="chat-result-card"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="chat-insight-card"]').exists()).toBe(false);
    expect(useDemoStore().records.value).toEqual([]);

    await wrapper.find('[data-test="recommended-fault-card"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(router.currentRoute.value.params.categoryKey).toBe('data-accuracy');
  });

  it('shows all fault choices when the description is ambiguous', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The customer needs help with this case.');
    await submitAndFinishStreaming(wrapper);

    expect(wrapper.find('[data-test="recommended-fault-card"]').exists()).toBe(false);
    expect(wrapper.findAll('[data-test="assistant-fault-option"]')).toHaveLength(4);
    expect(useDemoStore().records.value).toEqual([]);
  });

  it('does not auto-run detect even when the user provides a full SN', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('SN P2251212806JND44 has persistent low readings.');
    await submitAndFinishStreaming(wrapper);

    expect(wrapper.find('[data-test="recommended-fault-card"]').text()).toContain('Data accuracy');
    expect(wrapper.find('[data-test="chat-result-card"]').exists()).toBe(false);
    expect(useDemoStore().records.value).toEqual([]);
    expect(useDemoStore().sessions.value).toEqual([]);
  });

  it('starts a new chat from the header button', async () => {
    vi.useFakeTimers();
    const { router, wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The sensor fell off during wear.');
    await submitAndFinishStreaming(wrapper);
    const firstSessionId = useAgentChat().currentSessionId.value;

    await wrapper.find('button[data-test="new-chat-button"]').trigger('click');
    await flushPromises();

    const secondSessionId = useAgentChat().currentSessionId.value;
    expect(secondSessionId).not.toBe(firstSessionId);
    expect(router.currentRoute.value.query.session).toBe(secondSessionId);
    expect(wrapper.findAll('[data-test="fault-entry-card"]')).toHaveLength(4);
  });

  it('does not expose the old batch query modal entry', async () => {
    const { wrapper } = await mountChat();

    expect(wrapper.find('[data-test="batch-query-button"]').exists()).toBe(false);
    expect(wrapper.find('.batch-query-modal').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Batch Query');
  });
});
