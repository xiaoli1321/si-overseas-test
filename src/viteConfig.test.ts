import { describe, expect, it } from 'vitest';
import { loadConfigFromFile } from 'vite';

describe('Vite module resolution', () => {
  it('loads TypeScript and Vue source files before stale generated JavaScript siblings', async () => {
    const loaded = await loadConfigFromFile(
      { command: 'serve', mode: 'development' },
      'vite.config.js',
      process.cwd(),
      undefined,
      undefined,
      'runner',
    );
    const extensions = loaded?.config.resolve?.extensions ?? [];

    expect(extensions).toContain('.ts');
    expect(extensions).toContain('.vue');
    expect(extensions).toContain('.js');
    expect(extensions.indexOf('.ts')).toBeLessThan(extensions.indexOf('.js'));
    expect(extensions.indexOf('.vue')).toBeLessThan(extensions.indexOf('.js'));
  });
});
