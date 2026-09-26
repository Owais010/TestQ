# TestQ frontend

A local-first React + TypeScript workspace, built from scratch. The backend remains
unchanged. The welcome page opens at http://127.0.0.1:3000 (also available at
/welcome). Choose Open workspace to enter /dashboard.

## Start

Start the existing backend in one terminal, from the repository root:

```powershell
python backend/run.py
```

Then in another:

```powershell
cd frontend
npm ci
npm run dev
```

Node 22.12+ (or Node 20.19+) is required by Vite. The development server binds only
to loopback. /api and /health are proxied to http://127.0.0.1:8000. Fonts are bundled
locally; there are no runtime font CDN or paid service dependencies.

## Screens and behavior

- `/` and `/welcome`: editorial introduction, interactive 3D sculpture, scrolling
  capability strip with pause control, evidence illustration, workflow and FAQs.
- `/dashboard`: dashboard, latest-run summary, recent runs and workflow introduction.
- `/runs`: paginated history, current-page filters and new-run creation.
- `/runs/:id`: live progress, cancellation, application map, strategy, test plan, results, evidence,
  logs and existing backend failure analysis.
- `/projects`: repository cards derived from the latest 100 runs. The backend does
  not provide a projects-list endpoint; this view explicitly describes its scope.
- `/settings`: persisted motion preference, connection information and API docs.

The dashboard labels statistics scoped to the latest 12 runs. No sample metrics,
seeded records or canned findings are injected by the frontend. Starting a run sends
`discover: true`, with `testing_enabled` determined by the selected mode. Model and
AI configuration remain backend-owned. Discovery completion is not a QA pass verdict.

Run details poll every three seconds, lists every five seconds, and health every
15 seconds. Hidden browser tabs do not background-poll. Network failures, empty
states, unavailable discovery data, form errors and cancellation are surfaced.
Logs show the latest 500 matching records for readability (the current backend
endpoint returns the full log list). Evidence downloads use backend-provided,
validated per-run artifact paths. Test result assertions and steps are inspectable.

## Design and structure

Warm paper, ink, sage and terracotta; DM Sans with Instrument Serif. CSS tokens and
responsive rules are in `src/styles.css`. No neon, cursor replacement, scroll hijack,
autoplay video or mandatory WebGL dependency. The sculpture has a CSS fallback.

- `src/lib/`: typed API contracts, request/query helpers, motion preference.
- `src/components/`: reusable UI primitives, accessible Radix modal, WebGL sculpture.
- `src/pages/`: overview, history/projects, run details, editorial introduction.
- `src/App.tsx`: routes, responsive navigation, preferences and error boundary.
- `tests/`: browser workflows, mocked API contracts, accessibility and opt-in real API checks.

Motion powers scroll reveals, word entrances and a scroll progress line. Three.js
provides the mouse/scroll-responsive sculpture. Rendering pauses while offscreen or
backgrounded; reduced motion renders a static sculpture. All geometry/materials,
event listeners and animation handles are disposed on unmount. System reduced-motion
and the workspace preference are respected. Modal focus is trapped and restored;
mobile navigation traps focus, makes the background inert, and closes with Escape.

## Verification

```powershell
npm run build
npx playwright install chromium
npm test
# Optional: existing backend running, read-only live verification
$env:TESTQ_LIVE = '1'
npm test
```

Mutation tests use intercepted API responses, so the test suite does not create or
cancel actual repository runs. The opt-in live test reads existing backend data.
Axe checks cover the overview, run dialog and mobile introduction; they supplement,
not replace, manual accessibility review. Screenshots are written to test-results/.

Verified on September 26, 2026: production build and formatting checks passed;
all 15 Chromium browser tests passed (14 intercepted-API tests and one read-only
live-backend test). Desktop and mobile screenshots were visually inspected.
Coverage includes navigation, run creation and cancellation contracts, error and
empty states, keyboard focus, reduced motion, responsive overflow and Axe checks.
It also covers welcome entry routes, CTAs, FAQ toggles, marquee pause/resume,
live system-motion changes, run pagination/filtering, log filtering, persisted
preferences and evidence download controls. The live check downloads an existing
artifact when available. Mobile navigation closes before opening the run dialog.
The live check reads existing records; it does not prove a new repository execution.
Backend execution tests were not rerun for this frontend-only change.

## Production

`npm run build` writes `dist/`. `npm run preview` previews it locally on port 3000
with the same backend proxy. For deployment, serve dist with an SPA fallback to
index.html, and reverse-proxy /api and /health to the backend. Or set
`VITE_API_BASE_URL` in .env.local **before building**. That origin must be allowed by
the backend's CORS configuration. No authentication or multi-user authorization is
added by this frontend; preserve the backend's intended local deployment boundary.
The previous backend /dashboard route is not replaced; open the new frontend URL.
