/**
 * Escape text for safe insertion into v-html after we add our own tags.
 */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Renders a small subset of markdown-style markers as HTML (no raw ** or [] visible).
 * - `**text**` → strong emphasis (accent)
 * - `[chip]` → highlighted pill
 */
export function assistantMessageToHtml(raw: string): string {
  let s = escapeHtml(raw);
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong class="chat-rich-strong">$1</strong>');
  s = s.replace(/\[([^\]]+)\]/g, '<span class="chat-rich-pill">$1</span>');
  return s;
}
