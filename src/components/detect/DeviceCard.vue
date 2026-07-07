<script setup lang="ts">
import { computed } from 'vue';
import type { Device, FaultCategory } from '@/types/device';

const props = defineProps<{
  device: Device;
  selectedPathCategory?: FaultCategory;
}>();

defineEmits<{
  open: [sn: string];
}>();

const pathAligned = computed(() => (
  !props.selectedPathCategory || props.device.fault.faultCategory === props.selectedPathCategory
));

const pathLabel = computed(() => (
  pathAligned.value ? 'Matches selected path' : `Mapped: ${props.device.fault.faultCategory}`
));
</script>

<template>
  <button
    class="device-card"
    :class="{ 'device-card--aligned': pathAligned, 'device-card--other-path': !pathAligned }"
    type="button"
    @click="$emit('open', device.sn)"
  >
    <span class="device-card-rail" aria-hidden="true">
      <span class="device-card-dot" :class="pathAligned ? 'device-card-dot--on' : 'device-card-dot--warn'"></span>
    </span>
    <span class="device-card-inner">
      <span class="device-card-headline">
        <span class="device-sn-hero">{{ device.sn }}</span>
        <span class="device-type-badge">{{ device.type }}</span>
      </span>
      <span class="device-pill-row">
        <span class="device-pill device-pill--wear">Wear {{ device.wearDays }}d {{ device.wearHours }}h</span>
        <span class="device-pill device-pill--mute">{{ device.status }}</span>
        <span class="device-pill" :class="pathAligned ? 'device-pill--path' : 'device-pill--alert'">{{ pathLabel }}</span>
      </span>
      <span class="device-card-meta">
        <span>Activated {{ device.activatedAt }}</span>
        <span>Last data {{ device.lastDataAt }}</span>
      </span>
      <span class="device-card-action">
        <span>Continue with {{ selectedPathCategory ?? device.fault.faultCategory }}</span>
        <span class="device-card-chevron" aria-hidden="true">&rarr;</span>
      </span>
    </span>
  </button>
</template>

<style scoped>
.device-card {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 14px;
  width: 100%;
  padding: 18px 20px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 22px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.5), rgba(255, 255, 255, 0.22));
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.22s ease,
    border-color 0.22s ease,
    background 0.22s ease,
    box-shadow 0.22s ease;
}

.device-card:hover {
  transform: translateY(-2px);
  border-color: rgba(0, 168, 132, 0.28);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.3));
}

.device-card--other-path:hover {
  border-color: rgba(246, 166, 35, 0.35);
}

.device-card-rail {
  display: flex;
  padding-top: 4px;
}

.device-card-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.18);
}

.device-card-dot--on {
  background: var(--accent);
  box-shadow: 0 0 0 4px rgba(0, 168, 132, 0.14);
}

.device-card-dot--warn {
  background: #d97706;
  box-shadow: 0 0 0 4px rgba(217, 119, 6, 0.14);
}

.device-card-inner {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.device-card-headline,
.device-pill-row,
.device-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: center;
}

.device-card-headline {
  justify-content: space-between;
  gap: 10px;
}

.device-sn-hero {
  min-width: 0;
  overflow-wrap: anywhere;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 0.98rem;
  font-weight: 700;
  line-height: 1.2;
}

.device-type-badge,
.device-pill {
  display: inline-flex;
  width: max-content;
  padding: 5px 9px;
  border-radius: var(--radius-full);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  line-height: 1.1;
}

.device-type-badge {
  background: rgba(15, 23, 42, 0.07);
  color: var(--text-secondary);
}

.device-pill--wear {
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-secondary);
}

.device-pill--mute {
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-secondary);
  text-transform: capitalize;
}

.device-pill--path {
  background: rgba(0, 168, 132, 0.12);
  color: var(--accent);
}

.device-pill--alert {
  background: rgba(246, 166, 35, 0.14);
  color: #8a5a00;
}

.device-card-meta {
  color: var(--text-muted);
  font-size: 0.78rem;
  line-height: 1.45;
}

.device-card-meta span:not(:last-child)::after {
  content: "/";
  margin-left: 7px;
  color: rgba(15, 23, 42, 0.28);
}

.device-card-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 2px;
  color: var(--accent);
  font-size: 0.8rem;
  font-weight: 800;
}

.device-card--other-path .device-card-action {
  color: #9a6700;
}

.device-card-chevron {
  font-size: 1rem;
  line-height: 1;
  transition: transform 0.2s ease;
}

.device-card:hover .device-card-chevron {
  transform: translateX(3px);
}
</style>
