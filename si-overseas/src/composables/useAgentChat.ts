import { computed, ref } from 'vue';
import { backendApi } from '@/api/backend';
import { useDemoStore } from '@/composables/useDemoStore';
import { FAULT_CATEGORY_META, faultMetaForCategory } from '@/composables/faultCategories';
import { streamText } from '@/composables/streamText';
import {
  CHAT_AGENT_SCRIPTS,
  CHAT_FAULT_CATEGORY_BY_SN,
  CHAT_MAJOR_SCENARIO_KEYWORDS,
  CHAT_OFF_FOUR_PHRASES,
  CHAT_SCRIPT_BRACKET,
  CHAT_UNRELATED_PHRASES,
  textMatchesPhraseList,
} from '@/mocks/chatCases';
import type {
  ChatAttachment,
  ChatFaultOption,
  ChatMessage,
  ChatResultSummary,
  ChatSession,
  JudgeCaseResult,
} from '@/types/chat';
import type { Device, FaultCategory } from '@/types/device';

const CHAT_STORAGE_KEY = 'si-agent-chat-v1';
const UNRELATED_CARD_PROMPT_TURNS = positiveIntFromEnv(
  import.meta.env.VITE_UNRELATED_CARD_PROMPT_TURNS,
  3,
);
const SN_PATTERN = /P\d{10}[A-Z0-9]{5}/i;
const sessions = ref<ChatSession[]>(loadSessions());
const currentSessionId = ref(sessions.value[0]?.id ?? createSession().id);
const isResponding = ref(false);

function positiveIntFromEnv(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function nowIso() {
  return new Date().toISOString();
}

function makeId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createSession(): ChatSession {
  const session: ChatSession = {
    id: makeId('CHAT'),
    title: 'New device judgment',
    createdAt: nowIso(),
    updatedAt: nowIso(),
    messages: [],
  };
  sessions.value = [session, ...sessions.value];
  persistSessions();
  return session;
}

function loadSessions(): ChatSession[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatSession[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistSessions() {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(sessions.value));
}

function updateCurrentSession(updater: (session: ChatSession) => ChatSession) {
  sessions.value = sessions.value.map(session => (
    session.id === currentSessionId.value ? updater(session) : session
  ));
  persistSessions();
}

function getCurrentSession() {
  return sessions.value.find(session => session.id === currentSessionId.value) ?? sessions.value[0];
}

function isEmptySession(session: ChatSession | undefined) {
  return Boolean(session && session.messages && session.messages.length === 0);
}

function updateMessage(messageId: string, updater: (message: ChatMessage) => ChatMessage) {
  updateCurrentSession(session => ({
    ...session,
    updatedAt: nowIso(),
    messages: session.messages.map(message => (
      message.id === messageId ? updater(message) : message
    )),
  }));
}

function appendMessages(messages: ChatMessage[]) {
  updateCurrentSession(session => ({
    ...session,
    title: session.title === 'New device judgment'
      ? titleFromMessages([...session.messages, ...messages])
      : session.title,
    updatedAt: nowIso(),
    messages: [...session.messages, ...messages],
  }));
}

function titleFromMessages(messages: ChatMessage[]) {
  const userMessage = messages.find(message => message.role === 'user')?.content.trim();
  if (!userMessage) return 'New device judgment';
  const sn = userMessage.match(SN_PATTERN)?.[0]?.toUpperCase();
  if (sn) return sn;
  return userMessage.length > 42 ? `${userMessage.slice(0, 42)}...` : userMessage;
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}

function latestUserText(context: string) {
  const parts = context.split('\n').map(part => part.trim()).filter(Boolean);
  return parts[parts.length - 1] ?? context.trim();
}

function isUnrelatedText(text: string) {
  return textMatchesPhraseList(text, CHAT_UNRELATED_PHRASES);
}

function shouldPromptWithCards(turnCount: number) {
  return turnCount >= UNRELATED_CARD_PROMPT_TURNS;
}

function countUnrelatedUserTurns(messages: ChatMessage[]) {
  return messages.filter(message => (
    message.role === 'assistant' &&
    message.content === CHAT_AGENT_SCRIPTS.unrelated &&
    (!message.options || message.options.length === 0)
  )).length;
}

function inferFaultCategory(text: string): FaultCategory | undefined {
  const value = normalize(text);
  if (/(application|applicator|implant|site|photo|needle|bleed|adhesive|insertion)/.test(value)) {
    return 'Application failure';
  }
  if (/(fall|fell|drop|off|detach|loose|came off|falling)/.test(value)) {
    return 'Sensor falling off';
  }
  if (/(warm|warm-up|abnormal|probe|temporary|initialization|sensor error|failed sensor)/.test(value)) {
    return 'Sensor Abnormal';
  }
  if (/(inaccur|glucose|curve|flat|jump|low|reading|deviation|bias)/.test(value)) {
    return 'Data accuracy';
  }
  return undefined;
}

function extractSn(text: string) {
  return text.match(SN_PATTERN)?.[0]?.toUpperCase() ?? '';
}

function resolveDevice(sn: string): Device | undefined {
  if (!sn) return undefined;
  const store = useDemoStore();
  return store.findCachedDeviceBySn(sn) ?? store.findExactDeviceBySn(sn);
}

async function resolveDeviceRemote(sn: string): Promise<Device | undefined> {
  if (!sn) return undefined;
  const store = useDemoStore();
  if (!store.backendOnline.value) return resolveDevice(sn);
  return store.findExactDeviceBySnRemote(sn);
}

const MAJOR_SCENARIO_ORDER: FaultCategory[] = [
  'Data accuracy',
  'Application failure',
  'Sensor Abnormal',
  'Sensor falling off',
];

function matchMajorScenarioKeyword(text: string): FaultCategory | undefined {
  for (const category of MAJOR_SCENARIO_ORDER) {
    if (textMatchesPhraseList(text, CHAT_MAJOR_SCENARIO_KEYWORDS[category])) {
      return category;
    }
  }
  return undefined;
}

function faultOptionForCategory(category: FaultCategory): ChatFaultOption {
  const meta = faultMetaForCategory(category);
  return {
    category: meta.category,
    title: meta.title,
    copy: meta.shortCopy,
    key: meta.key,
  };
}

function allFaultOptions(): ChatFaultOption[] {
  return FAULT_CATEGORY_META.map(meta => ({
    category: meta.category,
    title: meta.title,
    copy: meta.shortCopy,
    key: meta.key,
  }));
}

export function judgeCase(
  context: string,
  _attachments: ChatAttachment[] = [],
  options: { unrelatedTurnCount?: number } = {},
): JudgeCaseResult {
  const sn = extractSn(context);
  const device = resolveDevice(sn);
  const currentText = latestUserText(context);

  if (isUnrelatedText(currentText)) {
    return {
      content: shouldPromptWithCards(options.unrelatedTurnCount ?? 1)
        ? CHAT_AGENT_SCRIPTS.offFour
        : CHAT_AGENT_SCRIPTS.unrelated,
      options: shouldPromptWithCards(options.unrelatedTurnCount ?? 1)
        ? allFaultOptions()
        : [],
    };
  }

  const majorPhraseCategory = matchMajorScenarioKeyword(context);
  if (majorPhraseCategory) {
    const option = faultOptionForCategory(majorPhraseCategory);
    return {
      content: CHAT_AGENT_SCRIPTS.major(CHAT_SCRIPT_BRACKET[majorPhraseCategory]),
      options: [option],
    };
  }

  if (textMatchesPhraseList(context, CHAT_OFF_FOUR_PHRASES)) {
    return {
      content: CHAT_AGENT_SCRIPTS.offFour,
      options: allFaultOptions(),
    };
  }

  const category = inferFaultCategory(context) ?? device?.fault?.faultCategory ?? CHAT_FAULT_CATEGORY_BY_SN.get(sn);

  if (category) {
    const option = faultOptionForCategory(category);
    return {
      content: CHAT_AGENT_SCRIPTS.major(CHAT_SCRIPT_BRACKET[category]),
      options: [option],
    };
  }

  return {
    content: CHAT_AGENT_SCRIPTS.offFour,
    options: allFaultOptions(),
  };
}

async function judgeCaseRemote(
  context: string,
  attachments: ChatAttachment[] = [],
  options: { unrelatedTurnCount?: number } = {},
): Promise<JudgeCaseResult> {
  const fallback = judgeCase(context, attachments, options);
  const store = useDemoStore();
  if (!store.backendOnline.value) return fallback;

  try {
    const sn = extractSn(context);
    const [device, classified] = await Promise.all([
      resolveDeviceRemote(sn),
      backendApi.classify(context),
    ]);
    const category = classified.faultCategory ?? (fallback.options.length === 1 ? fallback.options[0].category : undefined);

    if (category) {
      return {
        content: CHAT_AGENT_SCRIPTS.major(CHAT_SCRIPT_BRACKET[category]),
        options: [faultOptionForCategory(category)],
      };
    }

    if (classified.intentType === 'unrelated') {
      const priorCount = countUnrelatedUserTurns(getCurrentSession()?.messages ?? []);
      const shouldShowCards = shouldPromptWithCards(priorCount + 1);
      return {
        content: shouldShowCards
          ? CHAT_AGENT_SCRIPTS.offFour
          : (classified.message || CHAT_AGENT_SCRIPTS.unrelated),
        options: shouldShowCards ? allFaultOptions() : [],
      };
    }

    return {
      content: classified.message || CHAT_AGENT_SCRIPTS.offFour,
      options: allFaultOptions(),
    };
  } catch {
    return fallback;
  }
}

function userMessage(content: string): ChatMessage {
  return {
    id: makeId('MSG'),
    role: 'user',
    content,
    createdAt: nowIso(),
  };
}

function emptyAssistantMessage(): ChatMessage {
  return {
    id: makeId('MSG'),
    role: 'assistant',
    content: '',
    createdAt: nowIso(),
    isStreaming: true,
  };
}

async function streamAssistantReply(messageId: string, judgment: JudgeCaseResult) {
  updateMessage(messageId, message => ({
    ...message,
    options: judgment.options,
  }));

  await streamText(judgment.content, partial => {
    updateMessage(messageId, message => ({
      ...message,
      content: partial,
      isStreaming: true,
    }));
  });

  updateMessage(messageId, message => ({
    ...message,
    content: judgment.content,
    options: judgment.options,
    isStreaming: false,
  }));
}

async function sendMessage(content: string, _attachments: ChatAttachment[] = []) {
  const cleaned = content.trim();
  if (!cleaned) return;
  if (isResponding.value) return;

  const priorMessages = getCurrentSession()?.messages ?? [];
  const priorContext = priorMessages
    .filter(message => message.role === 'user')
    .map(message => message.content)
    .join('\n');
  const context = [priorContext, cleaned].filter(Boolean).join('\n');
  const unrelatedTurnCount = countUnrelatedUserTurns(priorMessages) + (isUnrelatedText(cleaned) ? 1 : 0);

  const userMsg = userMessage(cleaned);
  const assistant = emptyAssistantMessage();
  appendMessages([
    userMsg,
    assistant,
  ]);

  const store = useDemoStore();

  isResponding.value = true;
  try {
    let judgment: JudgeCaseResult;
    let persistedByTurnEndpoint = false;

    if (store.backendOnline.value) {
      try {
        const turn = await backendApi.sendChatTurn(currentSessionId.value, {
          id: userMsg.id,
          assistantId: assistant.id,
          content: userMsg.content,
        });
        judgment = {
          content: turn.assistantMessage.content,
          options: turn.assistantMessage.options ?? [],
        };
        persistedByTurnEndpoint = true;
      } catch (err) {
        console.warn('Failed to save chat turn on backend:', err);
        if (err && (err as any).isNetworkError) {
          judgment = judgeCase(context, _attachments, { unrelatedTurnCount });
        } else {
          judgment = await judgeCaseRemote(context, _attachments, { unrelatedTurnCount });
        }
      }
    } else {
      judgment = await judgeCaseRemote(context, _attachments, { unrelatedTurnCount });
    }

    await streamAssistantReply(assistant.id, judgment);

    if (store.backendOnline.value && !persistedByTurnEndpoint) {
      void backendApi.sendChatMessage(currentSessionId.value, {
        id: userMsg.id,
        role: userMsg.role,
        content: userMsg.content,
      }).catch(err => {
        console.warn('Failed to save user message on backend:', err);
      });

      void backendApi.sendChatMessage(currentSessionId.value, {
        id: assistant.id,
        role: assistant.role,
        content: judgment.content,
        options: judgment.options,
      }).catch(err => {
        console.warn('Failed to save assistant message on backend:', err);
      });

      const current = getCurrentSession();
      if (current) {
        const newTitle = titleFromMessages(current.messages);
        if (current.title !== newTitle) {
          updateCurrentSession(session => ({
            ...session,
            title: newTitle,
          }));
          void backendApi.updateChatSession(current.id, newTitle).catch(() => {});
        }
      }
    }
  } finally {
    isResponding.value = false;
  }
}

function startNewChat() {
  const current = getCurrentSession();
  if (isEmptySession(current)) {
    currentSessionId.value = current.id;
    return current;
  }

  const session = createSession();
  currentSessionId.value = session.id;
  const store = useDemoStore();
  if (store.backendOnline.value) {
    void backendApi.createChatSession(session.id, session.title).catch(err => {
      console.warn('Failed to create new session on backend:', err);
    });
  }
  return session;
}

function deleteSession(sessionId: string) {
  const remaining = sessions.value.filter(session => session.id !== sessionId);
  const store = useDemoStore();
  if (store.backendOnline.value) {
    void backendApi.deleteChatSession(sessionId).catch(err => {
      console.warn('Failed to delete session on backend:', err);
    });
  }
  if (!remaining.length) {
    clearHistory();
    return;
  }
  sessions.value = remaining;
  if (currentSessionId.value === sessionId) {
    currentSessionId.value = remaining[0].id;
    if (store.backendOnline.value) {
      void openSession(remaining[0].id);
    }
  }
  persistSessions();
}

async function openSession(sessionId: string) {
  if (sessions.value.some(session => session.id === sessionId)) {
    currentSessionId.value = sessionId;
    const store = useDemoStore();
    if (store.backendOnline.value) {
      try {
        const detail = await backendApi.getChatSession(sessionId);
        updateCurrentSession(() => detail);
      } catch (err) {
        console.warn('Failed to load chat session details:', err);
      }
    }
  }
}

function clearHistory() {
  const oldSessions = [...sessions.value];
  sessions.value = [];
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(CHAT_STORAGE_KEY);
  }
  const store = useDemoStore();
  if (store.backendOnline.value) {
    for (const s of oldSessions) {
      void backendApi.deleteChatSession(s.id).catch(() => {});
    }
  }
  const session = createSession();
  currentSessionId.value = session.id;
  if (store.backendOnline.value) {
    void backendApi.createChatSession(session.id, session.title).catch(() => {});
  }
}

async function bootstrap(initialSessionId?: string) {
  const store = useDemoStore();
  if (store.backendOnline.value) {
    try {
      const fetched = await backendApi.listChatSessions();
      
      const targetId = initialSessionId || currentSessionId.value;
      const current = sessions.value.find(s => s.id === targetId) || (targetId === currentSessionId.value ? getCurrentSession() : null);
      
      if (current && !fetched.some(s => s.id === current.id)) {
        sessions.value = [current, ...fetched];
      } else {
        sessions.value = fetched;
      }
      
      if (targetId) {
        currentSessionId.value = targetId;
        if (fetched.some(s => s.id === targetId)) {
          await openSession(targetId);
        } else if (!sessions.value.some(s => s.id === targetId)) {
          // Backend has no record of this session yet (e.g. a brand-new local id
          // or one dropped after a DB reset). Seed a local placeholder so the
          // current id always maps to a visible session — otherwise turns get
          // written on the backend but the UI has nowhere to render them. The
          // backend get-or-creates the session on the first turn.
          const seeded: ChatSession = {
            id: targetId,
            title: 'New device judgment',
            createdAt: nowIso(),
            updatedAt: nowIso(),
            messages: [],
          };
          sessions.value = [seeded, ...sessions.value];
          persistSessions();
        }
      } else if (fetched.length > 0) {
        currentSessionId.value = fetched[0].id;
        await openSession(fetched[0].id);
      } else {
        const session = createSession();
        currentSessionId.value = session.id;
        await backendApi.createChatSession(session.id, session.title);
      }
    } catch (err) {
      console.warn('Failed to bootstrap chat sessions from backend:', err);
    }
  }
}

function restoreResult(result: ChatResultSummary) {
  useDemoStore().restoreDetectRecord(result.record);
}

export function useAgentChat() {
  const currentSession = computed(() => (
    getCurrentSession()
  ));

  return {
    CHAT_STORAGE_KEY,
    currentSession,
    currentSessionId,
    sessions,
    isResponding,
    clearHistory,
    deleteSession,
    openSession,
    restoreResult,
    sendMessage,
    startNewChat,
    judgeCase,
    bootstrap,
  };
}
