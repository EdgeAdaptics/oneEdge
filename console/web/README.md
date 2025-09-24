# Console Web

Next.js 14 app providing the oneEdge fleet console UI.

## Getting started

```bash
cd console/web
npm install
npm run dev
```

The UI expects `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8080`) to reach the console API. It provides three pages in this PoC:

- `/` – Fleet overview with live metrics fed by SSE.
- `/devices` – Device inventory with basic metadata.
- `/devices/[id]` – Device detail view with approve/quarantine actions wired to the API.
