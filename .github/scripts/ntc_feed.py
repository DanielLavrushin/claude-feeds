#!/usr/bin/env python3
"""Print public posts of the ntc.party forum (Discourse) as JSON lines, oldest first.

Usage: ntc_feed.py SINCE_ISO_UTC     e.g. ntc_feed.py 2026-10-20T00:00:00Z
Walks /posts.json (forum-wide latest posts, 50 per page, allowed by robots.txt) back to SINCE.
type is "topic" for the first post of a topic, "post" for a reply; staff marks forum staff
(bolvan = bol-van, the zapret author). Quotes are shortened to one line, images become [image].
No token needed.
"""
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://ntc.party"
UA = "claude-feeds (+https://github.com/DanielLavrushin/claude-feeds)"
SKIP_CATEGORIES = {"site-feedback"}
MAX_PAGES = 40  # 2000 posts; 8 days is ~5 pages
BODY = 2000

QUOTE = re.compile(r'\[quote(?:="([^",\]]*)[^\]]*)?\]((?:(?!\[quote).)*?)\[/quote\]', re.S | re.I)
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
UPLOAD = re.compile(r"\[([^\]]*)\]\(upload://[^)]*\)")
TOPIC_LINK = re.compile(r"https?://ntc\.party/t/(?:[^/\s)\]]*[^\d/\s)\]][^/\s)\]]*/)?(\d+)(/\d+)?")


def iso(s):
    """Discourse returns milliseconds (2026-10-26T12:41:01.951Z); drop them to match the other feeds."""
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            try:
                wait = float(e.headers.get("Retry-After") or "")
            except ValueError:
                wait = 15 * (attempt + 1)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            wait = 15 * (attempt + 1)
        time.sleep(min(wait, 60))


def clean(p):
    text = p.get("raw") or html.unescape(re.sub(r"<[^>]+>", " ", p.get("cooked") or ""))

    def quote(m):
        said = " ".join(m.group(2).split())
        said = said[:200] + "..." if len(said) > 200 else said
        return f"\n> {m.group(1) or 'quote'}: {said}\n"

    while True:  # innermost quotes first, so nested ones collapse too
        text, n = QUOTE.subn(quote, text)
        if not n:
            break
    text = IMAGE.sub("[image]", text)
    text = UPLOAD.sub(r"[file: \1]", text)
    text = TOPIC_LINK.sub(lambda m: f"{BASE}/t/{m.group(1)}{m.group(2) or ''}", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:BODY]


def main():
    since = sys.argv[1]
    cats = {c["id"]: c for c in get("/site.json")["categories"]}

    posts, before = {}, None
    for _ in range(MAX_PAGES):
        page = get("/posts.json" + (f"?before={before}" if before else ""))["latest_posts"]
        if not page:
            break
        posts.update((p["id"], p) for p in page)
        before = min(p["id"] for p in page)  # exclusive: the next page starts below it
        if min(iso(p["created_at"]) for p in page) < since:
            break
        time.sleep(2)
    else:
        print(f"ntc: stopped at the {MAX_PAGES}-page cap before reaching {since}", file=sys.stderr)

    out = []
    for p in sorted(posts.values(), key=lambda p: p["id"]):
        cat = cats.get(p.get("category_id")) or {}
        created = iso(p["created_at"])
        if (created < since or p.get("post_type") != 1 or p.get("hidden") or p.get("deleted_at")
                or cat.get("slug") in SKIP_CATEGORIES):
            continue
        body = clean(p)
        if not body:
            continue
        out.append({"type": "topic" if p["post_number"] == 1 else "post", "id": p["id"],
                    "topic_id": p["topic_id"], "category": cat.get("name"), "title": p.get("topic_title"),
                    "url": f"{BASE}/t/{p['topic_id']}/{p['post_number']}", "user": p.get("username"),
                    "staff": bool(p.get("staff")), "created": created,
                    "reply_to": p.get("reply_to_post_number"), "body": body})

    for o in out:  # printed only at the end, so a failed request leaves no partial output
        print(json.dumps(o, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # one line for errors.txt instead of a traceback
        sys.exit(f"ntc: {e}")
