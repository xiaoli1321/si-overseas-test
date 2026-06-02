import { createApp } from 'vue';
import App from './App.vue';
import originalHtml from '../index_aligned_to_doc (1)_pdf-ch5-8-en.html?raw';
import { extractStyleBlock } from './legacy/originalHtml';
import './styles/main.css';
function installOriginalStyles() {
    const style = document.createElement('style');
    style.setAttribute('data-source', 'original-html');
    style.textContent = extractStyleBlock(originalHtml);
    document.head.appendChild(style);
}
installOriginalStyles();
createApp(App).mount('#app');
