<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { FAULT_CATEGORY_META, keyForFaultCategory } from '@/composables/faultCategories';
import { useAgentChat } from '@/composables/useAgentChat';
import { assistantMessageToHtml } from '@/utils/chatRichText';
import type { ChatFaultOption } from '@/types/chat';
import type { FaultCategory } from '@/types/device';

const router = useRouter();
const route = useRoute();
const chat = useAgentChat();
const draft = ref('');
const historyOpen = ref(false);
const threadRef = ref<HTMLElement | null>(null);

const messages = computed(() => chat.currentSession.value?.messages ?? []);
const historySessions = computed(() => chat.sessions.value);
const isResponding = computed(() => chat.isResponding.value);
const hasUserMessages = computed(() => messages.value.some(message => message.role === 'user'));
const isWelcomeLayout = computed(() => !hasUserMessages.value);
const faultCards = FAULT_CATEGORY_META;

async function submit() {
  await chat.sendMessage(draft.value);
  draft.value = '';
  await scrollThreadToBottom();
}

function openFaultCategory(category: FaultCategory) {
  router.push({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(category) },
    query: { from: 'chat' },
  });
}

function openFaultOption(option: ChatFaultOption) {
  router.push({
    name: 'fault-query',
    params: { categoryKey: option.key },
    query: { from: 'chat' },
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

function deleteHistory(sessionId: string, event: Event) {
  event.stopPropagation();
  chat.deleteSession(sessionId);
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

onMounted(() => {
  const sessionId = String(route.query.session ?? '');
  if (sessionId) {
    chat.openSession(sessionId);
  }
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
          <button class="btn btn-secondary btn-sm" type="button" aria-label="Open chat history" @click="historyOpen = !historyOpen">
            Chat history
          </button>
          <button class="btn btn-primary btn-sm" type="button" data-test="new-chat-button" @click="startNewChat">
            New chat
          </button>
        </div>
      </header>

      <aside v-if="historyOpen" class="chat-history-panel" aria-label="Chat history">
        <div class="chat-history-head">
          <strong>Chat history</strong>
        </div>
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
            class="chat-history-delete"
            type="button"
            :aria-label="`Delete ${session.title}`"
            data-test="delete-history-item"
            @click="deleteHistory(session.id, $event)"
          >
            Delete
          </button>
        </div>
      </aside>

      <div
        class="agent-chat-body"
        :class="{
          'agent-chat-body--welcome': isWelcomeLayout,
          'agent-chat-body--thread': hasUserMessages,
        }"
      >
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
            :class="`chat-message--${message.role}`"
          >
            <div class="chat-bubble">
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
            </div>
          </article>
        </section>

        <div v-if="isWelcomeLayout" class="agent-chat-welcome-title" aria-label="New chat welcome">
          <h1>What should we check?</h1>
        </div>

        <form class="agent-composer search-panel agent-composer--centered" @submit.prevent="submit">
          <textarea
            v-model="draft"
            aria-label="Describe the case"
            placeholder="Describe your device issue, and I'll help identify the possible cause."
            rows="2"
            :disabled="isResponding"
          ></textarea>
          <div class="composer-footer">
            <div class="composer-attachments">
              <span v-if="isResponding" class="streaming-indicator" data-test="streaming-indicator">Agent is responding...</span>
            </div>
            <button class="btn btn-primary" type="submit" :disabled="isResponding || !draft.trim()">Send</button>
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
  gap: 18px;
  width: min(980px, calc(100vw - 32px));
  height: calc(100vh - 132px);
  max-height: calc(100vh - 132px);
  margin: 0 auto;
  padding: 34px 0;
}

.agent-chat-shell--wide {
  gap: 12px;
  padding: 16px 0 20px;
  width: min(1040px, calc(100vw - 32px));
}

.agent-chat-shell--welcome {
  grid-template-rows: auto 1fr;
}

.agent-chat-body {
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
}

.agent-chat-body--thread {
  align-items: stretch;
  gap: 10px;
  width: 100%;
  max-width: 100%;
}

.agent-fault-entry-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  width: min(980px, 100%);
}

.agent-chat-body--welcome .agent-fault-entry-grid {
  gap: 10px;
  width: 100%;
  margin-top: clamp(8px, 1.2vh, 18px);
}

.agent-fault-entry-card,
.chat-fault-option {
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 12px;
  min-height: 164px;
  padding: 18px 18px 16px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.34);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.22s ease,
    border-color 0.22s ease,
    background 0.22s ease;
}

.agent-chat-body--welcome .agent-fault-entry-card {
  gap: 10px;
  min-height: 152px;
  padding: 15px 14px 13px;
  border-radius: 16px;
}

.agent-fault-entry-card--data-accuracy {
  border-color: rgba(0, 168, 132, 0.28);
}

.agent-fault-entry-card--application-failure {
  border-color: rgba(246, 166, 35, 0.3);
}

.agent-fault-entry-card:hover,
.chat-fault-option:hover {
  transform: translateY(-2px);
  border-color: rgba(0, 168, 132, 0.3);
  background: rgba(255, 255, 255, 0.48);
}

.agent-chat-body--welcome .agent-fault-entry-card:hover {
  transform: translateY(-1px);
}

.fault-entry-title {
  color: var(--text-primary);
  font-size: 0.98rem;
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
  font-size: 0.82rem;
  line-height: 1.45;
  min-height: 4.35em;
}

.agent-chat-body--welcome .fault-entry-copy {
  font-size: 0.88rem;
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
  border-radius: var(--radius-full);
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
  border-radius: var(--radius-full);
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
  padding: 8px 12px 8px;
  border-radius: 16px !important;
}

.agent-chat-body--welcome .agent-composer textarea,
.agent-chat-body--thread .agent-composer textarea {
  min-height: 36px;
  max-height: 56px;
  resize: none;
  line-height: 1.42;
}

.agent-chat-body--welcome .composer-footer,
.agent-chat-body--thread .composer-footer {
  padding-top: 4px;
}

.agent-chat-body--welcome .composer-footer .btn,
.agent-chat-body--thread .composer-footer .btn {
  padding-block: 6px;
  font-size: 0.88rem;
}

.agent-chat-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.agent-chat-header--welcome {
  justify-content: flex-end;
}

.agent-chat-actions,
.composer-footer,
.chat-history-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chat-history-panel {
  position: absolute;
  top: 88px;
  right: 0;
  z-index: 20;
  width: min(340px, calc(100vw - 40px));
  padding: 14px;
}

.chat-history-head {
  justify-content: space-between;
  margin-bottom: 8px;
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
  color: var(--text-secondary);
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
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
  border-radius: var(--radius-full);
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

.chat-fault-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
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
  font-size: 0.82rem;
  font-weight: 600;
}

@keyframes blink {
  50% { opacity: 0; }
}

.composer-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 20px;
}

.agent-composer textarea {
  width: 100%;
  min-height: 58px;
  max-height: 112px;
  resize: vertical;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  line-height: 1.55;
}

.composer-footer {
  justify-content: space-between;
  gap: 10px;
  padding-top: 8px;
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

  .agent-chat-actions .btn {
    flex: 1;
  }

  .agent-fault-entry-grid,
  .chat-fault-options {
    grid-template-columns: 1fr;
  }
}
</style>
