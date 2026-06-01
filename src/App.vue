<script setup lang="ts">
import { computed } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import AppShell from '@/components/layout/AppShell.vue';

const route = useRoute();
const transitionName = computed(() => (
  route.name === 'login' ? 'page-fade' : 'page-slide'
));
</script>

<template>
  <AppShell>
    <RouterView v-slot="{ Component }">
      <Transition :name="transitionName" mode="out-in">
        <component :is="Component" :key="route.fullPath" />
      </Transition>
    </RouterView>
  </AppShell>
</template>

<style>
.page-fade-enter-active,
.page-fade-leave-active,
.page-slide-enter-active,
.page-slide-leave-active {
  transition:
    opacity 0.32s cubic-bezier(0.4, 0, 0.2, 1),
    transform 0.32s cubic-bezier(0.4, 0, 0.2, 1);
}

.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
}

.page-slide-enter-from {
  opacity: 0;
  transform: translateY(14px);
}

.page-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
