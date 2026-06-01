import { createApp } from 'vue';
import App from './App.vue';
import originalHtml from '../index_aligned_to_doc (1)_pdf-ch5-8-en.html?raw';
import { extractStyleBlock, normalizeLightOnlyStyleBlock } from './legacy/originalHtml';
import router from './router';
import liquidGlassCss from './styles/liquid-glass.css?inline';
import './styles/main.css';

function installOriginalStyles() {
  document.documentElement.removeAttribute('data-theme');
  const style = document.createElement('style');
  style.setAttribute('data-source', 'original-html');
  style.textContent = normalizeLightOnlyStyleBlock(extractStyleBlock(originalHtml));
  document.head.appendChild(style);
}

function installLiquidGlassStyles() {
  const style = document.createElement('style');
  style.setAttribute('data-source', 'liquid-glass');
  style.textContent = liquidGlassCss;
  document.head.appendChild(style);
}

installOriginalStyles();
installLiquidGlassStyles();
createApp(App).use(router).mount('#app');
