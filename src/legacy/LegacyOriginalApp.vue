<script setup lang="ts">
import { onMounted, ref } from 'vue';
import originalHtml from '../../index_aligned_to_doc (1)_pdf-ch5-8-en.html?raw';
import { extractBodyMarkup, extractInlineScript } from './originalHtml';

const BOOT_KEY = '__siLegacyDemoBooted';

const host = ref<HTMLElement | null>(null);

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    const w = window as unknown as Window & Record<string, unknown>;
    if (w[BOOT_KEY]) {
      delete w[BOOT_KEY];
      window.location.reload();
    }
  });
}

onMounted(() => {
  const el = host.value;
  if (!el) return;

  el.innerHTML = extractBodyMarkup(originalHtml);

  const w = window as unknown as Window & Record<string, unknown>;
  if (w[BOOT_KEY]) return;
  w[BOOT_KEY] = true;

  const tag = document.createElement('script');
  tag.setAttribute('type', 'text/javascript');
  tag.setAttribute('data-si-legacy-demo', '');
  tag.textContent = extractInlineScript(originalHtml);
  document.body.appendChild(tag);
});
</script>

<template>
  <div ref="host" class="si-legacy-root"></div>
</template>
