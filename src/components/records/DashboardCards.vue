<script setup lang="ts">
import { useDemoStore } from '@/composables/useDemoStore';

const store = useDemoStore();
</script>

<template>
  <div class="logs-summary">
    <article class="log-sum-card">
      <div class="lbl">Total runs logged</div>
      <div class="val">{{ store.dashboard.value.total }}</div>
    </article>
    <article class="log-sum-card">
      <div class="lbl">After-sales Allow</div>
      <div class="val">{{ store.dashboard.value.allowed }}</div>
    </article>
    <article class="log-sum-card">
      <div class="lbl">Not allow</div>
      <div class="val">{{ store.dashboard.value.notAllowed }}</div>
    </article>
    <article class="log-sum-card">
      <div class="lbl">Pending review</div>
      <div class="val">{{ store.dashboard.value.pending }}</div>
    </article>
  </div>
</template>
