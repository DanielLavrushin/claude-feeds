#!/usr/bin/env python3
"""Post a Telegram-HTML file to a chat/topic.

Usage: tg_post.py FILE CHAT_ID [THREAD_ID]
Env:   TELEGRAM_BOT_TOKEN (required), HEADER (optional line prepended to the first message)

Splits at blank lines to fit Telegram's 4096-char limit.
If Telegram rejects the HTML, the chunk is resent as plain text so the post is never lost.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
LIMIT = 3900


def api(method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
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
    base = {"chat_id": chat, "link_preview_options": {"is_disabled": True}}
    if thread:
        base["message_thread_id"] = int(thread)
    r = api("sendMessage", {**base, "text": text, "parse_mode": "HTML"})
    if not r.get("ok") and "parse" in r.get("description", "").lower():
        print(f"HTML rejected ({r.get('description')}), resending as plain text")
        r = api("sendMessage", {**base, "text": html.unescape(re.sub(r"<[^>]+>", "", text))})
    if not r.get("ok"):
        sys.exit(f"Telegram error: {r.get('description')}")


def main():
    path, chat = sys.argv[1], sys.argv[2]
    thread = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    text = open(path, encoding="utf-8").read().strip()
    if not text:
        sys.exit(f"{path} is empty")
    header = os.environ.get("HEADER", "").strip()
    parts = chunks(text)
    if header:
        parts[0] = f"{header}\n\n{parts[0]}"
    for part in parts:
        send(chat, thread, part)
    print(f"posted {path} -> {chat} thread {thread} ({len(parts)} message(s))")


if __name__ == "__main__":
    main()
