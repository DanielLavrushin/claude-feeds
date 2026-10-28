#!/usr/bin/env python3
"""Post a Telegram-HTML file to a chat/topic.

Usage: tg_post.py FILE CHAT_ID [THREAD_ID]
       tg_post.py --check FILE      prints links outside the allowlist, exit 1 if any
Env:   TELEGRAM_BOT_TOKEN (required for posting), HEADER (optional plain-text line
       prepended to the first message), SILENT=1 (no notification sound)

Splits at blank lines to fit Telegram's 4096-char limit.
If Telegram rejects the HTML, the chunk is resent as plain text so the post is never lost.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

LIMIT = 3900

# Links allowed in auto-published posts. The digest summarizes public issues/comments that
# anyone can write, so a post must never carry a link the model picked up from them.
ALLOWED_HOSTS = {
    "habr.com", "gfw.report", "ooni.org", "explorer.ooni.org", "censoredplanet.org",
    "usenix.org", "www.usenix.org", "petsymposium.org", "arxiv.org", "byebyedpi.xyz",
}
GITHUB_OWNERS = {  # github.com links only to the tracked projects
    "bol-van", "hufrea", "waujito", "dilluti0n", "gvcoder09", "xvzc", "valdikss", "flowseal",
    "romanvht", "xtls", "sagernet", "apernet", "amnezia-vpn", "net4people", "daniellavrushin",
    "runnin4ik", "william-aqn", "runetfreedom",
}
GITLAB_OWNERS = {"netwalker071778"}  # gitlab.com links only to these namespaces (chimera-project)


def bad_links(text):
    bad = []
    for url in re.findall(r"https?://[^\s\"'<>]+", html.unescape(text)):
        u = urllib.parse.urlsplit(url)
        host = (u.hostname or "").lower()
        owner = u.path.strip("/").split("/")[0].lower()
        if u.scheme != "https":
            bad.append(url)
        elif host == "github.com":
            if owner not in GITHUB_OWNERS:
                bad.append(url)
        elif host == "gitlab.com":
            if owner not in GITLAB_OWNERS:
                bad.append(url)
        elif host not in ALLOWED_HOSTS:
            bad.append(url)
    return bad


def api(method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def chunks(text):
    parts, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) + 2 > LIMIT:
            parts.append(cur)
            cur = ""
        while len(para) > LIMIT:  # single huge paragraph: split at a line end
            cut = para.rfind("\n", 0, LIMIT)
            cut = cut if cut > 0 else LIMIT
            parts.append(para[:cut])
            para = para[cut:].lstrip("\n")
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


def send(chat, thread, text):
    base = {"chat_id": chat, "link_preview_options": {"is_disabled": True},
            "disable_notification": os.environ.get("SILENT") == "1"}
    if thread:
        base["message_thread_id"] = int(thread)
    r = api("sendMessage", {**base, "text": text, "parse_mode": "HTML"})
    if not r.get("ok") and "parse" in r.get("description", "").lower():
        print(f"HTML rejected ({r.get('description')}), resending as plain text")
        r = api("sendMessage", {**base, "text": html.unescape(re.sub(r"<[^>]+>", "", text))})
    if not r.get("ok"):
        sys.exit(f"Telegram error: {r.get('description')}")


def main():
    if sys.argv[1] == "--check":
        bad = bad_links(open(sys.argv[2], encoding="utf-8").read())
        print("\n".join(bad))
        sys.exit(1 if bad else 0)
    path, chat = sys.argv[1], sys.argv[2]
    thread = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    text = open(path, encoding="utf-8").read().strip()
    if not text:
        sys.exit(f"{path} is empty")
    header = os.environ.get("HEADER", "").strip()
    parts = chunks(text)
    if header:
        parts[0] = f"{html.escape(header, quote=False)}\n\n{parts[0]}"
    for part in parts:
        send(chat, thread, part)
    print(f"posted {path} -> {chat} thread {thread} ({len(parts)} message(s))")


if __name__ == "__main__":
    main()
