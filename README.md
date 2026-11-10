<img src="assets/icon.svg" width="64" height="64" alt="">

# amasol Deck Studio

A one-page chat tool that turns any input into an amasol PowerPoint deck. Type what you need into the message
box: a one-line ask, meeting notes or a finished outline. Drop files, folders or ZIPs anywhere on the page, or
paste them. Every deck is built with the `skill/` (amasol-deck) workflow and has to pass its checks before you
see it. Each deck is a thread in the sidebar; a follow-up message (with or without new files) builds the next
version, and every version stays downloadable.

## Architecture

```
Browser ─┬─ /            web/      Vite React SPA (service "web")
         ├─ /api/upload  upload/   tiny Node fn with @vercel/blob (service "upload") → browser sends bytes straight to Blob
         └─ /api/*       server/   FastAPI fn (service "api") ── Postgres: jobs, events, draft
                                       └─ Sandbox "deck-<job>" from snapshot: python -m app.worker <job>
                                            runs today's pipeline unchanged on local disk; writes events/draft/status to Postgres, files to Blob
```

The api uses Postgres (Neon) to hold jobs, events and the live draft, and private Blob storage for files. Every
build gets its own Vercel Sandbox, started from a snapshot, running `python -m app.worker <job-id>`. A Vercel
Cron calls `/api/internal/sweep` every minute: it stops sandboxes whose job is finished and fails jobs whose
sandbox has gone quiet (a stale heartbeat).

## Live

**https://amasol.jgsaw.ai** (Vercel team "puneet-8736's projects", project `amasol-deck-studio`). The old
`amasol-deck-studio.vercel.app` link redirects there.

## Run locally

```bash
npx vercel link              # once, to the amasol-deck-studio project
npx vercel env pull .env.local
npx vercel dev --listen 0.0.0.0:<port>
```

`vercel dev` runs all three services (web, upload, api) together. A local run still uses the real cloud Neon
database, Blob store and Sandbox — there is no local-only mode. Vercel Crons do not run under `vercel dev`, so
`/api/internal/sweep` must be called by hand (or hit the deployed URL) to stop sandboxes or fail stale jobs
while testing locally.

## Deploy

When `server/` or `skill/` code changes, rebuild the sandbox snapshot the worker runs from:

```bash
python server/sandbox/image.py code --base <base-snapshot-id>   # current code on top of the base image
```

Only rebuild the base image (`python server/sandbox/image.py base`) when apt packages or `requirements.txt`
change — it reinstalls LibreOffice, poppler and both venvs from scratch.

Then point production at the new snapshot and deploy:

```bash
npx vercel env add DECK_SANDBOX_SNAPSHOT production   # paste the new snapshot id, or `vercel env rm` + `add` to replace it
npx vercel deploy --prod
```

## Env vars

- `DATABASE_URL` — Neon Postgres connection string
- `BLOB_READ_WRITE_TOKEN` — Vercel Blob store
- `LLM_PROXY_BASE_URL`, `LLM_PROXY_API_KEY` — the Anthropic-compatible LLM proxy
- `DECK_SANDBOX_SNAPSHOT` — snapshot id the API boots each build's sandbox from
- `CRON_SECRET` — checked on `/api/internal/sweep` so only the Vercel Cron can call it
- `DECK_MODEL` (optional) — default model, `claude-opus-5-5` if unset

## Tests

```bash
cd server && .venv/bin/python -m pytest -q tests/
```

Tests run against the real Neon database (in a throwaway schema) and the real Blob store (under a run-unique
prefix), not mocks.

## How a deck is built

| Stage | What runs | Gate the server checks itself |
|---|---|---|
| Read inputs | Files, folders, ZIPs and pasted text become text in `work/sources/`; images and reference files become page images; `scripts/intake.py classify`; `scripts/draftgen.py` starting draft | - |
| Storyline | The model writes `draft.md` in the standard draft format | `draft_check.py` PASS (and no skeleton slots for a bare ask) |
| Visuals and layouts | The model writes `plan.json` | `planlib.py check` PASS and `matcher.py` exit 0 |
| Build and verify | The model writes `spec.json`; `matchbuild.build()` builds the deck | `verify_deck.py --strict` ends in `RESULT: PASS` |
| Visual review | LibreOffice render, the model looks at every slide and fixes defects once | The delivered build passed verify and was rendered |

Each model stage is a tool loop (`server/app/llm.py`) over a fixed set of tools (`server/app/tools.py`) that wrap
the skill's own scripts. A stage ends only when its gate passes. If a later change breaks the deck, the last
build that passed verify is delivered. The hand-off report (verify result, assumptions, flagged items, edits,
plan, layouts, font note) is assembled from the scripts' outputs, not from model prose.

A follow-up message copies the last finished version and reruns the stages with the change request; files sent
with it are added to the sources. A message longer than 1,500 characters is treated as content (it is stored as
the source "Message"), so pasted notes are cited like any uploaded file.

## Layout

```
skill/            the amasol-deck skill (read-only for the app)
server/app/       FastAPI app: ingest, tools, agent loop, pipeline, job store, launcher, worker, blobs
server/runner/    build_spec.py: JSON spec -> matchbuild.build(), runs in the skill venv
server/sandbox/   image.py: builds the Vercel Sandbox snapshots the worker runs from
server/tests/     pytest against the real Neon DB and Blob store
upload/           tiny Node service: client-upload tokens for @vercel/blob
web/              Vite + React + Tailwind single-page UI
vercel.json       services web/upload/api, rewrites, the sweep cron
```
