function requireMatch(source: string, match: RegExpMatchArray | null, label: string): string {
  if (!match?.[1]) {
    throw new Error(`Unable to extract ${label} from original HTML.`);
  }
  return match[1].trim();
}

export function extractStyleBlock(html: string): string {
  return requireMatch(html, html.match(/<style\b[^>]*>([\s\S]*?)<\/style>/i), 'style block');
}

const LIGHT_THEME_OVERRIDES = `
/* ===== LIGHT-ONLY RUNTIME OVERRIDES ===== */
body {
  background: var(--page-gradient) !important;
  color: var(--text-primary) !important;
}
.app-bg-ambient::after {
  background: var(--page-gradient) !important;
}
.aurora-mesh {
  opacity: 0.5 !important;
  filter: saturate(1.02) !important;
  background:
    radial-gradient(ellipse 72% 58% at 10% 26%, rgba(0, 168, 132, 0.1), transparent 50%),
    radial-gradient(ellipse 58% 48% at 88% 18%, rgba(0, 168, 132, 0.06), transparent 46%),
    radial-gradient(ellipse 52% 62% at 76% 84%, rgba(0, 168, 132, 0.05), transparent 40%),
    radial-gradient(ellipse 45% 38% at 30% 92%, rgba(0, 168, 132, 0.04), transparent 38%) !important;
}
/* topbar/card glass handled in liquid-glass.css */
.btn-secondary {
  background: rgba(15, 23, 42, 0.05) !important;
  color: var(--text-primary) !important;
  border-color: rgba(15, 23, 42, 0.1) !important;
}
.btn-secondary:hover {
  background: rgba(0, 168, 132, 0.08) !important;
  border-color: rgba(0, 168, 132, 0.22) !important;
}
.btn-ghost:hover {
  color: var(--text-primary) !important;
  background: rgba(0, 168, 132, 0.06) !important;
}
.nav a:hover {
  color: var(--text-primary) !important;
  background: rgba(0, 168, 132, 0.06) !important;
}
.nav a.active {
  color: var(--accent) !important;
  background: rgba(0, 168, 132, 0.1) !important;
}
.user-pill {
  background: rgba(255, 255, 255, 0.9) !important;
  border-color: var(--border) !important;
}
.wave-layer { opacity: 0.35 !important; }
.wave-layer--top { opacity: 0.22 !important; }
.bg-grid-fine {
  background-image:
    linear-gradient(rgba(0, 168, 132, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 168, 132, 0.04) 1px, transparent 1px);
}
`;

export function normalizeLightOnlyStyleBlock(css: string): string {
  const withoutDarkRoot = css.replace(
    /:root\s*\{[^}]*--bg-deep:\s*#040810[\s\S]*?\}/,
    '',
  );

  return `${withoutDarkRoot
    .replace(/\[data-theme="light"\]\s*\{/g, ':root {')
    .replace(/\[data-theme="light"\]\s+/g, '')
    .replace(/\[data-theme="dark"\]\s+[^{]+\{[^}]*\}/g, '')
    .replace(/\.theme-toggle[^{]*\{[^}]*\}/g, '')
    .replace(/\.login-theme-toggle[^{]*\{[^}]*\}/g, '')}${LIGHT_THEME_OVERRIDES}`;
}

export function extractBodyMarkup(html: string): string {
  const body = requireMatch(html, html.match(/<body\b[^>]*>([\s\S]*?)<\/body>/i), 'body markup');
  const scriptStart = body.search(/<script\b/i);
  return (scriptStart === -1 ? body : body.slice(0, scriptStart)).trim();
}

export function extractInlineScript(html: string): string {
  const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)]
    .map(match => match[1].trim())
    .filter(Boolean);

  if (!scripts.length) {
    throw new Error('Unable to extract inline script from original HTML.');
  }

  return scripts.join('\n\n');
}
