#!/usr/bin/env python3
"""Print recent Habr and gfw.report articles as JSON lines, newest first.

Usage: web_feed.py SINCE_ISO_UTC     e.g. web_feed.py 2026-10-20T00:00:00Z
Each line: source, feed, created, title, url, tags, full_text, body. For Habr articles of the last 3 days body is the
start of the article (full_text true), otherwise the lead from the feed. Exits 1 and names the source on stderr when
all of a source's feeds failed; what the other source gave is still printed.
"""
import datetime as dt
import email.utils
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (X11; Linux x86_64)"
HABR = "https://habr.com/ru/rss/search/?q={}&order_by=date&target_type=posts&hl=ru&fl=ru"
FEEDS = [("habr", q, HABR.format(urllib.parse.quote(q))) for q in ("DPI", "ТСПУ", "zapret", "byedpi", "[тспу]", "[Роскомнадзор]")]
FEEDS.append(("gfw.report", "gfw.report", "https://gfw.report/index.xml"))
MAX_ARTICLES = 10
LEAD = 1500
ARTICLE = 6000


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def text(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).split())


def article_text(url):
    t = get(url).decode("utf-8", "replace")
    t = t[t.find("article-formatted-body"):]
    t = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", t)
    return text(t)[:ARTICLE]


def main():
    since = sys.argv[1]
    items, ok, failed = {}, set(), set()
    for source, feed, url in FEEDS:  # one at a time: Habr rate-limits parallel requests
        try:
            root = ET.fromstring(get(url))
            if root.tag != "rss":
                raise ValueError("not RSS")
            ok.add(source)
        except Exception as e:
            print(f"{source} feed {feed}: {e}", file=sys.stderr)
            failed.add(source)
            continue
        finally:
            time.sleep(3)
        for it in root.iter("item"):
            link = (it.findtext("link") or "").split("?")[0]
            try:
                d = email.utils.parsedate_to_datetime(it.findtext("pubDate")).astimezone(dt.timezone.utc)
            except Exception:
                continue
            created = d.strftime("%Y-%m-%dT%H:%M:%SZ")
            if created < since or link in items:
                continue
            items[link] = {"source": source, "feed": feed, "created": created, "title": it.findtext("title"), "url": link,
                           "tags": [c.text for c in it.findall("category") if c.text], "full_text": False,
                           "body": text(it.findtext("description"))[:LEAD]}

    rows = sorted(items.values(), key=lambda o: o["created"], reverse=True)
    recent = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for o in [o for o in rows if o["source"] == "habr" and o["created"] >= recent][:MAX_ARTICLES]:
        try:
            body = article_text(o["url"])
            if body:
                o["body"], o["full_text"] = body, True
        except Exception as e:
            print(f"habr article {o['url']}: {e}", file=sys.stderr)  # the lead stays; not a source failure
        time.sleep(3)

    for o in rows:
        print(json.dumps(o, ensure_ascii=False))
    down = failed - ok
    for source in sorted(down):
        print(f"{source} failed", file=sys.stderr)
    sys.exit(1 if down else 0)


if __name__ == "__main__":
    main()
