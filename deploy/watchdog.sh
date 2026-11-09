#!/usr/bin/env bash
# Keep Deck Studio reachable. Run by amasol-deck-watchdog.timer every 2 minutes.
#  1. Backend (127.0.0.1:4300) must answer; after 3 failed tries 10 s apart, restart the service.
#     systemd's Restart=always already covers crashes; this covers a hung process.
#  2. Public route (Tailscale Funnel :8443) must answer; if not while the backend is fine, re-apply the rule.
#  3. The Vercel front end is checked and logged only (Vercel runs it; nothing to restart here).
set -u
LOCAL=http://127.0.0.1:4300/api/config
PUBLIC=https://sudo-cloud.tail6d4c37.ts.net:8443/api/config
VERCEL=https://amasol-deck-studio.vercel.app/api/config
ok() { curl -fsS -m 15 -o /dev/null "$1"; }

healthy=0
for i in 1 2 3; do
  if ok "$LOCAL"; then healthy=1; break; fi
  sleep 10
done
if [ "$healthy" = 0 ]; then
  echo "backend not answering after 3 tries: restarting amasol-deck"
  systemctl --user restart amasol-deck
  exit 0
fi

if ! ok "$PUBLIC" && ! { sleep 5; ok "$PUBLIC"; }; then
  echo "public Funnel route down: re-applying tailscale funnel on :8443"
  sudo -n tailscale funnel --bg --https=8443 http://127.0.0.1:4300 >/dev/null 2>&1 \
    || echo "could not re-apply the Funnel rule (sudo or tailscale failed)"
fi

ok "$VERCEL" || echo "Vercel front end not answering (https://amasol-deck-studio.vercel.app)"
exit 0
