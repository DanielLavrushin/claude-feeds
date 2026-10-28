#!/usr/bin/env python3
"""Print recent activity of a public GitLab project as JSON lines, in the same shape
as the GitHub items in items.jsonl (type, repo, url, title, user, created, updated, body).

Usage: gitlab_feed.py GROUP/PROJECT SINCE_ISO_UTC     e.g. netwalker071778/chimera-project 2026-10-20T00:00:00Z
Covers commits on all branches, tags and releases. No token needed for public projects.
"""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request


def iso(s):
    """GitLab returns local offsets (+03:00); normalize to UTC 'Z' so string comparison works."""
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    project, since = sys.argv[1], sys.argv[2]
    pid = urllib.parse.quote(project, safe="")
    repo = f"gitlab:{project}"

    def get(path):
        with urllib.request.urlopen(f"https://gitlab.com/api/v4/projects/{pid}{path}", timeout=30) as r:
            return json.load(r)

    out = []
    for c in get(f"/repository/commits?all=true&since={urllib.parse.quote(since)}&per_page=100"):
        t = iso(c.get("committed_date"))
        out.append({"type": "commit", "repo": repo, "url": c.get("web_url"), "title": c.get("title"),
                    "user": c.get("author_name"), "created": t, "updated": t,
                    "body": (c.get("message") or "")[:1000]})

    for tag in get("/repository/tags?per_page=20&order_by=updated"):
        commit = tag.get("commit") or {}
        t = iso(commit.get("committed_date") or commit.get("created_at"))
        if t and t >= since:
            out.append({"type": "tag", "repo": repo, "url": f"https://gitlab.com/{project}/-/tags/{urllib.parse.quote(tag['name'])}",
                        "title": tag["name"], "user": None, "created": t, "updated": t,
                        "body": (tag.get("message") or "")[:1000]})

    for rel in get("/releases?per_page=10"):
        t = iso(rel.get("released_at") or rel.get("created_at"))
        if t and t >= since:
            out.append({"type": "release", "repo": repo,
                        "url": (rel.get("_links") or {}).get("self") or f"https://gitlab.com/{project}/-/releases",
                        "title": rel.get("name") or rel.get("tag_name"), "user": (rel.get("author") or {}).get("username"),
                        "created": t, "updated": t, "body": (rel.get("description") or "")[:1500]})

    for o in out:  # printed only at the end, so a failed request leaves no partial output
        print(json.dumps(o, ensure_ascii=False))


if __name__ == "__main__":
    main()
