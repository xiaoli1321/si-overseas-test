import { afterEach, describe, expect, it } from 'vitest';
import {
  CHAT_AGENT_SCRIPTS,
  CHAT_MOCK_CASES_ALL,
  CHAT_SCRIPT_BRACKET,
} from '@/mocks/chatCases';
import { useAgentChat } from '@/composables/useAgentChat';
import { useDemoStore } from '@/composables/useDemoStore';

describe('useAgentChat judgeCase matrix', () => {
  afterEach(() => {
    useDemoStore().resetDemoState();
    useAgentChat().clearHistory();
  });

  it.each(CHAT_MOCK_CASES_ALL.map(testCase => [testCase.id, testCase] as const))(
    '%s',
    (_id, testCase) => {
      const chat = useAgentChat();
      const context = testCase.turns.map(turn => turn.text).join('\n');
      const judgment = chat.judgeCase(context);

      expect(judgment.result).toBeUndefined();
      expect(useDemoStore().records.value).toEqual([]);
      expect(useDemoStore().sessions.value).toEqual([]);

      if (testCase.expectedCategory) {
        expect(judgment.insight.faultCategory).toBe(testCase.expectedCategory);
      }
    },
  );

  it('returns all fault options and the off-four script when the description cannot be classified', () => {
    const judgment = useAgentChat().judgeCase('The customer needs help.');

    expect(judgment.insight.faultCategory).toBeUndefined();
    expect(judgment.content).toBe(CHAT_AGENT_SCRIPTS.offFour);
    expect(judgment.options.map(option => option.category)).toEqual([
      'Data accuracy',
      'Sensor falling off',
      'Sensor Malfunction',
      'Application failure',
    ]);
  });
});

describe('useAgentChat scripted replies', () => {
  afterEach(() => {
    useDemoStore().resetDemoState();
    useAgentChat().clearHistory();
  });

  it('uses the major-scenario script and a single fault card for data accuracy', () => {
    const judgment = useAgentChat().judgeCase('data accuracy');
    expect(judgment.content).toBe(
      CHAT_AGENT_SCRIPTS.major(CHAT_SCRIPT_BRACKET['Data accuracy']),
    );
    expect(judgment.options).toHaveLength(1);
    expect(judgment.options[0].category).toBe('Data accuracy');
  });

  it('returns unrelated script with no cards when the user is not discussing CGM', () => {
    const judgment = useAgentChat().judgeCase('not related to cgm');
    expect(judgment.content).toBe(CHAT_AGENT_SCRIPTS.unrelated);
    expect(judgment.options).toEqual([]);
    expect(judgment.insight.faultCategory).toBeUndefined();
  });
});
