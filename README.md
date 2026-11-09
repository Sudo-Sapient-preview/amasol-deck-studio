<img src="assets/icon.svg" width="64" height="64" alt="">

# amasol Deck Studio

A one-page chat tool that turns any input into an amasol PowerPoint deck. Type what you need into the message
box: a one-line ask, meeting notes or a finished outline. Drop files, folders or ZIPs anywhere on the page, or
paste them. Every deck is built with the `skill/` (amasol-deck) workflow and has to pass its checks before you
see it. Each deck is a thread in the sidebar; a follow-up message (with or without new files) builds the next
version, and every version stays downloadable.

## Run

```bash
./start.sh                 # serves UI + API on 0.0.0.0:4300
PORT=4310 ./start.sh       # another port
```

`start.sh` creates the skill venv (`skill/scripts/setup.sh`) and the server venv if they are missing, and
rebuilds the web app when its sources changed. The server needs `LLM_PROXY_BASE_URL` and `LLM_PROXY_API_KEY`
in the environment (the Anthropic-compatible LLM proxy). LibreOffice (`soffice`) and poppler (`pdftotext`,
`pdftoppm`) must be on PATH.

## Production (always on)

The app runs as the systemd user service `amasol-deck` (enabled, restarts on failure, starts at boot because
the user has linger on) and is public at **https://sudo-cloud.tail6d4c37.ts.net:8443** through Tailscale Funnel.
There is no login: anyone with the link can open every deck and start builds.

```bash
systemctl --user status amasol-deck          # state
journalctl --user -u amasol-deck -f          # logs
systemctl --user restart amasol-deck         # after a code change (rebuild web/ first: cd web && npm run build)
sudo tailscale funnel --https=8443 off       # take the public link down
```

### Vercel front end

The UI is also deployed on Vercel at **https://amasol-deck-studio.vercel.app** (project `amasol-deck-studio`,
team `janiths-projects`, config in `web/vercel.json`). Vercel serves only the static page: `/api/*` is
forwarded to the backend above, so the backend on this server must stay up. Vercel's proxy drops request
bodies over a few MB, so on `*.vercel.app` the page sends uploads straight to the backend URL in
`web/.env.production`, and the backend allows that origin through CORS (`server/app/main.py`).
Redeploy after UI changes: `cd web && npx vercel deploy --prod`.

The service reads `LLM_PROXY_BASE_URL` and `LLM_PROXY_API_KEY` from `~/.config/amasol-deck/env` (mode 600).
A restart stops builds that are running; check `/api/jobs` first.

Optional settings: `DECK_MODEL` (default `claude-opus-5-5`), `DECK_MAX_JOBS` (parallel builds, default 3),
`DECK_DATA_DIR` (default `data/`).

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
server/app/       FastAPI app: ingest, tools, agent loop, pipeline, report, job store
server/runner/    build_spec.py: JSON spec -> matchbuild.build(), runs in the skill venv
web/              Vite + React + Tailwind single-page UI
data/jobs/<id>/   job.json, events.jsonl, work/ (draft, plan, spec, renders), output/ (pptx, pdf, slides)
```
