#!/usr/bin/env python3
"""Update README recent activity with high-signal GitHub events only.

Included activity types:
- Published releases from the user's public events
- Merged pull requests authored by the user, including external repositories
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://api.github.com"
START = "<!--START_SECTION:activity-->"
END = "<!--END_SECTION:activity-->"


def github_get(url: str) -> dict | list:
    if url.startswith("/"):
        url = API + url

    headers = {
        "Accept": "application/vnd.github+json",
        "Accept-Encoding": "identity",
        "User-Agent": "CaoYuhaoCarl-profile-activity",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError:
            raise
        except (
            urllib.error.URLError,
            http.client.RemoteDisconnected,
            http.client.IncompleteRead,
            json.JSONDecodeError,
            TimeoutError,
            OSError,
        ) as error:
            last_error = error
            if attempt == 2:
                break
            time.sleep(2**attempt)

    raise last_error


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().replace("`", "'")


def release_activities(username: str) -> list[dict]:
    events = github_get(f"/users/{username}/events/public?per_page=100")
    activities = []

    for event in events:
        if event.get("type") != "ReleaseEvent":
            continue
        payload = event.get("payload", {})
        if payload.get("action") != "published":
            continue

        release = payload.get("release", {})
        repo = event.get("repo", {}).get("name")
        tag = release.get("tag_name")
        url = release.get("html_url")
        created_at = event.get("created_at")
        if not (repo and tag and url and created_at):
            continue

        activities.append(
            {
                "date": parse_time(created_at),
                "url": url,
                "line": f"🚀 Published release [{tag}]({url}) in [{repo}](https://github.com/{repo})",
            }
        )

    return activities


def merged_pr_activities(username: str) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "q": f"author:{username} is:pr is:merged",
            "sort": "updated",
            "order": "desc",
            "per_page": "30",
        }
    )
    data = github_get(f"/search/issues?{query}")
    activities = []

    for item in data.get("items", []):
        repo_url = item.get("repository_url", "")
        repo = repo_url.split("/repos/", 1)[-1] if "/repos/" in repo_url else ""
        number = item.get("number")
        url = item.get("html_url")
        title = clean_title(item.get("title", ""))
        closed_at = item.get("closed_at")
        if not (repo and number and url and title and closed_at):
            continue

        if repo.startswith(f"{username}/"):
            label = "🎉 Merged PR"
        else:
            label = "🌱 Contributed merged PR"

        activities.append(
            {
                "date": parse_time(closed_at),
                "url": url,
                "line": f"{label} [#{number}]({url}) — `{title}` in [{repo}](https://github.com/{repo})",
            }
        )

    return activities


def update_readme(readme_path: Path, lines: list[str]) -> bool:
    text = readme_path.read_text(encoding="utf-8")
    body = "\n".join(f"{index}. {line}" for index, line in enumerate(lines, start=1))
    replacement = f"{START}\n{body}\n{END}"

    pattern = re.compile(f"{re.escape(START)}.*?{re.escape(END)}", re.DOTALL)
    new_text, count = pattern.subn(replacement, text)
    if count != 1:
        raise SystemExit("Could not find exactly one recent activity section in README.md")

    if new_text == text:
        return False

    readme_path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    username = os.environ.get("GH_USERNAME", "CaoYuhaoCarl")
    max_lines = int(os.environ.get("MAX_LINES", "3"))
    readme_path = Path(os.environ.get("README_PATH", "README.md"))

    activities = release_activities(username) + merged_pr_activities(username)
    unique = {}
    for activity in activities:
        unique.setdefault(activity["url"], activity)

    selected = sorted(unique.values(), key=lambda item: item["date"], reverse=True)[:max_lines]
    if not selected:
        raise SystemExit("No release or merged PR activity found")

    changed = update_readme(readme_path, [item["line"] for item in selected])
    print(f"Updated {readme_path} with {len(selected)} high-signal activities")
    print("changed=" + str(changed).lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
