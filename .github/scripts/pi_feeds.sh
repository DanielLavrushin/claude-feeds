#!/bin/sh
# Runs on Daniel's Raspberry Pi (192.168.1.200) from cron, before the 07:30 digest. ntc.party refuses GitHub's
# runners, and Habr and gfw.report refuse the digest's cloud shell, so this box collects them and pushes:
#   dpi-feeds/ntc.jsonl + ntc_collected_at.txt, or ntc_error.txt on failure (the last good snapshot stays)
#   dpi-feeds/web.jsonl + web_collected_at.txt, plus web_error.txt naming any source that failed
# crontab: 30 6 * * * sh "$HOME/claude-feeds/.github/scripts/pi_feeds.sh" >> "$HOME/.cache/pi_feeds.log" 2>&1
# ntc.party gets 4 attempts 10 minutes apart: b4's ntc.party set on the ASUS can break the path until its watchdog
# heals it. If this script cannot reach GitHub at all nothing is pushed, and the digest sees an old timestamp.
set -u
SELF=$(readlink -f "$0")
cd "$(dirname "$SELF")/../.." || exit 1
OUT=dpi-feeds

log() { echo "$(date -u +%FT%TZ) $*"; }
sync_repo() { git fetch -q --depth 1 origin main 2>&1 && git reset -q --hard origin/main 2>&1; }

if [ -z "${PI_FEEDS_SYNCED:-}" ]; then
  for attempt in 1 2 3 4 5; do
    if err=$(sync_repo); then
      PI_FEEDS_SYNCED=1 exec sh "$SELF"   # run the version just pulled
    fi
    log "sync attempt $attempt: $(echo "$err" | head -n 1)"
    [ "$attempt" -lt 5 ] && sleep 300
  done
  log "gave up: cannot sync with GitHub, nothing collected"
  exit 1
fi

T=$(mktemp -d) || exit 1
trap 'rm -rf "$T"' EXIT
SINCE=$(date -u -d '8 days ago' +%Y-%m-%dT%H:%M:%SZ)

collect_ntc() {
  for attempt in 1 2 3 4; do
    stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # taken first, so a post made during collection falls in the next window
    if python3 .github/scripts/ntc_feed.py "$SINCE" > "$T/ntc.jsonl" 2> "$T/ntc.err"; then
      echo "$stamp" > "$T/ntc_collected_at.txt"
      return
    fi
    log "ntc attempt $attempt: $(tail -n 1 "$T/ntc.err")"
    [ "$attempt" -lt 4 ] && sleep 600
  done
  echo "$(date -u +%FT%TZ) $(tail -n 1 "$T/ntc.err")" > "$T/ntc_error.txt"
}

collect_web() {
  for attempt in 1 2 3; do
    stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    if python3 .github/scripts/web_feed.py "$SINCE" > "$T/web.jsonl" 2> "$T/web.err"; then
      echo "$stamp" > "$T/web_collected_at.txt"
      return
    fi
    log "web attempt $attempt: $(tr '\n' ' ' < "$T/web.err")"
    [ "$attempt" -lt 3 ] && sleep 300
  done
  { date -u +%FT%TZ; cat "$T/web.err"; } > "$T/web_error.txt"
  [ -s "$T/web.jsonl" ] && echo "$stamp" > "$T/web_collected_at.txt"   # one source failed: keep what the other gave
}

collect_ntc &
collect_web &
wait

apply_files() {
  if [ -f "$T/ntc_collected_at.txt" ]; then
    cp "$T/ntc.jsonl" "$T/ntc_collected_at.txt" "$OUT/" && rm -f "$OUT/ntc_error.txt"
  else
    cp "$T/ntc_error.txt" "$OUT/"
  fi
  [ -f "$T/web_collected_at.txt" ] && cp "$T/web.jsonl" "$T/web_collected_at.txt" "$OUT/"
  if [ -f "$T/web_error.txt" ]; then cp "$T/web_error.txt" "$OUT/"; else rm -f "$OUT/web_error.txt"; fi
}

summary() {
  echo "ntc=$([ -f "$T/ntc_collected_at.txt" ] && echo "ok,$(wc -l < "$T/ntc.jsonl")" || echo failed)" \
       "web=$([ -f "$T/web_collected_at.txt" ] && echo "ok,$(wc -l < "$T/web.jsonl")" || echo failed)$([ -f "$T/web_error.txt" ] && echo ",partial")"
}

for i in 1 2 3 4 5; do
  if [ "$i" -gt 1 ]; then  # lost a push race or lost the network: start again from the remote, files are in $T
    sleep 60
    sync_repo > /dev/null || { log "push attempt $i: sync failed"; continue; }
  fi
  apply_files
  git add -A "$OUT"
  if git diff --cached --quiet; then log "nothing to push, $(summary)"; exit 0; fi
  if git commit -q -m "pi feeds $(date -u +%F)" && git push -q origin HEAD:main 2>&1; then
    log "pushed, $(summary)"
    exit 0
  fi
  log "push attempt $i failed"
done
log "gave up: collected but could not push, $(summary)"
exit 1
