from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FEEDS = [
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://www.theverge.com/rss/index.xml",
    "https://hnrss.org/frontpage",
]

DEFAULT_TOPIC = "Technology"
POSTS_DIR = Path("posts")
NEWS_DIR = Path("news")
LATEST_JSON_PATH = NEWS_DIR / "latest.json"
MAX_ITEMS = int(os.getenv("NEWS_MAX_ITEMS", "6"))
TIMEOUT_SECONDS = int(os.getenv("NEWS_TIMEOUT", "20"))


@dataclass
class NewsItem:
    title: str
    link: str
    published: str
    summary: str


def strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text)
    no_spaces = re.sub(r"\s+", " ", no_tags)
    return html.unescape(no_spaces).strip()


def parse_date(raw: str) -> dt.datetime | None:
    if not raw:
        return None

    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def fmt_date(raw: str) -> str:
    parsed = parse_date(raw)
    if parsed is None:
        return "Date not provided"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def read_feed(url: str) -> list[NewsItem]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "codex-demo-news-bot/1.0"},
    )

    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        content = resp.read()

    root = ET.fromstring(content)
    items: list[NewsItem] = []

    # RSS 2.0
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "Untitled").strip()
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        summary = strip_html(item.findtext("description") or "")
        items.append(NewsItem(title=title, link=link, published=published, summary=summary))

    if items:
        return items

    # Atom fallback
    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f"./{atom_ns}entry"):
        title = (entry.findtext(f"{atom_ns}title") or "Untitled").strip()
        summary = strip_html(entry.findtext(f"{atom_ns}summary") or "")
        published = (entry.findtext(f"{atom_ns}updated") or "").strip()

        link = ""
        link_node = entry.find(f"{atom_ns}link")
        if link_node is not None:
            link = (link_node.attrib.get("href") or "").strip()

        items.append(NewsItem(title=title, link=link, published=published, summary=summary))

    return items


def selected_feeds() -> list[str]:
    env_value = os.getenv("NEWS_FEEDS", "").strip()
    if not env_value:
        return DEFAULT_FEEDS

    feeds = [part.strip() for part in env_value.split(",") if part.strip()]
    return feeds or DEFAULT_FEEDS


def dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    output: list[NewsItem] = []

    for item in items:
        key = (item.link or item.title).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)

    return output


def build_post(items: list[NewsItem], topic: str) -> str:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()

    lines = [
        "---",
        "layout: post",
        f'title: "Daily {topic} News Digest - {today}"',
        f"date: {today} 07:00:00 +0000",
        "categories: [news, automation]",
        "---",
        "",
        f"Automated daily digest for **{topic}**.",
        "",
    ]

    for index, item in enumerate(items, start=1):
        title = item.title.replace("|", "-")
        summary = item.summary if item.summary else "No summary available from feed."
        summary = summary[:220].rstrip()

        lines.extend(
            [
                f"## {index}. [{title}]({item.link})",
                f"Published: {fmt_date(item.published)}",
                "",
                summary,
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def build_latest_json(items: list[NewsItem], topic: str) -> str:
    payload = {
        "topic": topic,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": [
            {
                "title": item.title,
                "link": item.link,
                "published_utc": fmt_date(item.published),
                "summary": (item.summary or "No summary available from feed.")[:220].rstrip(),
            }
            for item in items
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def output_path() -> Path:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return POSTS_DIR / f"{today}-daily-news-digest.md"


def main() -> int:
    topic = os.getenv("NEWS_TOPIC", DEFAULT_TOPIC).strip() or DEFAULT_TOPIC
    feeds = selected_feeds()

    collected: list[NewsItem] = []
    errors: list[str] = []

    for feed in feeds:
        try:
            collected.extend(read_feed(feed))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{feed}: {exc}")

    unique_items = dedupe(collected)

    if not unique_items:
        print("No news items collected.")
        for err in errors:
            print(f"- {err}")
        return 1

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    post_items = unique_items[:MAX_ITEMS]
    post_text = build_post(post_items, topic)
    path = output_path()
    path.write_text(post_text, encoding="utf-8")
    LATEST_JSON_PATH.write_text(build_latest_json(post_items, topic), encoding="utf-8")

    print(f"Saved {len(post_items)} items to {path}")
    print(f"Updated {LATEST_JSON_PATH}")
    if errors:
        print("Feeds with errors:")
        for err in errors:
            print(f"- {err}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
