<script setup lang="ts">
import { faultCategoryLabel } from '@/composables/faultCategories';
import { computed } from 'vue';
import { formatDeviceTime, formatDurationHours } from '@/utils/date';
import type { Device, FaultCategory } from '@/types/device';

const props = defineProps<{
  device: Device;
  selectedPathCategory?: FaultCategory;
}>();

defineEmits<{
  open: [sn: string];
}>();

const pathAligned = computed(() => (
  !props.selectedPathCategory || props.device.fault?.faultCategory === props.selectedPathCategory
));

const wearTime = computed(() => formatDurationHours(props.device.wearDays * 24 + props.device.wearHours));
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
        <span class="device-pill device-pill--wear">Wear {{ wearTime }}</span>
        <span class="device-pill device-pill--mute">{{ device.status }}</span>
        <span class="device-activation">
          <span class="device-pill device-pill--activated">Activated</span>
          <span class="device-activation-time">{{ formatDeviceTime(device.activatedAt) }}</span>
        </span>
      </span>
      <span class="device-card-meta">
        <span>Last data {{ device.lastDataAt }}</span>
      </span>
      <span class="device-card-action">
        <span>Continue with {{ faultCategoryLabel(selectedPathCategory ?? device.fault?.faultCategory) || 'No mapped fault' }}</span>
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
  border-radius: var(--radius-sm);
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

.device-pill--activated {
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(0, 168, 132, 0.18);
  background:
    linear-gradient(135deg, rgba(0, 168, 132, 0.14), rgba(0, 168, 132, 0.06));
  color: #047857;
  text-transform: none;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.58);
  white-space: nowrap;
}

.device-pill--activated::before {
  content: "";
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 3px rgba(0, 168, 132, 0.12);
}

.device-activation {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  max-width: 100%;
  flex-wrap: wrap;
}

.device-activation-time {
  min-width: 0;
  overflow-wrap: anywhere;
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
