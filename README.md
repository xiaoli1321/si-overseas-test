# SI Overseas Fault Detect Demo

SIBIONICS Fault Detect demo packaged with Vue 3, TypeScript, and Vite. The runtime loads `index_aligned_to_doc (1)_pdf-ch5-8-en.html` as the source of truth for the page markup, styles, and interactions, so the Vue build stays visually and behaviorally aligned with the original HTML demo.

## Requirements

- Node.js 20 or later
- npm

## Local Startup

Install dependencies:

```bash
npm install
```

Start the Vite dev server:

```bash
npm run dev
```

Open the URL printed by Vite, usually:

```text
http://localhost:5173/
```

The dev server uses `--host 0.0.0.0`, so the page can also be opened from other devices on the same LAN. Demo credentials are prefilled on the login page.

## Verification

Run unit tests:

```bash
npm test
```

Run TypeScript and Vue type checks:

```bash
npm run typecheck
```

Create a production build:

```bash
npm run build
```

Preview the production build locally:

```bash
npm run preview
```

## Deployment

1. Install dependencies on the build machine:

   ```bash
   npm install
   ```

2. Build the static assets:

   ```bash
   npm run build
   ```

3. Deploy the generated `dist/` directory to static hosting such as Nginx, Vercel, Netlify, or object-storage static hosting.

4. Configure SPA fallback so direct visits return `dist/index.html`.

### Nginx Example

```nginx
server {
  listen 80;
  server_name example.com;
  root /var/www/si-overseas/dist;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

## Implementation Notes

- `src/legacy/LegacyOriginalApp.vue` mounts the original HTML body and executes the original inline script.
- `src/main.ts` injects the original `<style>` block before Vue mounts.
- `src/legacy/originalHtml.ts` contains the HTML extraction helpers covered by Vitest.
- The original UI, animation, page switching, drawers, upload mocks, threshold controls, and detect-record interactions stay in the original HTML script; Vue/Vite only packages and serves the demo.
