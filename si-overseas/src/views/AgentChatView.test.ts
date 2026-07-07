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
    expect(wrapper.findAll('[data-test="fault-entry-card"]')[0].text()).toContain('Sudden Glucose Fluctuations.');
    expect(wrapper.findAll('[data-test="fault-entry-card"]')[0].text()).toContain('Flat Glucose Readings');
    expect(wrapper.find('textarea[aria-label="Describe the case"]').attributes('placeholder')).toBe(
      "Describe the issue you are experiencing. I will help identify the most likely cause.",
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
    expect(useDemoStore().records.value).toEqual([]);

    await wrapper.find('[data-test="recommended-fault-card"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(router.currentRoute.value.params.categoryKey).toBe('data-accuracy');
  });

  it('shows an animated loading bubble while the agent is responding', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The glucose curve is flat and readings are inaccurate.');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(wrapper.find('[data-test="chat-loading-bubble"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="streaming-indicator"]').text()).toContain('Agent is responding');

    await vi.runAllTimersAsync();
    await flushPromises();
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

  it('delays card choices until the third unrelated user turn', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();
    const unrelatedMessage = 'This is not related to CGM.';

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue(unrelatedMessage);
    await submitAndFinishStreaming(wrapper);
    expect(wrapper.findAll('[data-test="assistant-fault-option"]')).toHaveLength(0);

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue(unrelatedMessage);
    await submitAndFinishStreaming(wrapper);
    expect(wrapper.findAll('[data-test="assistant-fault-option"]')).toHaveLength(0);

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue(unrelatedMessage);
    await submitAndFinishStreaming(wrapper);
    expect(wrapper.findAll('[data-test="assistant-fault-option"]')).toHaveLength(4);
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

  it('does not create duplicates while the current new chat is still blank', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('[data-test="new-chat-button"]').trigger('click');
    const firstBlankSessionId = useAgentChat().currentSessionId.value;
    const sessionCount = useAgentChat().sessions.value.length;

    await wrapper.find('[data-test="new-chat-button"]').trigger('click');
    await wrapper.find('[data-test="new-chat-button"]').trigger('click');

    expect(useAgentChat().currentSessionId.value).toBe(firstBlankSessionId);
    expect(useAgentChat().sessions.value).toHaveLength(sessionCount);
  });

  it('creates a fresh blank chat when the current session already has messages', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The glucose curve is flat and readings are inaccurate.');
    await submitAndFinishStreaming(wrapper);
    const messageSessionId = useAgentChat().currentSessionId.value;

    await wrapper.find('[data-test="new-chat-button"]').trigger('click');

    expect(useAgentChat().currentSessionId.value).not.toBe(messageSessionId);
    expect(useAgentChat().currentSession.value?.messages).toEqual([]);
  });

  it('uses danger styling for destructive chat history actions', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The sensor fell off during wear.');
    await submitAndFinishStreaming(wrapper);
    await wrapper.find('button[aria-label="Open chat history"]').trigger('click');

    const deleteButton = wrapper.find('[data-test="delete-history-item"]');
    expect(deleteButton.exists()).toBe(true);
    expect(deleteButton.classes()).toContain('chat-history-delete');
    expect(deleteButton.classes()).toContain('btn-danger');
  });

  it('only shows chat history sessions updated within the last week', async () => {
    const { wrapper } = await mountChat();
    const chat = useAgentChat();
    const now = new Date();
    const mockMessage = { id: 'msg-1', role: 'user', content: 'test', createdAt: now.toISOString() };
    const recentSession = {
      id: 'CHAT-recent',
      title: 'Recent inaccuracy case',
      createdAt: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      updatedAt: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      messages: [mockMessage],
    };
    const oldSession = {
      id: 'CHAT-old',
      title: 'Old falling off case',
      createdAt: new Date(now.getTime() - 9 * 24 * 60 * 60 * 1000).toISOString(),
      updatedAt: new Date(now.getTime() - 9 * 24 * 60 * 60 * 1000).toISOString(),
      messages: [mockMessage],
    };
    chat.sessions.value = [recentSession, oldSession, ...chat.sessions.value];

    await wrapper.find('button[aria-label="Open chat history"]').trigger('click');

    expect(wrapper.find('.chat-history-panel').text()).toContain('Recent inaccuracy case');
    expect(wrapper.find('.chat-history-panel').text()).not.toContain('Old falling off case');
  });

  it('confirms before deleting a chat history item', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The sensor fell off during wear.');
    await submitAndFinishStreaming(wrapper);
    const sessionId = useAgentChat().currentSessionId.value;
    const sessionCount = useAgentChat().sessions.value.length;
    await wrapper.find('button[aria-label="Open chat history"]').trigger('click');

    await wrapper.find('[data-test="delete-history-item"]').trigger('click');

    expect(useAgentChat().sessions.value).toHaveLength(sessionCount);
    expect(wrapper.find('.chat-confirm-modal').text()).toContain('Delete this chat?');

    await wrapper.find('[data-test="delete-history-confirm"]').trigger('click');

    expect(useAgentChat().sessions.value).toHaveLength(sessionCount);
    expect(useAgentChat().sessions.value.some(session => session.id === sessionId)).toBe(false);
    expect(wrapper.find('.chat-confirm-modal').exists()).toBe(false);
  });

  it('does not expose the old batch query modal entry', async () => {
    const { wrapper } = await mountChat();

    expect(wrapper.find('[data-test="batch-query-button"]').exists()).toBe(false);
    expect(wrapper.find('.batch-query-modal').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Batch Query');
  });

  it('closes the chat history menu when clicking outside', async () => {
    const { wrapper } = await mountChat();

    // The history panel is closed initially
    expect(wrapper.find('.chat-history-panel').exists()).toBe(false);

    // Open chat history
    await wrapper.find('button[aria-label="Open chat history"]').trigger('click');
    expect(wrapper.find('.chat-history-panel').exists()).toBe(true);

    // Click inside the menu (e.g. inside the chat history panel)
    await wrapper.find('.chat-history-panel').trigger('click');
    expect(wrapper.find('.chat-history-panel').exists()).toBe(true);

    // Dispatch a click event on document (outside the menu)
    document.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushPromises();

    // Verify it is closed
    expect(wrapper.find('.chat-history-panel').exists()).toBe(false);
  });

  it('does not close the chat history menu when clicking outside while delete confirmation is open', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountChat();

    await wrapper.find('textarea[aria-label="Describe the case"]').setValue('The sensor fell off during wear.');
    await submitAndFinishStreaming(wrapper);

    // Open chat history
    await wrapper.find('button[aria-label="Open chat history"]').trigger('click');
    expect(wrapper.find('.chat-history-panel').exists()).toBe(true);

    // Click the delete button to open the confirmation modal
    await wrapper.find('[data-test="delete-history-item"]').trigger('click');
    expect(wrapper.find('.chat-confirm-modal').exists()).toBe(true);

    // Dispatch a click event on document (outside the menu, e.g. clicking the modal overlay or outside)
    document.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushPromises();

    // The confirmation modal and chat history panel should both remain open
    expect(wrapper.find('.chat-confirm-modal').exists()).toBe(true);
    expect(wrapper.find('.chat-history-panel').exists()).toBe(true);

    // Cancel delete
    await wrapper.find('.chat-confirm-actions button.btn-secondary').trigger('click');
    expect(wrapper.find('.chat-confirm-modal').exists()).toBe(false);
    expect(wrapper.find('.chat-history-panel').exists()).toBe(true); // Panel still open since we just cancelled delete

    // Now clicking outside should close the history panel
    document.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushPromises();
    expect(wrapper.find('.chat-history-panel').exists()).toBe(false);
  });
});
