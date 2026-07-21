<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

const props = defineProps<{ modelValue: string; placeholder?: string }>();
const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const calendarCursor = ref(new Date());

const monthFormatter = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' });
const weekdayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const monthLabel = computed(() => monthFormatter.format(calendarCursor.value));

const calendarDays = computed(() => {
  const year = calendarCursor.value.getFullYear();
  const month = calendarCursor.value.getMonth();
  const first = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const blanks = Array.from({ length: first.getDay() }, (_, i) => ({ key: `b-${i}`, label: '', value: '', blank: true }));
  const days = Array.from({ length: daysInMonth }, (_, i) => {
    const day = i + 1;
    const value = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return { key: value, label: String(day), value, blank: false };
  });
  return [...blanks, ...days];
});

function toggle() {
  open.value = !open.value;
  if (open.value && props.modelValue) {
    const parsed = new Date(`${props.modelValue}T00:00:00`);
    if (!Number.isNaN(parsed.getTime())) calendarCursor.value = parsed;
  }
}

function pick(value: string) {
  emit('update:modelValue', value);
  open.value = false;
}

function clear() {
  emit('update:modelValue', '');
  open.value = false;
}

function shiftMonth(delta: number) {
  calendarCursor.value = new Date(calendarCursor.value.getFullYear(), calendarCursor.value.getMonth() + delta, 1);
}

function onDocClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false;
}
onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));
</script>

<template>
  <div ref="root" class="edp" lang="en-US">
    <button type="button" class="edp-trigger" data-test="edp-trigger" @click.stop="toggle">
      <span :class="{ 'edp-placeholder': !modelValue }">{{ modelValue || placeholder || 'Select date' }}</span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M8 2v4M16 2v4" /></svg>
    </button>
    <div v-if="open" class="edp-panel" @click.stop>
      <div class="edp-head">
        <button type="button" class="edp-nav" aria-label="Previous month" @click="shiftMonth(-1)">‹</button>
        <strong>{{ monthLabel }}</strong>
        <button type="button" class="edp-nav" aria-label="Next month" @click="shiftMonth(1)">›</button>
      </div>
      <div class="edp-weekdays">
        <span v-for="w in weekdayLabels" :key="w">{{ w }}</span>
      </div>
      <div class="edp-grid">
        <button
          v-for="day in calendarDays"
          :key="day.key"
          type="button"
          class="edp-day"
          :class="{ 'is-blank': day.blank, 'is-selected': day.value && day.value === modelValue }"
          :disabled="day.blank"
          @click="!day.blank && pick(day.value)"
        >{{ day.label }}</button>
      </div>
      <div class="edp-foot">
        <button type="button" class="edp-clear" @click="clear">Clear</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.edp { position: relative; }
.edp-trigger {
  min-width: 168px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 42, 0.14);
  background: #fff;
  color: var(--text-primary);
  font-size: 0.86rem;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.edp-trigger:hover { border-color: rgba(15, 23, 42, 0.28); }
.edp-trigger:focus-visible { outline: none; border-color: #00a884; box-shadow: 0 0 0 3px rgba(0, 168, 132, 0.16); }
.edp-trigger svg { width: 15px; height: 15px; flex-shrink: 0; fill: none; stroke: #94a3b8; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.edp-placeholder { color: #94a3b8; }

.edp-panel {
  position: absolute;
  z-index: 90;
  top: calc(100% + 8px);
  left: 0;
  width: 268px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: #fff;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16);
}
.edp-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.edp-head strong { font-size: 0.9rem; color: var(--text-primary); }
.edp-nav {
  width: 30px; height: 30px;
  border: none; border-radius: 8px;
  background: rgba(15, 23, 42, 0.05);
  color: var(--text-primary);
  font-size: 1rem; cursor: pointer;
  transition: background 0.16s ease;
}
.edp-nav:hover { background: rgba(0, 168, 132, 0.12); color: #00806a; }
.edp-weekdays, .edp-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
.edp-weekdays { margin-bottom: 6px; }
.edp-weekdays span { text-align: center; font-size: 0.64rem; font-weight: 600; letter-spacing: 0.02em; color: #94a3b8; text-transform: uppercase; }
.edp-day {
  aspect-ratio: 1;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease;
}
.edp-day:hover:not(:disabled):not(.is-selected) { background: rgba(0, 168, 132, 0.12); }
.edp-day.is-selected { background: #00a884; color: #fff; font-weight: 700; }
.edp-day.is-blank { cursor: default; }
.edp-foot { display: flex; justify-content: flex-end; margin-top: 8px; }
.edp-clear {
  border: none; background: transparent;
  color: var(--text-secondary);
  font-size: 0.78rem; font-weight: 600;
  cursor: pointer; padding: 4px 6px;
}
.edp-clear:hover { color: #c5221f; }
</style>
