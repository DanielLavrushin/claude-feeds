#!/bin/sh
# Run by the digest at its start, from the repo root: feed_window.sh ntc web
# Works out where each Pi feed's reading window starts, so a morning without a snapshot is caught up the next day
# instead of falling outside a fixed 26 hours. Writes /tmp/<name>_since and moves the watermark dpi-feeds/<name>_seen.txt
# ("<window start> <snapshot read>"), which the digest commits together with dpi-feeds/refresh.
# Always exits 0: it runs inside the digest's refresh command, which must not fail because of a bad file here.
set -u
OUT=dpi-feeds
DIR=${FEED_WINDOW_DIR:-/tmp}
NOW=$(date -u +%s)
for N in "$@"; do
  collected=$(cat "$OUT/${N}_collected_at.txt" 2>/dev/null)
  seen=$(cat "$OUT/${N}_seen.txt" 2>/dev/null)
  start=${seen%% *}
  last=${seen##* }
  if [ -z "$collected" ] || [ -z "$seen" ]; then       # first run
    start=$(date -u -d '26 hours ago' +%Y-%m-%dT%H:%M:%SZ)
    [ -n "$collected" ] && echo "$start $collected" > "$OUT/${N}_seen.txt"
  elif [ "$collected" != "$last" ]; then               # a snapshot no digest has read yet
    start=$last
    echo "$last $collected" > "$OUT/${N}_seen.txt"
  elif [ $(( NOW - $(date -u -d "$collected" +%s 2>/dev/null || echo 0) )) -ge 43200 ]; then   # no new snapshot today: nothing new to read
    start=$last
  fi                                                   # else a rerun of today's digest: same window again
  case "$start" in
    20[0-9][0-9]-*T*Z) ;;
    *) start=$(date -u -d '26 hours ago' +%Y-%m-%dT%H:%M:%SZ) ;;   # a damaged file must not empty the window
  esac
  echo "$start" > "$DIR/${N}_since"
  echo "$N window starts $start (snapshot ${collected:-none})"
done
exit 0
