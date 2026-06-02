<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { FAULT_CATEGORY_META, keyForFaultCategory } from '@/composables/faultCategories';
import { useAgentChat } from '@/composables/useAgentChat';
import { assistantMessageToHtml } from '@/utils/chatRichText';
import type { ChatFaultOption, ChatSession } from '@/types/chat';
import type { FaultCategory } from '@/types/device';

const CHAT_HISTORY_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

const router = useRouter();
const route = useRoute();
const chat = useAgentChat();
const draft = ref('');
const historyOpen = ref(false);
const threadRef = ref<HTMLElement | null>(null);
const historyMenuRef = ref<HTMLElement | null>(null);
const pendingDeleteSessionId = ref<string | null>(null);

const messages = computed(() => chat.currentSession.value?.messages ?? []);
const historySessions = computed(() => chat.sessions.value.filter(session => isRecentHistorySession(session) && (!session.messages || session.messages.length > 0)));
const isResponding = computed(() => chat.isResponding.value);
const hasUserMessages = computed(() => messages.value.some(message => message.role === 'user'));
const isWelcomeLayout = computed(() => !hasUserMessages.value);
const faultCards = FAULT_CATEGORY_META;
const pendingDeleteSession = computed(() => (
  historySessions.value.find(session => session.id === pendingDeleteSessionId.value) ?? null
));

const hasEmptyStreamingAssistantMessage = computed(() => {
  const last = messages.value[messages.value.length - 1];
  return last && last.role === 'assistant' && last.isStreaming && !last.content;
});

function isRecentHistorySession(session: ChatSession) {
  const updatedAt = Date.parse(session.updatedAt);
  return Number.isFinite(updatedAt) && Date.now() - updatedAt <= CHAT_HISTORY_WINDOW_MS;
}

async function submit() {
  await chat.sendMessage(draft.value);
  draft.value = '';
  await scrollThreadToBottom();
}

function onSubmitEnter(event: KeyboardEvent) {
  if (event.isComposing) return;
  if (isResponding.value || !draft.value.trim()) return;
  void submit();
}

function openFaultCategory(category: FaultCategory) {
  router.push({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(category) },
    query: { entry_source: 'shortcut' },
  });
}

function openFaultOption(option: ChatFaultOption) {
  router.push({
    name: 'fault-query',
    params: { categoryKey: option.key },
    query: { entry_source: 'recommendation' },
  });
}

function openHistory(sessionId: string) {
  chat.openSession(sessionId);
  historyOpen.value = false;
  router.replace({
    name: 'chat',
    query: { session: sessionId },
  });
  void scrollThreadToTop();
}

function startNewChat() {
  const session = chat.startNewChat();
  historyOpen.value = false;
  router.replace({
    name: 'chat',
    query: { session: session.id },
  });
  void scrollThreadToTop();
}

function requestDeleteHistory(sessionId: string, event: Event) {
  event.stopPropagation();
  pendingDeleteSessionId.value = sessionId;
}

function cancelDeleteHistory() {
  pendingDeleteSessionId.value = null;
}

function confirmDeleteHistory() {
  const sessionId = pendingDeleteSessionId.value;
  if (!sessionId) return;
  chat.deleteSession(sessionId);
  pendingDeleteSessionId.value = null;
  router.replace({
    name: 'chat',
    query: { session: chat.currentSessionId.value },
  });
}

function isActiveSession(sessionId: string) {
  return chat.currentSessionId.value === sessionId;
}

async function scrollThreadToTop() {
  await nextTick();
  if (threadRef.value) threadRef.value.scrollTop = 0;
}

async function scrollThreadToBottom() {
  await nextTick();
  if (threadRef.value) threadRef.value.scrollTop = threadRef.value.scrollHeight;
}

watch(() => chat.currentSessionId.value, () => {
  if (!isWelcomeLayout.value) {
    void scrollThreadToBottom();
  }
});

watch(() => messages.value, () => {
  void scrollThreadToBottom();
}, { deep: true });

function handleClickOutside(event: MouseEvent) {
  if (pendingDeleteSession.value) return;
  if (historyOpen.value && historyMenuRef.value && !historyMenuRef.value.contains(event.target as Node)) {
    historyOpen.value = false;
  }
}

onMounted(async () => {
  const querySessionId = String(route.query.session ?? '');
  await chat.bootstrap(querySessionId);

  watch(() => route.query.session, async (newSessionId) => {
    if (route.name !== 'chat') return;
    const sessionId = String(newSessionId ?? '');
    if (sessionId) {
      if (chat.currentSessionId.value !== sessionId) {
        await chat.openSession(sessionId);
      }
    } else {
      const current = chat.currentSession.value;
      if (current && current.messages && current.messages.length === 0) {
        router.replace({
          name: 'chat',
          query: { session: current.id },
        });
      } else {
        const session = chat.startNewChat();
        router.replace({
          name: 'chat',
          query: { session: session.id },
        });
      }
    }
  }, { immediate: true });

  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>

<template>
  <main class="page active agent-chat-page" id="page-agent-chat">
    <div
      class="agent-chat-shell"
      :class="{
        'agent-chat-shell--welcome': isWelcomeLayout,
        'agent-chat-shell--wide': isWelcomeLayout || hasUserMessages,
      }"
    >
      <header class="agent-chat-header" :class="{ 'agent-chat-header--welcome': isWelcomeLayout }">
        <div class="agent-chat-actions">
          <div class="chat-history-menu" ref="historyMenuRef">
            <button class="btn btn-secondary btn-sm" type="button" aria-label="Open chat history" @click="historyOpen = !historyOpen">
              Chat history
            </button>

            <aside v-if="historyOpen" class="chat-history-panel" aria-label="Chat history">
              <div class="chat-history-head">
                <strong>Chat history</strong>
              </div>
              <div class="chat-history-list">
                <div
                  v-for="session in historySessions"
                  :key="session.id"
                  class="chat-history-item"
                  :class="{ active: isActiveSession(session.id) }"
                >
                  <button class="chat-history-item-main" type="button" @click="openHistory(session.id)">
                    <span>{{ session.title }}</span>
                    <small>{{ new Date(session.updatedAt).toLocaleString('en') }}</small>
                  </button>
                  <button
                    class="chat-history-delete btn-danger"
                    type="button"
                    :aria-label="`Delete ${session.title}`"
                    data-test="delete-history-item"
                    @click="requestDeleteHistory(session.id, $event)"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </aside>
          </div>
          <button class="btn btn-primary btn-sm" type="button" data-test="new-chat-button" @click="startNewChat">
            New chat
          </button>
        </div>
      </header>

      <div
        class="agent-chat-body"
        :class="{
          'agent-chat-body--welcome': isWelcomeLayout,
          'agent-chat-body--thread': hasUserMessages,
        }"
      >
        <div v-if="isWelcomeLayout" class="welcome-ambient" aria-hidden="true">
          <span class="welcome-ambient-glow welcome-ambient-glow--primary"></span>
          <span class="welcome-ambient-glow welcome-ambient-glow--secondary"></span>
        </div>

        <section
          v-if="hasUserMessages"
          ref="threadRef"
          class="agent-chat-thread"
          aria-label="Agent conversation"
        >
          <article
            v-for="message in messages"
            :key="message.id"
            class="chat-message"
            :class="[
              `chat-message--${message.role}`,
              { 'chat-message--loading': message.role === 'assistant' && message.isStreaming && !message.content }
            ]"
          >
            <div class="chat-bubble">
              <template v-if="message.role === 'assistant' && message.isStreaming && !message.content">
                <div class="chat-loading-bubble" role="status" aria-label="Agent is responding" data-test="chat-loading-bubble">
                  <span class="chat-loading-mark" aria-hidden="true">
                    <span></span>
                    <span></span>
                    <span></span>
                  </span>
                </div>
              </template>
              <template v-else>
                <p v-if="message.role === 'assistant'" class="chat-bubble-plain">
                  <span class="chat-bubble-rich" v-html="assistantMessageToHtml(message.content)"></span><span v-if="message.isStreaming" class="streaming-cursor">|</span>
                </p>
                <p v-else class="chat-bubble-plain">
                  {{ message.content }}<span v-if="message.isStreaming" class="streaming-cursor">|</span>
                </p>
                <div v-if="message.options?.length && !message.isStreaming" class="chat-fault-options">
                  <button
                    v-for="option in message.options"
                    :key="option.category"
                    class="chat-fault-option"
                    :data-test="message.options.length === 1 ? 'recommended-fault-card' : 'assistant-fault-option'"
                    type="button"
                    @click="openFaultOption(option)"
                  >
                    <span class="fault-entry-title">{{ option.title }}</span>
                    <span class="fault-entry-copy">{{ option.copy }}</span>
                    <span class="fault-option-action">Continue</span>
                  </button>
                </div>
              </template>
            </div>
          </article>
          <article v-if="isResponding && !hasEmptyStreamingAssistantMessage" class="chat-message chat-message--assistant chat-message--loading" data-test="chat-loading-bubble">
            <div class="chat-loading-bubble" role="status" aria-label="Agent is responding">
              <span class="chat-loading-mark" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </span>
            </div>
          </article>
        </section>

        <div v-if="isWelcomeLayout" class="agent-chat-welcome-title" aria-label="New chat welcome">
          <h1>What issue are you experiencing?</h1>
        </div>

        <form class="agent-composer search-panel agent-composer--centered" @submit.prevent="submit">
          <textarea
            v-model="draft"
            aria-label="Describe the case"
            placeholder="Describe the issue you are experiencing. I will help identify the most likely cause."
            rows="1"
            :disabled="isResponding"
            @keydown.enter.exact.prevent="onSubmitEnter($event)"
          ></textarea>
          <div class="composer-actions">
            <span v-if="isResponding" class="streaming-indicator" data-test="streaming-indicator">Agent is responding...</span>
            <button class="btn-send-round" type="submit" :disabled="isResponding || !draft.trim()" aria-label="Send message">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="send-icon">
                <line x1="12" y1="19" x2="12" y2="5"></line>
                <polyline points="5 12 12 5 19 12"></polyline>
              </svg>
            </button>
          </div>
        </form>

        <Transition name="fault-entry">
          <section v-if="isWelcomeLayout" class="agent-fault-entry-grid" aria-label="Fault type shortcuts">
            <button
              v-for="card in faultCards"
              :key="card.category"
              class="agent-fault-entry-card"
              :class="`agent-fault-entry-card--${card.key}`"
              type="button"
              data-test="fault-entry-card"
              @click="openFaultCategory(card.category)"
            >
              <span class="fault-entry-title">{{ card.title }}</span>
              <span class="fault-entry-copy">{{ card.shortCopy }}</span>
              <span class="fault-entry-tags">
                <span
                  v-for="tag in card.tags"
                  :key="tag.label"
                  class="fault-path-chip"
                  :class="`fault-path-chip--${tag.kind}`"
                >{{ tag.label }}</span>
              </span>
            </button>
          </section>
        </Transition>
      </div>
    </div>

    <div v-if="pendingDeleteSession" class="modal-overlay chat-confirm-overlay" role="presentation" @click.self="cancelDeleteHistory">
      <section
        class="modal chat-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-delete-confirm-title"
        aria-describedby="chat-delete-confirm-description"
      >
        <h2 id="chat-delete-confirm-title">Delete this chat?</h2>
        <p id="chat-delete-confirm-description">
          This will remove "{{ pendingDeleteSession.title }}" from chat history.
        </p>
        <div class="modal-actions chat-confirm-actions">
          <button class="btn btn-secondary" type="button" @click="cancelDeleteHistory">Cancel</button>
          <button class="btn btn-danger" type="button" data-test="delete-history-confirm" @click="confirmDeleteHistory">Delete</button>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.agent-chat-page {
  min-height: calc(100vh - 86px);
}

.agent-chat-shell {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: var(--space-lg);
  width: min(980px, calc(100vw - 32px));
  height: calc(100vh - 132px);
  max-height: calc(100vh - 132px);
  margin: 0 auto;
  padding: var(--page-padding) 0;
}

.agent-chat-shell--wide {
  gap: var(--space-md);
  padding: 16px 0 20px;
  width: min(1040px, calc(100vw - 32px));
}

.agent-chat-shell--welcome {
  grid-template-rows: auto 1fr;
}

.agent-chat-body {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.agent-chat-body--welcome {
  justify-content: flex-start;
  align-items: stretch;
  padding-top: clamp(20px, 14vh, 140px);
  gap: clamp(10px, 1.6vh, 16px);
  width: 100%;
  max-width: 100%;
  margin-inline: auto;
  overflow: visible;
}

.welcome-ambient {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: visible;
  pointer-events: none;
}

.welcome-ambient-glow {
  position: absolute;
  left: 50%;
  top: clamp(70px, 16vh, 132px);
  display: block;
  width: min(980px, 104vw);
  height: 360px;
  border-radius: 999px;
  background:
    radial-gradient(
      ellipse at center,
      rgba(0, 184, 169, 0.22) 0%,
      rgba(52, 211, 203, 0.16) 34%,
      rgba(178, 244, 235, 0.1) 58%,
      rgba(255, 255, 255, 0) 78%
    );
  filter: blur(38px);
  opacity: 0.56;
  transform: translateX(-50%) translateY(20px) scale(0.96);
  animation: welcome-breath 8.5s ease-in-out infinite;
  will-change: transform, opacity, filter;
}

.welcome-ambient-glow--secondary {
  top: clamp(110px, 20vh, 164px);
  width: min(700px, 84vw);
  height: 230px;
  background:
    radial-gradient(
      ellipse at center,
      rgba(78, 140, 255, 0.13) 0%,
      rgba(0, 168, 132, 0.1) 42%,
      rgba(255, 255, 255, 0) 76%
    );
  filter: blur(42px);
  opacity: 0.38;
  animation-duration: 10.5s;
  animation-delay: -3.2s;
}

.agent-chat-body--thread {
  align-items: stretch;
  gap: var(--space-sm);
  width: 100%;
  max-width: 100%;
}

.agent-fault-entry-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-md);
  width: min(980px, 100%);
}

.agent-chat-body--welcome .agent-fault-entry-grid {
  gap: var(--space-sm);
  width: 100%;
  margin-top: clamp(8px, 1.2vh, 18px);
}

.agent-fault-entry-card,
.chat-fault-option {
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: var(--space-md);
  min-height: 164px;
  padding: var(--card-padding);
  border: 1px solid rgba(15, 118, 110, 0.12);
  border-radius: var(--radius-xl);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.5));
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(16px);
  transition:
    transform 0.22s ease,
    border-color 0.22s ease,
    background 0.22s ease,
    box-shadow 0.22s ease;
}

.agent-chat-body--welcome .agent-fault-entry-card {
  gap: var(--space-sm);
  min-height: 152px;
  padding: 15px 14px 13px;
  border-radius: var(--radius-lg);
}

.agent-fault-entry-card:hover,
.chat-fault-option:hover {
  transform: translateY(-2px);
  border-color: rgba(0, 168, 132, 0.28);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.86), rgba(255, 255, 255, 0.58));
  box-shadow: 0 22px 48px rgba(0, 128, 112, 0.08);
}

.agent-chat-body--welcome .agent-fault-entry-card:hover {
  transform: translateY(-1px);
}

.fault-entry-title {
  color: var(--text-primary);
  font-size: var(--text-base);
  font-weight: 800;
  line-height: 1.2;
  min-height: 2.4em;
  display: flex;
  align-items: flex-start;
}

.agent-chat-body--welcome .fault-entry-title {
  font-size: 1.04rem;
  min-height: 2.35em;
  line-height: 1.22;
}

.fault-entry-copy {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  line-height: 1.45;
  min-height: 4.35em;
}

.agent-chat-body--welcome .fault-entry-copy {
  font-size: var(--text-sm);
  line-height: 1.45;
  min-height: 3.25em;
}

.fault-entry-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-self: end;
  min-height: 58px;
  align-content: flex-end;
}

.agent-chat-body--welcome .fault-entry-tags {
  gap: 6px;
  min-height: 52px;
}

.agent-chat-body--welcome .fault-path-chip {
  padding: 5px 9px;
  font-size: 0.72rem;
}

.fault-path-chip {
  display: inline-flex;
  width: max-content;
  padding: 5px 9px;
  border-radius: var(--radius-sm);
  font-size: 0.68rem;
  font-weight: 800;
  line-height: 1.1;
  white-space: nowrap;
}

.fault-path-chip--check {
  background: rgba(0, 168, 132, 0.1);
  color: var(--accent);
}

.fault-path-chip--material {
  background: rgba(59, 130, 246, 0.1);
  color: #1d4ed8;
}

.fault-path-chip--outcome {
  background: rgba(15, 23, 42, 0.07);
  color: var(--text-secondary);
}

.fault-option-action {
  display: inline-flex;
  width: max-content;
  padding: 5px 9px;
  border-radius: var(--radius-sm);
  background: rgba(0, 168, 132, 0.1);
  color: var(--accent);
  font-size: 0.7rem;
  font-weight: 800;
  line-height: 1.1;
  white-space: nowrap;
}

.fault-entry-enter-active,
.fault-entry-leave-active {
  transition:
    opacity 0.24s ease,
    transform 0.24s ease,
    max-height 0.28s ease;
}

.fault-entry-enter-from,
.fault-entry-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-8px);
}

.fault-entry-enter-to,
.fault-entry-leave-from {
  max-height: 220px;
  opacity: 1;
  transform: translateY(0);
}

.agent-chat-body--welcome .fault-entry-enter-to,
.agent-chat-body--welcome .fault-entry-leave-from {
  max-height: 200px;
}

.agent-chat-welcome-title {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 100%;
  text-align: center;
}

.agent-chat-welcome-title h1 {
  margin: 10px 0 0;
  color: var(--text-primary);
  font-size: clamp(2rem, 5vw, 3.2rem);
  line-height: 1.02;
}

.agent-chat-body--welcome .agent-chat-welcome-title h1 {
  margin: 4px 0 0;
  font-size: clamp(1.35rem, 3.4vw, 2.05rem);
  line-height: 1.12;
}

.agent-composer--centered {
  position: relative;
  z-index: 1;
  width: min(820px, 100%);
  margin-inline: auto;
  margin-bottom: 0;
}

.agent-chat-body--welcome .agent-composer--centered,
.agent-chat-body--thread .agent-composer--centered {
  width: 100%;
  max-width: 100%;
}

.agent-chat-body--welcome .agent-composer.search-panel,
.agent-chat-body--thread .agent-composer.search-panel {
  padding: 6px 6px 6px 20px;
  border-radius: 9999px !important;
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.94) !important;
  border: 1px solid rgba(15, 118, 110, 0.14) !important;
  box-shadow:
    0 18px 46px rgba(15, 118, 110, 0.12),
    0 4px 18px rgba(15, 23, 42, 0.06) !important;
  backdrop-filter: blur(18px);
  transition:
    border-color 0.22s ease,
    box-shadow 0.22s ease,
    background 0.22s ease;
}

.agent-chat-body--welcome .agent-composer.search-panel:focus-within,
.agent-chat-body--thread .agent-composer.search-panel:focus-within {
  background: rgba(255, 255, 255, 0.98) !important;
  border-color: rgba(0, 168, 132, 0.3) !important;
  box-shadow:
    0 22px 58px rgba(0, 168, 132, 0.16),
    0 0 0 4px rgba(0, 168, 132, 0.08) !important;
}

.agent-chat-body--welcome .agent-composer textarea,
.agent-chat-body--thread .agent-composer textarea {
  min-height: 24px;
  max-height: 72px;
  resize: none;
  line-height: 24px;
  padding: 4px 0;
  margin: 0;
  border: 0;
  outline: 0;
  background: transparent !important;
  flex: 1;
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex-shrink: 0;
}

.btn-send-round {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50% !important;
  background: linear-gradient(135deg, #00b894 0%, #008f72 100%) !important;
  color: #ffffff !important;
  border: none !important;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
  padding: 0;
}

.btn-send-round:hover:not(:disabled) {
  background: linear-gradient(135deg, #00caa2 0%, #00987b 100%) !important;
  transform: scale(1.05);
  box-shadow: 0 10px 22px rgba(0, 168, 132, 0.22);
}

.btn-send-round:active:not(:disabled) {
  transform: scale(0.95);
}

.btn-send-round:disabled {
  background: rgba(15, 23, 42, 0.08) !important;
  color: rgba(15, 23, 42, 0.35) !important;
  cursor: not-allowed;
}

.btn-send-round .send-icon {
  width: 18px;
  height: 18px;
  stroke-width: 2.5px;
}

.agent-chat-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-lg);
}

.agent-chat-header--welcome {
  justify-content: flex-end;
}

.agent-chat-actions,
.composer-footer,
.chat-history-head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.chat-history-menu {
  position: relative;
  display: inline-flex;
}

.chat-history-panel {
  position: absolute;
  top: calc(100% + 10px);
  left: 0;
  z-index: 20;
  width: min(340px, calc(100vw - 40px));
  padding: 14px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(18px);
  display: flex;
  flex-direction: column;
}

.chat-history-head {
  justify-content: space-between;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.chat-history-list {
  max-height: 360px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-right: -4px;
  padding-right: 4px;
}

.chat-history-list::-webkit-scrollbar {
  width: 4px;
}

.chat-history-list::-webkit-scrollbar-track {
  background: transparent;
}

.chat-history-list::-webkit-scrollbar-thumb {
  background: rgba(15, 23, 42, 0.15);
  border-radius: 4px;
}

.chat-history-list::-webkit-scrollbar-thumb:hover {
  background: rgba(15, 23, 42, 0.3);
}

.chat-history-item {
  display: flex;
  align-items: stretch;
  gap: 8px;
  width: 100%;
  padding: 4px;
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  background: transparent;
}

.chat-history-item:hover,
.chat-history-item.active {
  background: rgba(0, 168, 132, 0.1);
}

.chat-history-item.active {
  border-color: rgba(0, 168, 132, 0.22);
}

.chat-history-item-main {
  display: grid;
  flex: 1;
  gap: 4px;
  padding: 8px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.chat-history-item-main small {
  color: var(--text-muted);
}

.chat-history-delete {
  flex-shrink: 0;
  align-self: center;
  padding: 6px 12px;
  border: 1px solid rgba(239, 68, 68, 0.3) !important;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, rgba(248, 113, 113, 0.92), rgba(220, 38, 38, 0.82)) !important;
  color: #ffffff !important;
  font-size: 0.72rem;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(220, 38, 38, 0.18) !important;
  transition:
    transform 0.2s ease,
    filter 0.2s ease,
    box-shadow 0.2s ease;
}

.chat-history-delete:hover {
  filter: brightness(1.04);
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(220, 38, 38, 0.24);
}

.chat-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.18);
}

.chat-confirm-modal {
  width: min(420px, 100%);
  padding: var(--card-padding);
}

.chat-confirm-modal h2 {
  margin: 0 0 8px;
  color: var(--text-primary);
  font-size: 1.1rem;
}

.chat-confirm-modal p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.5;
}

.chat-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: 20px;
}

.agent-chat-thread {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 2px 16px;
}

.agent-composer.agent-composer {
  flex-shrink: 0;
  width: min(820px, 100%);
  margin-inline: auto;
}

.agent-chat-body--welcome .agent-composer.agent-composer,
.agent-chat-body--thread .agent-composer.agent-composer {
  width: 100%;
  max-width: 100%;
}

.chat-message {
  display: flex;
}

.chat-message--user {
  justify-content: flex-end;
}

.chat-message--assistant {
  justify-content: flex-start;
}

.chat-message--loading {
  padding-top: 2px;
}

.chat-bubble {
  color: var(--text-primary);
}

.chat-message--user .chat-bubble {
  max-width: min(520px, 88%);
  padding: 12px 16px;
}

.chat-message--assistant .chat-bubble {
  max-width: min(760px, 100%);
  padding: 4px 0 20px;
}

.chat-bubble p {
  margin: 0;
  line-height: 1.65;
  white-space: pre-wrap;
}

.chat-bubble :deep(.chat-rich-strong) {
  font-weight: 800;
  color: var(--accent);
}

.chat-bubble :deep(.chat-rich-pill) {
  display: inline-block;
  margin: 0 2px;
  padding: 0.12em 0.5em;
  border-radius: var(--radius-sm);
  font-weight: 800;
  font-size: 0.9em;
  line-height: 1.25;
  background: rgba(0, 168, 132, 0.14);
  color: var(--accent);
  border: 1px solid rgba(0, 168, 132, 0.24);
  vertical-align: baseline;
}

.chat-bubble-rich {
  display: inline;
}

.chat-loading-bubble {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 54px;
  min-height: 36px;
  padding: 8px 12px;
  border: 1px solid rgba(0, 168, 132, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.44);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(14px);
}

.chat-loading-mark {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.chat-loading-mark span {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--accent);
  opacity: 0.4;
  animation: chat-loading-pulse 1s ease-in-out infinite;
}

.chat-loading-mark span:nth-child(2) {
  animation-delay: 0.14s;
}

.chat-loading-mark span:nth-child(3) {
  animation-delay: 0.28s;
}

.chat-fault-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-sm);
  margin-top: 14px;
}

.chat-fault-option {
  min-height: 116px;
}

.chat-fault-option .fault-entry-title,
.chat-fault-option .fault-entry-copy {
  min-height: 0;
}

.streaming-cursor {
  margin-left: 2px;
  color: var(--accent);
  animation: blink 0.9s step-end infinite;
}

.streaming-indicator {
  color: var(--accent);
  font-size: var(--text-xs);
  font-weight: 600;
}

@keyframes blink {
  50% { opacity: 0; }
}

@keyframes chat-loading-pulse {
  0%,
  80%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }

  40% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

@keyframes welcome-breath {
  0%,
  100% {
    opacity: 0.48;
    transform: translateX(-50%) translateY(26px) scale(0.94);
    filter: blur(30px);
  }

  50% {
    opacity: 0.82;
    transform: translateX(-50%) translateY(8px) scale(1.06);
    filter: blur(44px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .welcome-ambient-glow {
    animation: none;
    opacity: 0.54;
    transform: translateX(-50%) translateY(16px) scale(1);
  }
}

@media (max-width: 480px) {
  .agent-chat-shell {
    width: 100%;
    padding: 0;
    margin: 0;
    height: calc(100vh - 60px);
    max-height: calc(100vh - 60px);
  }

  .agent-chat-header {
    padding: 0 var(--page-padding);
  }

  .agent-chat-body {
    padding: 0 var(--page-padding);
  }

  .agent-chat-body--welcome {
    padding-top: clamp(18px, 8vh, 72px);
  }

  .welcome-ambient-glow {
    top: 44px;
    width: 110vw;
    height: 300px;
  }

  .chat-message--user .chat-bubble {
    max-width: 95%;
    padding: 10px 14px;
  }

  .chat-message--assistant .chat-bubble {
    max-width: 100%;
    padding: 4px 0 12px;
  }

  .chat-fault-options {
    grid-template-columns: 1fr;
  }

  .agent-chat-thread {
    padding: 6px 0 12px;
  }
}

.composer-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 20px;
}

.agent-composer textarea {
  width: 100%;
  min-height: 24px;
  max-height: 72px;
  resize: none;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  line-height: 24px;
  padding: 4px 0;
}

@media (max-width: 900px) {
  .agent-fault-entry-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .agent-chat-header,
  .composer-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .agent-chat-actions {
    width: 100%;
  }

  .chat-history-menu {
    flex: 1;
  }

  .agent-chat-actions .btn {
    flex: 1;
  }

  .chat-history-panel {
    width: min(340px, calc(100vw - 32px));
  }

  .agent-fault-entry-grid,
  .chat-fault-options {
    grid-template-columns: 1fr;
  }
}
</style>
