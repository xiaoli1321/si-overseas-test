<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import DeviceCard from '@/components/detect/DeviceCard.vue';
import { useDemoStore } from '@/composables/useDemoStore';

const route = useRoute();
const router = useRouter();
const store = useDemoStore();
const page = ref(1);
const pageSize = ref(5);
const query = computed(() => String(route.query.q ?? '').trim());
const totalResults = computed(() => store.searchResults.value.length);
const pageCount = computed(() => Math.max(1, Math.ceil(totalResults.value / pageSize.value)));
const pageSlice = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return store.searchResults.value.slice(start, start + pageSize.value);
});
const resultsLabel = computed(() => {
  const count = totalResults.value;
  if (!query.value) return `${count} result(s)`;
  return `SN fuzzy match: "${query.value}" · ${count} result${count === 1 ? '' : 's'}`;
});
const paginationLabel = computed(() => {
  if (!totalResults.value) return 'No results';
  const start = (page.value - 1) * pageSize.value + 1;
  const end = Math.min(page.value * pageSize.value, totalResults.value);
  return `Showing ${start}-${end} of ${totalResults.value} results`;
});

watch(query, () => {
  if (query.value) {
    store.searchBySn(query.value);
  }
  page.value = 1;
}, { immediate: true });

watch([totalResults, pageSize], () => {
  if (page.value > pageCount.value) page.value = pageCount.value;
});

watch(pageSize, () => {
  page.value = 1;
});

function changePage(delta: number) {
  const next = page.value + delta;
  if (next < 1 || next > pageCount.value) return;
  page.value = next;
}

function openDevice(sn: string) {
  store.selectDevice(sn);
  const device = store.selectedDevice.value;
  const q = query.value;
  router.push({
    name: 'detect',
    params: { sn },
    query: {
      category: device?.fault.faultCategory ?? 'Data accuracy',
      from: 'device-detect',
      ...(q ? { q } : {}),
    },
  });
}
</script>

<template>
  <div class="page active" id="page-detect-devices">
    <div class="page-body">
      <div class="devices-header slide-up stagger-1">
        <div>
          <h1>Matched devices</h1>
          <p id="devices-email-label">{{ resultsLabel }}</p>
        </div>
        <button class="btn btn-secondary" type="button" @click="router.push({ name: 'chat' })">&#8592; Back to Device detection</button>
      </div>
      <div v-if="!store.searchResults.value.length" class="empty-state">Search first to reveal devices.</div>
      <div v-else class="device-grid">
        <DeviceCard
          v-for="device in pageSlice"
          :key="device.sn"
          :device="device"
          @open="openDevice"
        />
      </div>
      <div v-if="totalResults" class="pagination">
        <span>{{ paginationLabel }}</span>
        <div class="page-btns">
          <label class="page-size-control">
            <span>Per page</span>
            <select v-model.number="pageSize" class="form-select" aria-label="Devices per page">
              <option :value="5">5</option>
              <option :value="10">10</option>
              <option :value="20">20</option>
            </select>
          </label>
          <button class="btn btn-secondary btn-sm" type="button" :disabled="page <= 1" @click="changePage(-1)">Previous</button>
          <button class="btn btn-secondary btn-sm" type="button" :disabled="page >= pageCount" @click="changePage(1)">Next</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.device-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.page-size-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 0.78rem;
}
.page-size-control .form-select {
  width: auto;
  min-width: 74px;
  padding: 8px 10px;
}

@media (max-width: 760px) {
  .device-grid {
    grid-template-columns: 1fr;
  }
}
</style>
