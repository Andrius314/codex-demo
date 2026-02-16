from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

DEFAULT_RSS_FEEDS = [
    "https://www.artificialintelligence-news.com/feed/",
    "https://www.marktechpost.com/feed/",
    "https://blog.google/technology/ai/rss/",
]

# Add your channel IDs or URLs via NEWS_YOUTUBE_CHANNELS env.
# Examples: UCxxxx..., https://www.youtube.com/channel/UCxxxx..., https://www.youtube.com/@handle
DEFAULT_YOUTUBE_CHANNELS: list[str] = [
    "UCIgnGlGkVRhd4qNFcEwLL4A",  # theAIsearch
    "UCbfYPyITQ-7l4upoX8nvctg",  # Two Minute Papers
    "UCZHmQk67mSJgfCCTn7xBfew",  # OpenAI
    "UCXZCJLdBC09xxGZ6gcdrc6A",  # Google DeepMind
]

KNOWN_YOUTUBE_HANDLES = {
    "@theaisearch": "UCIgnGlGkVRhd4qNFcEwLL4A",
    "@twominutepapers": "UCbfYPyITQ-7l4upoX8nvctg",
    "@openai": "UCZHmQk67mSJgfCCTn7xBfew",
    "@googledeepmind": "UCXZCJLdBC09xxGZ6gcdrc6A",
}

UNKNOWN_LT = "Neaptikta siame saltinyje."

DEFAULT_TOPIC = "Dirbtinis intelektas ir technologijos"
POSTS_DIR = Path("posts")
NEWS_DIR = Path("news")
LATEST_JSON_PATH = NEWS_DIR / "latest.json"
ARCHIVE_JSON_PATH = NEWS_DIR / "archive.json"
GENERATED_IMAGES_DIR = NEWS_DIR / "generated-images"

MAX_ITEMS = int(os.getenv("NEWS_MAX_ITEMS", "12"))
TIMEOUT_SECONDS = int(os.getenv("NEWS_TIMEOUT", "20"))
MAX_SUMMARY_CHARS = int(os.getenv("NEWS_SUMMARY_CHARS", "320"))
MAX_ARCHIVE_DIGESTS = int(os.getenv("NEWS_MAX_ARCHIVE_DIGESTS", "120"))
MAX_YT_PER_CHANNEL = int(os.getenv("NEWS_MAX_YOUTUBE_PER_CHANNEL", "2"))
MIN_VIDEO_ITEMS = int(os.getenv("NEWS_MIN_VIDEO_ITEMS", "2"))
MAX_TRANSCRIPT_CHARS = int(os.getenv("NEWS_MAX_TRANSCRIPT_CHARS", "2400"))
MAX_ARTICLE_FETCH_BYTES = int(os.getenv("NEWS_MAX_ARTICLE_FETCH_BYTES", "320000"))
MAX_ARTICLE_CONTEXT_CHARS = int(os.getenv("NEWS_MAX_ARTICLE_CONTEXT_CHARS", "7000"))
TRANSLATE_TO_LT = os.getenv("NEWS_TRANSLATE_LT", "true").strip().lower() != "false"
IMAGE_MODE = os.getenv("NEWS_IMAGE_MODE", "generated").strip().lower()  # generated|source|hybrid

TRANSLATION_CACHE: dict[str, str] = {}


@dataclass
class NewsItem:
    title: str
    link: str
    published_iso: str
    published_lt: str
    summary_lt: str
    source: str
    source_image_url: str
    image_url: str
    kind: str  # article|video
    video_id: str
    bullets_lt: list[str] = field(default_factory=list)
    practical: dict[str, str] = field(default_factory=dict)


def strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text or "")
    no_spaces = re.sub(r"\s+", " ", no_tags)
    return html.unescape(no_spaces).strip()


def clean_mojibake(text: str) -> str:
    replacements = {
        "ā€": "'",
        "ā€™": "'",
        "ā€œ": '"',
        "ā€�": '"',
        "ā€”": "-",
        "ā€“": "-",
        "Ā£": "£",
        "Â£": "£",
        "Â": "",
    }
    cleaned = text
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned


def normalize_text(text: str) -> str:
    return clean_mojibake(strip_html(text))


def ensure_sentence(text: str) -> str:
    value = normalize_text(text)
    if not value:
        return ""
    if value[-1] not in ".!?":
        return value + "."
    return value


def split_sentences(text: str) -> list[str]:
    cleaned = normalize_text(text)
    if not cleaned:
        return []
    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]


def contains_any(text_lower: str, keywords: list[str]) -> bool:
    return any(keyword in text_lower for keyword in keywords)


def shorten_text(value: str, max_len: int = 220) -> str:
    clean = normalize_text(value)
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def chunk_text(text: str, max_chunk_len: int = 1200) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 > max_chunk_len and current:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1

    if current:
        chunks.append(" ".join(current))
    return chunks


def translate_chunk_google_free(text: str, target_lang: str = "lt") -> str:
    if not text:
        return ""

    cache_key = f"{target_lang}:{text}"
    if cache_key in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[cache_key]

    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_lang,
        "dt": "t",
        "q": text,
    }
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "codex-ai-news-bot/1.0"})

    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))

    translated = ""
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, list):
            translated = "".join(part[0] for part in first if isinstance(part, list) and part and isinstance(part[0], str))

    translated = normalize_text(translated)
    if not translated:
        translated = text

    TRANSLATION_CACHE[cache_key] = translated
    return translated


def translate_text_to_lt(text: str) -> str:
    cleaned = normalize_text(text)
    if not cleaned:
        return ""

    if not TRANSLATE_TO_LT:
        return cleaned

    try:
        chunks = chunk_text(cleaned, max_chunk_len=1000)
        translated_chunks = [translate_chunk_google_free(chunk, target_lang="lt") for chunk in chunks]
        result = normalize_text(" ".join(translated_chunks))
        return result if result else cleaned
    except Exception:
        return cleaned


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
        return normalize_text(feed_title)
    domain = urlparse(feed_url).netloc
    return domain.replace("www.", "") if domain else "Saltinis"


def extract_image_from_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    match = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", raw_html, re.IGNORECASE)
    return (match.group(1).strip() if match else "")


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
            node_type = (node.attrib.get("type") or "").lower()
            if url and ("image" in node_type or tag_name.endswith("thumbnail")):
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


def summarize_text(text: str, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    cleaned = normalize_text(text)
    if not cleaned:
        return "Santrauka nepateikta saltinyje."

    sentences = split_sentences(cleaned)
    if not sentences:
        return cleaned[:max_chars].rstrip()

    picked: list[str] = []
    size = 0
    for sentence in sentences:
        if len(sentence) < 25:
            continue
        if size + len(sentence) + 1 > max_chars:
            break
        picked.append(sentence)
        size += len(sentence) + 1
        if len(picked) >= 3:
            break

    if not picked:
        return cleaned[:max_chars].rstrip()
    return " ".join(picked).strip()


def slugify(text: str) -> str:
    lowered = normalize_text(text).lower()
    ascii_like = (
        lowered.replace("ą", "a")
        .replace("č", "c")
        .replace("ę", "e")
        .replace("ė", "e")
        .replace("į", "i")
        .replace("š", "s")
        .replace("ų", "u")
        .replace("ū", "u")
        .replace("ž", "z")
    )
    safe = re.sub(r"[^a-z0-9]+", "-", ascii_like).strip("-")
    return safe[:56] if safe else "naujiena"


def wrap_for_svg(text: str, line_len: int = 28, max_lines: int = 4) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 > line_len and current:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
            if len(lines) >= max_lines:
                break
        else:
            current.append(word)
            current_len += len(word) + 1

    if current and len(lines) < max_lines:
        lines.append(" ".join(current))

    if not lines:
        lines = ["DI naujienos"]

    if len(lines) == max_lines and len(words) > 0:
        lines[-1] = (lines[-1][: max(0, line_len - 3)] + "...") if len(lines[-1]) >= line_len else lines[-1]

    return lines


def generated_colors(seed_text: str) -> tuple[str, str]:
    digest = hashlib.sha256(seed_text.encode("utf-8", errors="ignore")).hexdigest()
    hue = int(digest[:2], 16)
    hue2 = (hue + 38) % 255
    c1 = f"#{hue:02x}7abf"
    c2 = f"#{hue2:02x}4f8f"
    return c1, c2


def generate_svg_image(item: NewsItem, digest_date: str, index: int) -> str:
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    safe_slug = slugify(item.title)
    filename = f"{digest_date}-{index:02d}-{safe_slug}.svg"
    path = GENERATED_IMAGES_DIR / filename

    c1, c2 = generated_colors(item.title + item.source)
    lines = wrap_for_svg(item.title, line_len=30, max_lines=4)

    title_svg = ""
    for idx, line in enumerate(lines):
        y = 84 + idx * 34
        title_svg += f'<text x="36" y="{y}" font-family="Manrope, Arial, sans-serif" font-size="28" font-weight="700" fill="#ffffff">{html.escape(line)}</text>'

    source_text = html.escape(item.source)
    date_text = html.escape(item.published_lt)
    kind_text = "YouTube" if item.kind == "video" else "RSS"

    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720' viewBox='0 0 1280 720'>"
        "<defs>"
        f"<linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'><stop offset='0%' stop-color='{c1}'/><stop offset='100%' stop-color='{c2}'/></linearGradient>"
        "</defs>"
        "<rect width='1280' height='720' fill='url(#bg)'/>"
        "<circle cx='1140' cy='-30' r='260' fill='rgba(255,255,255,0.16)'/>"
        "<circle cx='-40' cy='740' r='280' fill='rgba(255,255,255,0.14)'/>"
        "<rect x='28' y='28' width='1224' height='664' rx='28' fill='rgba(0,0,0,0.12)' stroke='rgba(255,255,255,0.22)'/>"
        "<text x='36' y='54' font-family='Manrope, Arial, sans-serif' font-size='20' font-weight='700' fill='rgba(255,255,255,0.95)'>DI naujienu santrauka</text>"
        f"{title_svg}"
        f"<text x='36' y='640' font-family='Manrope, Arial, sans-serif' font-size='20' fill='rgba(255,255,255,0.95)'>Saltinis: {source_text}</text>"
        f"<text x='36' y='672' font-family='Manrope, Arial, sans-serif' font-size='18' fill='rgba(255,255,255,0.9)'>Data: {date_text}</text>"
        f"<text x='1130' y='672' text-anchor='end' font-family='Manrope, Arial, sans-serif' font-size='18' font-weight='700' fill='rgba(255,255,255,0.9)'>{kind_text}</text>"
        "</svg>"
    )

    path.write_text(svg, encoding="utf-8")
    return f"generated-images/{filename}"


def cleanup_digest_images(digest_date: str) -> None:
    if not GENERATED_IMAGES_DIR.exists():
        return
    prefix = f"{digest_date}-"
    for path in GENERATED_IMAGES_DIR.glob(f"{prefix}*.svg"):
        try:
            path.unlink()
        except OSError:
            pass


def choose_image(source_image_url: str, generated_image_url: str) -> str:
    mode = IMAGE_MODE if IMAGE_MODE in {"generated", "source", "hybrid"} else "generated"
    if mode == "source":
        return source_image_url or generated_image_url
    if mode == "hybrid":
        return source_image_url or generated_image_url
    return generated_image_url


def item_from_raw(
    title: str,
    link: str,
    published_raw: str,
    summary_raw_html: str,
    source: str,
    source_image_url: str,
    kind: str = "article",
    video_id: str = "",
) -> NewsItem:
    parsed = parse_date(published_raw)
    summary_en = summarize_text(summary_raw_html, max_chars=MAX_SUMMARY_CHARS)

    title_clean = normalize_text(title) or "Be pavadinimo"
    summary_lt = translate_text_to_lt(summary_en)
    title_lt = translate_text_to_lt(title_clean)

    return NewsItem(
        title=title_lt,
        link=link.strip(),
        published_iso=parsed.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed else "",
        published_lt=format_date_lt(parsed),
        summary_lt=summary_lt,
        source=source,
        source_image_url=source_image_url.strip(),
        image_url="",
        kind=kind,
        video_id=video_id,
    )


def read_rss_feed(url: str) -> list[NewsItem]:
    req = urllib.request.Request(url, headers={"User-Agent": "codex-ai-news-bot/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        content = response.read()

    root = ET.fromstring(content)
    items: list[NewsItem] = []

    channel_title = root.findtext("./channel/title") or ""
    source = normalized_source(url, channel_title)

    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        published_raw = item.findtext("pubDate") or item.findtext("published") or ""
        summary_html = item.findtext("description") or item.findtext("content") or ""
        source_image_url = image_from_rss_item(item, summary_html)

        items.append(
            item_from_raw(
                title=title,
                link=link,
                published_raw=published_raw,
                summary_raw_html=summary_html,
                source=source,
                source_image_url=source_image_url,
                kind="article",
            )
        )

    if items:
        return items

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

        source_image_url = image_from_atom_entry(entry, atom_ns, summary_html)

        items.append(
            item_from_raw(
                title=title,
                link=link,
                published_raw=published_raw,
                summary_raw_html=summary_html,
                source=source,
                source_image_url=source_image_url,
                kind="article",
            )
        )

    return items


def parse_youtube_video_id(url: str) -> str:
    if not url:
        return ""

    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.endswith("youtu.be"):
            return parsed.path.strip("/")

        query = urllib.parse.parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]

        m = re.search(r"/shorts/([A-Za-z0-9_-]{6,})", parsed.path)
        if m:
            return m.group(1)
    except Exception:
        return ""

    return ""


def extract_channel_id_from_url(channel_url: str) -> str:
    m = re.search(r"/channel/(UC[\w-]{20,30})", channel_url)
    if m:
        return m.group(1)

    handle_match = re.search(r"/@([A-Za-z0-9_.-]+)", channel_url)
    if handle_match:
        handle = f"@{handle_match.group(1).lower()}"
        if handle in KNOWN_YOUTUBE_HANDLES:
            return KNOWN_YOUTUBE_HANDLES[handle]

    # Try resolving @handle or custom path by loading channel HTML.
    try:
        req = urllib.request.Request(channel_url, headers={"User-Agent": "codex-ai-news-bot/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            html_text = response.read().decode("utf-8", errors="ignore")
        m2 = re.search(r'"channelId":"(UC[\w-]{20,30})"', html_text)
        if m2:
            return m2.group(1)
        m3 = re.search(r'"externalId":"(UC[\w-]{20,30})"', html_text)
        if m3:
            return m3.group(1)
    except Exception:
        return ""

    return ""


def youtube_feed_from_channel_token(token: str) -> str:
    clean = token.strip()
    if not clean:
        return ""

    if clean.startswith("https://www.youtube.com/feeds/videos.xml"):
        return clean

    if re.fullmatch(r"UC[\w-]{20,30}", clean):
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={clean}"

    if clean.startswith("@"):
        mapped = KNOWN_YOUTUBE_HANDLES.get(clean.lower(), "")
        if mapped:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={mapped}"

    if clean.startswith("http") and "youtube.com" in clean:
        cid = extract_channel_id_from_url(clean)
        if cid:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

    return ""


def load_youtube_channels() -> list[str]:
    env_value = os.getenv("NEWS_YOUTUBE_CHANNELS", "").strip()
    raw_tokens = [part.strip() for part in re.split(r"[,\n]", env_value) if part.strip()] if env_value else DEFAULT_YOUTUBE_CHANNELS

    feed_urls: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        feed_url = youtube_feed_from_channel_token(token)
        if feed_url and feed_url not in seen:
            seen.add(feed_url)
            feed_urls.append(feed_url)
    return feed_urls


def load_youtube_transcript(video_id: str) -> str:
    if not video_id:
        return ""

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return ""

    transcript_items: list[Any] = []

    # youtube-transcript-api >= 1.0 uses instance.fetch(...),
    # older releases exposed classmethod get_transcript(...).
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["lt", "en"])
        if hasattr(fetched, "to_raw_data"):
            transcript_items = list(fetched.to_raw_data())
        else:
            transcript_items = list(fetched)
    except Exception:
        transcript_items = []

    if not transcript_items and hasattr(YouTubeTranscriptApi, "get_transcript"):
        try:
            transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=["lt", "en"])
        except Exception:
            try:
                transcript_items = YouTubeTranscriptApi.get_transcript(video_id)
            except Exception:
                transcript_items = []

    if not transcript_items:
        return ""

    text_parts = []
    for item in transcript_items:
        text = ""
        if isinstance(item, dict):
            text = normalize_text(str(item.get("text") or ""))
        else:
            text = normalize_text(str(getattr(item, "text", "") or ""))
        if not text:
            continue
        if text.startswith("[") and text.endswith("]"):
            continue
        text_parts.append(text)

    merged = " ".join(text_parts)
    return merged[:MAX_TRANSCRIPT_CHARS].strip()


def summarize_transcript_to_lt(transcript_text: str) -> str:
    if not transcript_text:
        return ""

    base = summarize_text(transcript_text, max_chars=max(320, MAX_SUMMARY_CHARS + 100))
    return translate_text_to_lt(base)


def read_youtube_feed(feed_url: str) -> list[NewsItem]:
    req = urllib.request.Request(feed_url, headers={"User-Agent": "codex-ai-news-bot/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        content = response.read()

    root = ET.fromstring(content)
    atom_ns = "{http://www.w3.org/2005/Atom}"
    media_ns = "{http://search.yahoo.com/mrss/}"

    channel_title = root.findtext(f"./{atom_ns}title") or "YouTube"
    source = normalize_text(channel_title)

    items: list[NewsItem] = []
    for entry in root.findall(f"./{atom_ns}entry")[:MAX_YT_PER_CHANNEL]:
        title = entry.findtext(f"{atom_ns}title") or ""
        published_raw = entry.findtext(f"{atom_ns}published") or entry.findtext(f"{atom_ns}updated") or ""

        link = ""
        for link_node in entry.findall(f"{atom_ns}link"):
            rel = (link_node.attrib.get("rel") or "alternate").lower()
            href = (link_node.attrib.get("href") or "").strip()
            if rel in ("alternate", "") and href:
                link = href
                break

        video_id = parse_youtube_video_id(link)
        description = ""
        group = entry.find(f"{media_ns}group")
        if group is not None:
            description = group.findtext(f"{media_ns}description") or ""
        if not description:
            description = entry.findtext(f"{atom_ns}summary") or ""

        thumbnail = ""
        if group is not None:
            thumb = group.find(f"{media_ns}thumbnail")
            if thumb is not None:
                thumbnail = (thumb.attrib.get("url") or "").strip()

        transcript_text = load_youtube_transcript(video_id)
        transcript_summary_lt = summarize_transcript_to_lt(transcript_text)
        if transcript_summary_lt:
            summary = transcript_summary_lt
        else:
            summary = translate_text_to_lt(summarize_text(description, max_chars=MAX_SUMMARY_CHARS))

        item = item_from_raw(
            title=title,
            link=link,
            published_raw=published_raw,
            summary_raw_html=summary,
            source=source,
            source_image_url=thumbnail,
            kind="video",
            video_id=video_id,
        )
        item.summary_lt = summary
        items.append(item)

    return items


def selected_rss_feeds() -> list[str]:
    env_value = os.getenv("NEWS_FEEDS", "").strip()
    if not env_value:
        return DEFAULT_RSS_FEEDS

    parts = [part.strip() for part in re.split(r"[,\n]", env_value) if part.strip()]
    return parts or DEFAULT_RSS_FEEDS


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


def choose_digest_items(items: list[NewsItem], max_items: int, min_videos: int) -> list[NewsItem]:
    if max_items <= 0:
        return []

    selected = items[:max_items]
    if min_videos <= 0:
        return selected

    current_video_count = sum(1 for item in selected if item.kind == "video")
    if current_video_count >= min_videos:
        return selected

    existing_keys = {(item.link or item.title).strip().lower() for item in selected}
    extra_videos = [
        item
        for item in items[max_items:]
        if item.kind == "video" and (item.link or item.title).strip().lower() not in existing_keys
    ]

    for video in extra_videos:
        replace_index = None
        for idx in range(len(selected) - 1, -1, -1):
            if selected[idx].kind != "video":
                replace_index = idx
                break

        if replace_index is None:
            break

        selected[replace_index] = video
        current_video_count += 1
        if current_video_count >= min_videos:
            break

    selected.sort(key=lambda current: current.published_iso, reverse=True)
    return selected


def extract_links_from_html(raw_html: str, base_url: str) -> list[str]:
    links = re.findall(r"href=[\"']([^\"']+)[\"']", raw_html, flags=re.IGNORECASE)
    out: list[str] = []
    seen: set[str] = set()

    for link in links:
        absolute = urljoin(base_url, link)
        if not absolute.startswith("http"):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
        if len(out) >= 40:
            break

    return out


def fetch_article_context(url: str) -> tuple[str, list[str]]:
    if not url.startswith("http"):
        return "", []

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; codex-ai-news-bot/1.0)",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_ARTICLE_FETCH_BYTES)

        decoded = raw.decode("utf-8", errors="ignore")
        cleaned = re.sub(r"<script[^>]*>.*?</script>", " ", decoded, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<style[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)

        links = extract_links_from_html(cleaned, base_url=url)

        meta_desc = ""
        meta_match = re.search(
            r'<meta[^>]+(?:name=["\']description["\']|property=["\']og:description["\'])[^>]+content=["\']([^"\']+)["\']',
            cleaned,
            flags=re.IGNORECASE,
        )
        if meta_match:
            meta_desc = normalize_text(meta_match.group(1))

        paragraph_matches = re.findall(r"<p[^>]*>(.*?)</p>", cleaned, flags=re.IGNORECASE | re.DOTALL)
        paragraphs = [normalize_text(match) for match in paragraph_matches]
        noise_keywords = ["twitter", "linkedin", "reddit", "privacy", "cookie", "menu", "subscribe", "advertise", "naujienu centras"]
        paragraphs = [
            p
            for p in paragraphs
            if len(p) > 40 and len(p.split()) >= 8 and not contains_any(p.lower(), noise_keywords)
        ][:6]

        combined = []
        if meta_desc:
            combined.append(meta_desc)
        combined.extend(paragraphs)
        if not combined:
            combined.append(normalize_text(cleaned))

        text = " ".join(combined)
        return text[:MAX_ARTICLE_CONTEXT_CHARS], links
    except Exception:
        return "", []


def extract_price_values(text: str) -> list[str]:
    pattern = re.compile(
        r"(?:USD|EUR|GBP|\$|€|£)\s?\d+(?:[\.,]\d{1,2})?(?:\s*(?:/|per)?\s*(?:month|mo|year|yr|user|seat|m\.)?)?",
        re.IGNORECASE,
    )
    found: list[str] = []
    seen: set[str] = set()

    for match in pattern.finditer(text):
        token = normalize_text(match.group(0))
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(token)
        if len(found) >= 4:
            break

    return found


def find_sentence_with_keywords(text: str, keywords: list[str]) -> str:
    for sentence in split_sentences(text):
        if contains_any(sentence.lower(), keywords):
            return sentence
    return ""


def detect_pricing(text: str) -> tuple[str, str]:
    low = text.lower()
    free_keywords = ["free", "open source", "open-source", "nemokam", "no cost"]
    paid_keywords = ["paid", "subscription", "pricing", "plan", "mokam", "license", "pro plan", "enterprise"]

    free_hit = contains_any(low, free_keywords)
    paid_hit = contains_any(low, paid_keywords)
    prices = extract_price_values(text)

    if free_hit and (paid_hit or prices):
        headline = "Yra nemokamas ir mokamas variantas."
    elif free_hit:
        headline = "Paminetas nemokamas arba atviro kodo variantas."
    elif paid_hit or prices:
        headline = "Labiau panasu i mokama sprendima."
    else:
        headline = UNKNOWN_LT

    details = ", ".join(prices) if prices else ""
    return headline, (shorten_text(details) if details else UNKNOWN_LT)


def detect_run_mode(text: str) -> str:
    low = text.lower()
    online_keys = ["web", "browser", "cloud", "hosted", "api", "online", "saas", "playground"]
    local_keys = ["local", "on-device", "on device", "offline", "download", "self-hosted", "self hosted", "gpu", "vram"]

    has_online = contains_any(low, online_keys)
    has_local = contains_any(low, local_keys)

    if has_online and has_local:
        return "Veikia tiek online, tiek lokaliai."
    if has_online:
        return "Panasu, kad veikia online (naršyklė/API)."
    if has_local:
        return "Panasu, kad skirta lokaliam paleidimui."
    return UNKNOWN_LT


def detect_online_limits(text: str) -> str:
    keywords = [
        "rate limit",
        "quota",
        "limit",
        "per day",
        "per hour",
        "requests",
        "messages",
        "tokens",
        "waitlist",
        "beta access",
        "preview",
    ]
    sentence = find_sentence_with_keywords(text, keywords)
    if not sentence:
        return UNKNOWN_LT
    return shorten_text(translate_text_to_lt(sentence))


def detect_local_requirements(text: str) -> str:
    pattern = re.compile(
        r"(?:\d+\s?(?:GB|GiB)\s?(?:VRAM|RAM)|RTX\s?\d{3,4}|NVIDIA\s+GPU|CUDA)",
        re.IGNORECASE,
    )
    matches = pattern.findall(text)

    if not matches:
        return UNKNOWN_LT

    values: list[str] = []
    seen: set[str] = set()
    for match in matches:
        key = match.lower()
        if key in seen:
            continue
        seen.add(key)
        values.append(normalize_text(match))
        if len(values) >= 6:
            break

    return shorten_text("Aptikta: " + ", ".join(values))


def detect_availability(text: str) -> str:
    low = text.lower()
    if contains_any(low, ["coming soon", "soon", "upcoming"]):
        return "Dar neissleista arba arteja."
    if contains_any(low, ["waitlist", "invite", "request access"]):
        return "Reikia prieigos (waitlist/invite)."
    if contains_any(low, ["beta", "preview", "alpha"]):
        return "Prieinama kaip beta/preview."
    if contains_any(low, ["available now", "launched", "released", "generally available", "now available"]):
        return "Panasu, kad jau galima bandyti."
    return UNKNOWN_LT


def choose_try_url(links: list[str], fallback: str) -> str:
    priorities = ["try", "demo", "playground", "signup", "start", "download", "app", "studio", "github", "huggingface", "docs"]
    for key in priorities:
        for link in links:
            if key in link.lower():
                return link
    return fallback if fallback else (links[0] if links else "")


def build_practical_info(item: NewsItem, context_text: str, links: list[str]) -> dict[str, str]:
    pricing_headline, pricing_details = detect_pricing(context_text)
    run_mode = detect_run_mode(context_text)
    online_limits = detect_online_limits(context_text)
    local_requirements = detect_local_requirements(context_text)
    availability = detect_availability(context_text)
    try_url = choose_try_url(links, item.link)

    return {
        "kaina": pricing_headline,
        "kainos_detales": pricing_details,
        "veikimo_budas": run_mode,
        "online_limitai": online_limits,
        "lokalus_reikalavimai": local_requirements,
        "prieinamumas": availability,
        "kur_isbandyti": f"Galima tikrinti cia: {try_url}" if try_url else UNKNOWN_LT,
        "try_url": try_url,
    }


def build_bullets(item: NewsItem, practical: dict[str, str]) -> list[str]:
    bullets: list[str] = []

    for sentence in split_sentences(item.summary_lt):
        line = ensure_sentence(sentence)
        if not line:
            continue
        bullets.append(line)
        if len(bullets) >= 3:
            break

    extras = [
        f"Kaina: {practical.get('kaina', UNKNOWN_LT)}",
        f"Veikimo budas: {practical.get('veikimo_budas', UNKNOWN_LT)}",
        f"Prieinamumas: {practical.get('prieinamumas', UNKNOWN_LT)}",
    ]
    for extra in extras:
        if UNKNOWN_LT.lower() in extra.lower():
            continue
        bullets.append(ensure_sentence(extra))
        if len(bullets) >= 6:
            break

    if not bullets:
        bullets.append("Detalesnes santraukos nepavyko sugeneruoti.")

    deduped: list[str] = []
    seen: set[str] = set()
    for bullet in bullets:
        key = bullet.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(bullet)
    return deduped[:6]


def enrich_item_details(item: NewsItem) -> None:
    context_parts = [item.summary_lt]
    links = [item.link] if item.link else []

    if item.kind == "article" and item.link:
        article_text, article_links = fetch_article_context(item.link)
        if article_text:
            context_parts.append(article_text)
        links.extend(article_links)

    context_text = normalize_text(" ".join(part for part in context_parts if part))
    practical = build_practical_info(item, context_text, links)
    item.practical = practical
    item.bullets_lt = build_bullets(item, practical)


def item_to_payload(item: NewsItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "link": item.link,
        "published_iso": item.published_iso,
        "published_lt": item.published_lt,
        "summary": item.summary_lt,
        "source": item.source,
        "source_image_url": item.source_image_url,
        "image_url": item.image_url,
        "kind": item.kind,
        "video_id": item.video_id,
        "bullets_lt": item.bullets_lt,
        "practical": item.practical,
    }


def build_post(items: list[NewsItem], topic: str, digest_date: str, generated_at: str) -> str:
    lines = [
        "---",
        "layout: post",
        f'title: "DI ir technologiju naujienu santrauka - {digest_date}"',
        f"date: {digest_date} 07:00:00 +0000",
        "categories: [ai, technologijos, youtube, automatizacija]",
        "---",
        "",
        f"Automatiskai sugeneruota dienos santrauka temai: **{topic}**.",
        f"Generavimo laikas (UTC): {generated_at}",
        "",
    ]

    for index, item in enumerate(items, start=1):
        safe_title = item.title.replace("|", "-")
        item_type = "YouTube video" if item.kind == "video" else "Straipsnis"
        practical = item.practical

        lines.extend(
            [
                f"## {index}. {safe_title}",
                f"Tipas: {item_type}",
                f"Saltinis: {item.source}",
                f"Publikuota: {item.published_lt}",
                f"Nuoroda: {item.link}",
                "",
                "Svarbiausi punktai:",
                "",
            ]
        )

        for bullet in item.bullets_lt[:6]:
            lines.append(f"- {bullet}")

        lines.extend(
            [
                "",
                f"- Kaina: {practical.get('kaina', UNKNOWN_LT)}",
                f"- Kainos detales: {practical.get('kainos_detales', UNKNOWN_LT)}",
                f"- Veikimo budas: {practical.get('veikimo_budas', UNKNOWN_LT)}",
                f"- Online limitai: {practical.get('online_limitai', UNKNOWN_LT)}",
                f"- Lokalios sistemos poreikiai: {practical.get('lokalus_reikalavimai', UNKNOWN_LT)}",
                f"- Prieinamumas: {practical.get('prieinamumas', UNKNOWN_LT)}",
                f"- Kur isbandyti: {practical.get('kur_isbandyti', UNKNOWN_LT)}",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def build_latest_payload(items: list[NewsItem], topic: str, digest_date: str, generated_at: str) -> dict[str, Any]:
    return {
        "topic_lt": topic,
        "digest_date": digest_date,
        "generated_at_utc": generated_at,
        "translate_to_lt": TRANSLATE_TO_LT,
        "image_mode": IMAGE_MODE,
        "items": [item_to_payload(item) for item in items],
    }


def load_archive(topic: str) -> dict[str, Any]:
    if not ARCHIVE_JSON_PATH.exists():
        return {"topic_lt": topic, "updated_at_utc": "", "digests": []}

    try:
        data = json.loads(ARCHIVE_JSON_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"topic_lt": topic, "updated_at_utc": "", "digests": []}

    if not isinstance(data, dict):
        return {"topic_lt": topic, "updated_at_utc": "", "digests": []}

    digests = data.get("digests") if isinstance(data.get("digests"), list) else []
    return {
        "topic_lt": str(data.get("topic_lt") or topic),
        "updated_at_utc": str(data.get("updated_at_utc") or ""),
        "digests": digests,
    }


def upsert_archive_digest(archive: dict[str, Any], digest_date: str, generated_at: str, items: list[NewsItem]) -> None:
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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    topic = os.getenv("NEWS_TOPIC", DEFAULT_TOPIC).strip() or DEFAULT_TOPIC
    rss_feeds = selected_rss_feeds()
    youtube_feeds = load_youtube_channels()

    now_utc = dt.datetime.now(dt.timezone.utc)
    digest_date = now_utc.date().isoformat()
    generated_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    collected: list[NewsItem] = []
    errors: list[str] = []

    for feed in rss_feeds:
        try:
            collected.extend(read_rss_feed(feed))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"RSS {feed}: {exc}")

    for feed in youtube_feeds:
        try:
            collected.extend(read_youtube_feed(feed))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"YouTube {feed}: {exc}")

    unique_items = dedupe(collected)
    if not unique_items:
        print("Nepavyko surinkti naujienu.")
        for err in errors:
            print(f"- {err}")
        return 1

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    post_items = choose_digest_items(unique_items, MAX_ITEMS, MIN_VIDEO_ITEMS)

    for item in post_items:
        enrich_item_details(item)

    cleanup_digest_images(digest_date)

    for idx, item in enumerate(post_items, start=1):
        generated_image_url = generate_svg_image(item, digest_date=digest_date, index=idx)
        item.image_url = choose_image(item.source_image_url, generated_image_url)

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
    print(f"Sugeneruota iliustraciju kataloge: {GENERATED_IMAGES_DIR}")

    if youtube_feeds:
        print(f"YouTube feed'u skaicius: {len(youtube_feeds)}")
    else:
        print("YouTube feed'u nerasta. Nurodyk NEWS_YOUTUBE_CHANNELS aplinkos kintamaji.")

    if errors:
        print("Dalis saltiniu nepasiekiami:")
        for err in errors:
            print(f"- {err}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
