#!/bin/sh
# Runs on Daniel's Raspberry Pi (192.168.1.200) from cron, before the 07:30 digest: ntc.party refuses
# GitHub's runners, so this box collects the forum and pushes dpi-feeds/ntc.jsonl and
# ntc_collected_at.txt. On failure it pushes ntc_error.txt and keeps the last good snapshot.
# Up to 4 attempts 10 minutes apart: b4's ntc.party set on the ASUS can break the path until its
# watchdog heals it.
# crontab: 30 6 * * * cd "$HOME/claude-feeds" && { git fetch -q --depth 1 origin main && git reset -q --hard origin/main && sh .github/scripts/ntc_push.sh; } >> "$HOME/.cache/ntc_push.log" 2>&1
set -u
cd "$(dirname "$0")/../.." || exit 1
OUT=dpi-feeds
T=$(mktemp -d) || exit 1
trap 'rm -rf "$T"' EXIT
SINCE=$(date -u -d '8 days ago' +%Y-%m-%dT%H:%M:%SZ)

ok=""
for attempt in 1 2 3 4; do
  if python3 .github/scripts/ntc_feed.py "$SINCE" > "$T/ntc.jsonl" 2> "$T/err"; then
    date -u +%Y-%m-%dT%H:%M:%SZ > "$T/ntc_collected_at.txt"
    ok=1
    break
  fi
  echo "$(date -u +%FT%TZ) attempt $attempt: $(tail -n 1 "$T/err")"
  [ "$attempt" -lt 4 ] && sleep 600
done
[ -n "$ok" ] || echo "$(date -u +%FT%TZ) $(tail -n 1 "$T/err")" > "$T/ntc_error.txt"

for i in 1 2 3; do
  if [ "$i" -gt 1 ]; then  # lost a push race: start again from the remote, files are in $T
    sleep 20
    git fetch -q --depth 1 origin main && git reset -q --hard origin/main || continue
  fi
  if [ -n "$ok" ]; then
    cp "$T/ntc.jsonl" "$T/ntc_collected_at.txt" "$OUT/" && rm -f "$OUT/ntc_error.txt"
  else
    cp "$T/ntc_error.txt" "$OUT/"
  fi
  git add -A "$OUT"
  git diff --cached --quiet && exit 0
  if git commit -q -m "ntc.party $(date -u +%F)" && git push -q origin HEAD:main; then
    echo "$(date -u +%FT%TZ) pushed, ok=${ok:-0}, $(wc -l < "$OUT/ntc.jsonl") posts"
    exit 0
  fi
done
echo "$(date -u +%FT%TZ) push failed"
exit 1
