import { computed, ref } from 'vue';
import { useDemoStore } from '@/composables/useDemoStore';
import { FAULT_CATEGORY_META, faultMetaForCategory } from '@/composables/faultCategories';
import { streamText } from '@/composables/streamText';
import {
  CHAT_AGENT_SCRIPTS,
  CHAT_MAJOR_SCENARIO_KEYWORDS,
  CHAT_OFF_FOUR_PHRASES,
  CHAT_SCRIPT_BRACKET,
  CHAT_UNRELATED_PHRASES,
  textMatchesPhraseList,
} from '@/mocks/chatCases';
import type {
  ChatAttachment,
  ChatFaultOption,
  ChatJudgmentInsight,
  ChatMessage,
  ChatResultSummary,
  ChatSession,
  JudgeCaseResult,
} from '@/types/chat';
import type { Device, FaultCategory } from '@/types/device';

const CHAT_STORAGE_KEY = 'si-agent-chat-v1';
const SN_PATTERN = /P\d{10}[A-Z0-9]{5}/i;
const sessions = ref<ChatSession[]>(loadSessions());
const currentSessionId = ref(sessions.value[0]?.id ?? createSession().id);
const isResponding = ref(false);

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

function inferFaultCategory(text: string): FaultCategory | undefined {
  const value = normalize(text);
  if (/(application|applicator|implant|site|photo|needle|bleed|adhesive|insertion)/.test(value)) {
    return 'Application failure';
  }
  if (/(fall|fell|drop|off|detach|loose|came off|falling)/.test(value)) {
    return 'Sensor falling off';
  }
  if (/(warm|warm-up|abnormal|probe|temporary|initialization|sensor error|failed sensor)/.test(value)) {
    return 'Sensor Malfunction';
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
  return useDemoStore().findExactDeviceBySn(sn);
}

const MAJOR_SCENARIO_ORDER: FaultCategory[] = [
  'Data accuracy',
  'Application failure',
  'Sensor Malfunction',
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

function summarizeScenario(context: string, device?: Device) {
  const lines = context
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean);
  const descriptiveLine = lines.find(line => !SN_PATTERN.test(line) && line.length > 0);
  if (descriptiveLine) {
    return descriptiveLine.length > 160 ? `${descriptiveLine.slice(0, 160)}...` : descriptiveLine;
  }
  if (device) {
    return `Device lookup for ${device.sn}; mapped ${device.fault.faultCategory} profile from catalog.`;
  }
  const first = lines[0] ?? '';
  if (!first) return 'No scenario described yet.';
  return first.length > 160 ? `${first.slice(0, 160)}...` : first;
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

function buildInsight(context: string, category: FaultCategory | undefined, sn: string, device?: Device): ChatJudgmentInsight {
  return {
    scenarioSummary: summarizeScenario(context, device),
    sn: sn || '-',
    snStatus: sn ? (device ? 'found' : 'unknown') : 'missing',
    imageStatus: 'not_required',
    imageSummary: 'Images are collected later in the selected fault flow when required.',
    faultCategory: category,
  };
}

export function judgeCase(context: string, _attachments: ChatAttachment[] = []): JudgeCaseResult {
  const sn = extractSn(context);
  const device = resolveDevice(sn);

  if (textMatchesPhraseList(context, CHAT_UNRELATED_PHRASES)) {
    const insight = buildInsight(context, undefined, sn, device);
    return {
      content: CHAT_AGENT_SCRIPTS.unrelated,
      insight,
      options: [],
    };
  }

  const majorPhraseCategory = matchMajorScenarioKeyword(context);
  if (majorPhraseCategory) {
    const option = faultOptionForCategory(majorPhraseCategory);
    const insight = buildInsight(context, majorPhraseCategory, sn, device);
    return {
      content: CHAT_AGENT_SCRIPTS.major(CHAT_SCRIPT_BRACKET[majorPhraseCategory]),
      insight,
      options: [option],
    };
  }

  if (textMatchesPhraseList(context, CHAT_OFF_FOUR_PHRASES)) {
    const insight = buildInsight(context, undefined, sn, device);
    return {
      content: CHAT_AGENT_SCRIPTS.offFour,
      insight,
      options: allFaultOptions(),
    };
  }

  const category = inferFaultCategory(context) ?? device?.fault.faultCategory;
  const insight = buildInsight(context, category, sn, device);

  if (category) {
    const option = faultOptionForCategory(category);
    return {
      content: CHAT_AGENT_SCRIPTS.major(CHAT_SCRIPT_BRACKET[category]),
      insight,
      options: [option],
    };
  }

  return {
    content: CHAT_AGENT_SCRIPTS.offFour,
    insight,
    options: allFaultOptions(),
  };
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
    insight: judgment.insight,
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
    insight: judgment.insight,
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

  const assistant = emptyAssistantMessage();
  appendMessages([
    userMessage(cleaned),
    assistant,
  ]);

  isResponding.value = true;
  try {
    const judgment = judgeCase(context);
    await streamAssistantReply(assistant.id, judgment);
  } finally {
    isResponding.value = false;
  }
}

function startNewChat() {
  const session = createSession();
  currentSessionId.value = session.id;
  return session;
}

function deleteSession(sessionId: string) {
  const remaining = sessions.value.filter(session => session.id !== sessionId);
  if (!remaining.length) {
    clearHistory();
    return;
  }
  sessions.value = remaining;
  if (currentSessionId.value === sessionId) {
    currentSessionId.value = remaining[0].id;
  }
  persistSessions();
}

function openSession(sessionId: string) {
  if (sessions.value.some(session => session.id === sessionId)) {
    currentSessionId.value = sessionId;
  }
}

function clearHistory() {
  sessions.value = [];
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(CHAT_STORAGE_KEY);
  }
  const session = createSession();
  currentSessionId.value = session.id;
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
  };
}
