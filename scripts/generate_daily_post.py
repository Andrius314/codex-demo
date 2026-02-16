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
from urllib.parse import urlparse

DEFAULT_FEEDS = [
    "https://www.artificialintelligence-news.com/feed/",
    "https://www.marktechpost.com/feed/",
    "https://blog.google/technology/ai/rss/",
]

DEFAULT_TOPIC = "Dirbtinis intelektas ir technologijos"
POSTS_DIR = Path("posts")
NEWS_DIR = Path("news")
LATEST_JSON_PATH = NEWS_DIR / "latest.json"
ARCHIVE_JSON_PATH = NEWS_DIR / "archive.json"
MAX_ITEMS = int(os.getenv("NEWS_MAX_ITEMS", "10"))
TIMEOUT_SECONDS = int(os.getenv("NEWS_TIMEOUT", "20"))
MAX_SUMMARY_CHARS = int(os.getenv("NEWS_SUMMARY_CHARS", "260"))
MAX_ARCHIVE_DIGESTS = int(os.getenv("NEWS_MAX_ARCHIVE_DIGESTS", "120"))


@dataclass
class NewsItem:
    title: str
    link: str
    published_iso: str
    published_lt: str
    summary: str
    source: str
    image_url: str


def strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text)
    no_spaces = re.sub(r"\s+", " ", no_tags)
    return html.unescape(no_spaces).strip()


def clean_mojibake(text: str) -> str:
    # Common malformed UTF-8 sequences observed in some feeds.
    replacements = {
        "ā€": "'",
        "ā€™": "'",
        "ā€œ": '"',
        "ā€�": '"',
        "ā€”": "-",
        "ā€“": "-",
        "Ā£": "£",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def extract_image_from_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    match = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", raw_html, re.IGNORECASE)
    return (match.group(1).strip() if match else "")


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


def format_date_lt(parsed: dt.datetime | None) -> str:
    if parsed is None:
        return "Data nenurodyta"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def normalized_source(feed_url: str, feed_title: str) -> str:
    if feed_title.strip():
        return feed_title.strip()
    domain = urlparse(feed_url).netloc
    return domain.replace("www.", "") if domain else "Saltinis"


def item_from_raw(
    title: str,
    link: str,
    published_raw: str,
    summary_raw_html: str,
    source: str,
    image_url: str,
) -> NewsItem:
    parsed = parse_date(published_raw)
    summary = strip_html(summary_raw_html)
    if not summary:
        summary = "Santrauka nepateikta saltinyje."

    clean_title = clean_mojibake(strip_html(title)) or "Be pavadinimo"
    clean_link = link.strip()
    clean_image_url = image_url.strip()
    clean_summary = clean_mojibake(summary)

    return NewsItem(
        title=clean_title,
        link=clean_link,
        published_iso=parsed.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed else "",
        published_lt=format_date_lt(parsed),
        summary=clean_summary[:MAX_SUMMARY_CHARS].rstrip(),
        source=source,
        image_url=clean_image_url,
    )


def image_from_rss_item(item: ET.Element, summary_html: str) -> str:
    enclosure = item.find("enclosure")
    if enclosure is not None:
        enclosure_type = (enclosure.attrib.get("type") or "").lower()
        enclosure_url = (enclosure.attrib.get("url") or "").strip()
        if enclosure_url and ("image" in enclosure_type or not enclosure_type):
            return enclosure_url

    for node in item.iter():
        tag_name = node.tag.lower()
        if tag_name.endswith("thumbnail") or tag_name.endswith("content"):
            url = (node.attrib.get("url") or "").strip()
            if url and ("image" in (node.attrib.get("type") or "").lower() or tag_name.endswith("thumbnail")):
                return url

    return extract_image_from_html(summary_html)


def image_from_atom_entry(entry: ET.Element, atom_ns: str, summary_html: str) -> str:
    for link_node in entry.findall(f"{atom_ns}link"):
        href = (link_node.attrib.get("href") or "").strip()
        rel = (link_node.attrib.get("rel") or "").lower()
        content_type = (link_node.attrib.get("type") or "").lower()
        if href and ("image" in content_type or rel == "enclosure"):
            return href

    return extract_image_from_html(summary_html)


def read_feed(url: str) -> list[NewsItem]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "codex-demo-ai-news-bot/1.0"},
    )

    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        content = response.read()

    root = ET.fromstring(content)
    items: list[NewsItem] = []

    channel_title = root.findtext("./channel/title") or ""
    source = normalized_source(url, channel_title)

    # RSS 2.0
    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        published_raw = item.findtext("pubDate") or item.findtext("published") or ""
        summary_html = item.findtext("description") or item.findtext("content") or ""
        image_url = image_from_rss_item(item, summary_html)

        items.append(
            item_from_raw(
                title=title,
                link=link,
                published_raw=published_raw,
                summary_raw_html=summary_html,
                source=source,
                image_url=image_url,
            )
        )

    if items:
        return items

    # Atom fallback
    atom_ns = "{http://www.w3.org/2005/Atom}"
    feed_title = root.findtext(f"./{atom_ns}title") or ""
    source = normalized_source(url, feed_title)

    for entry in root.findall(f"./{atom_ns}entry"):
        title = entry.findtext(f"{atom_ns}title") or ""
        published_raw = entry.findtext(f"{atom_ns}updated") or entry.findtext(f"{atom_ns}published") or ""
        summary_html = entry.findtext(f"{atom_ns}summary") or entry.findtext(f"{atom_ns}content") or ""

        link = ""
        for link_node in entry.findall(f"{atom_ns}link"):
            rel = (link_node.attrib.get("rel") or "alternate").lower()
            href = (link_node.attrib.get("href") or "").strip()
            if rel in ("alternate", "") and href:
                link = href
                break

        image_url = image_from_atom_entry(entry, atom_ns, summary_html)

        items.append(
            item_from_raw(
                title=title,
                link=link,
                published_raw=published_raw,
                summary_raw_html=summary_html,
                source=source,
                image_url=image_url,
            )
        )

    return items


def selected_feeds() -> list[str]:
    env_value = os.getenv("NEWS_FEEDS", "").strip()
    if not env_value:
        return DEFAULT_FEEDS

    parts = [part.strip() for part in re.split(r"[,\n]", env_value) if part.strip()]
    return parts or DEFAULT_FEEDS


def dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    output: list[NewsItem] = []

    for item in items:
        key = (item.link or item.title).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)

    output.sort(key=lambda current: current.published_iso, reverse=True)
    return output


def item_to_payload(item: NewsItem) -> dict[str, str]:
    return {
        "title": item.title,
        "link": item.link,
        "published_iso": item.published_iso,
        "published_lt": item.published_lt,
        "summary": item.summary,
        "source": item.source,
        "image_url": item.image_url,
    }


def build_post(items: list[NewsItem], topic: str, digest_date: str, generated_at: str) -> str:
    lines = [
        "---",
        "layout: post",
        f'title: "DI ir technologiju naujienu santrauka - {digest_date}"',
        f"date: {digest_date} 07:00:00 +0000",
        "categories: [ai, technologijos, automatizacija]",
        "---",
        "",
        f"Automatiskai sugeneruota dienos santrauka temai: **{topic}**.",
        f"Generavimo laikas (UTC): {generated_at}",
        "",
    ]

    for index, item in enumerate(items, start=1):
        safe_title = item.title.replace("|", "-")
        safe_summary = item.summary.replace("|", "-")

        lines.extend(
            [
                f"## {index}. [{safe_title}]({item.link})",
                f"Saltinis: {item.source}",
                f"Publikuota: {item.published_lt}",
                "",
                f"Santrauka: {safe_summary}",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def build_latest_payload(
    items: list[NewsItem],
    topic: str,
    digest_date: str,
    generated_at: str,
) -> dict[str, object]:
    return {
        "topic_lt": topic,
        "digest_date": digest_date,
        "generated_at_utc": generated_at,
        "items": [item_to_payload(item) for item in items],
    }


def load_archive(topic: str) -> dict[str, object]:
    if not ARCHIVE_JSON_PATH.exists():
        return {"topic_lt": topic, "updated_at_utc": "", "digests": []}

    try:
        data = json.loads(ARCHIVE_JSON_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"topic_lt": topic, "updated_at_utc": "", "digests": []}

    if not isinstance(data, dict):
        return {"topic_lt": topic, "updated_at_utc": "", "digests": []}

    digests = data.get("digests")
    if not isinstance(digests, list):
        digests = []

    return {
        "topic_lt": str(data.get("topic_lt") or topic),
        "updated_at_utc": str(data.get("updated_at_utc") or ""),
        "digests": digests,
    }


def upsert_archive_digest(
    archive: dict[str, object],
    digest_date: str,
    generated_at: str,
    items: list[NewsItem],
) -> None:
    digest_payload = {
        "digest_date": digest_date,
        "generated_at_utc": generated_at,
        "item_count": len(items),
        "items": [item_to_payload(item) for item in items],
    }

    digests = [
        digest
        for digest in archive.get("digests", [])
        if isinstance(digest, dict) and digest.get("digest_date") != digest_date
    ]

    digests.append(digest_payload)
    digests.sort(key=lambda current: str(current.get("digest_date") or ""), reverse=True)
    archive["digests"] = digests[:MAX_ARCHIVE_DIGESTS]


def output_path(digest_date: str) -> Path:
    return POSTS_DIR / f"{digest_date}-ai-tech-news-digest.md"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    topic = os.getenv("NEWS_TOPIC", DEFAULT_TOPIC).strip() or DEFAULT_TOPIC
    feeds = selected_feeds()

    now_utc = dt.datetime.now(dt.timezone.utc)
    digest_date = now_utc.date().isoformat()
    generated_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    collected: list[NewsItem] = []
    errors: list[str] = []

    for feed in feeds:
        try:
            collected.extend(read_feed(feed))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{feed}: {exc}")

    unique_items = dedupe(collected)
    if not unique_items:
        print("Nepavyko surinkti naujienu.")
        for err in errors:
            print(f"- {err}")
        return 1

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    post_items = unique_items[:MAX_ITEMS]

    post_path = output_path(digest_date)
    post_text = build_post(post_items, topic, digest_date, generated_at)
    post_path.write_text(post_text, encoding="utf-8")

    latest_payload = build_latest_payload(post_items, topic, digest_date, generated_at)
    write_json(LATEST_JSON_PATH, latest_payload)

    archive_payload = load_archive(topic)
    archive_payload["topic_lt"] = topic
    archive_payload["updated_at_utc"] = generated_at
    upsert_archive_digest(archive_payload, digest_date, generated_at, post_items)
    write_json(ARCHIVE_JSON_PATH, archive_payload)

    print(f"Issaugota {len(post_items)} irasu i {post_path}")
    print(f"Atnaujinta {LATEST_JSON_PATH}")
    print(f"Atnaujinta {ARCHIVE_JSON_PATH}")

    if errors:
        print("Dalis saltiniu nepasiekiami:")
        for err in errors:
            print(f"- {err}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
