from __future__ import annotations

import email.utils
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
DATA = PUBLIC / "data"
BANGKOK = ZoneInfo("Asia/Bangkok")
CATEGORY_NAMES = {
    "international": "国际",
    "finance": "财经",
    "technology": "科技",
    "domestic": "国内",
    "other": "其他",
}
LIMITS = {"international": 10, "finance": 10, "technology": 10, "domestic": 7, "other": 5}
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")


def clean(value: str | None) -> str:
    value = html.unescape(TAG_RE.sub(" ", value or ""))
    return SPACE_RE.sub(" ", value).strip()


def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text:
            return child.text.strip()
    return ""


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed:
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def canonical_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urllib.parse.urlencode(query), ""))


def summary(text: str, title: str) -> str:
    text = clean(text)
    if text.lower().startswith(title.lower()):
        text = text[len(title):].lstrip(" :-–—")
    sentences = [s.strip() for s in SENTENCE_RE.split(text) if len(s.strip()) > 20]
    result = " ".join(sentences[:3]) if sentences else text
    if len(result) > 420:
        result = result[:417].rsplit(" ", 1)[0] + "…"
    if not result:
        result = "来源暂未在 RSS 中提供摘要，请打开原文查看报道详情。"
    return result


def fetch(feed: dict) -> list[dict]:
    request = urllib.request.Request(feed["url"], headers={"User-Agent": "MorningBrief/1.0 (+personal RSS reader)"})
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()
    root = ET.fromstring(raw)
    nodes = [n for n in root.iter() if n.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    items = []
    for node in nodes:
        title = clean(child_text(node, ("title",)))
        link = child_text(node, ("link",))
        if not link:
            for child in node.iter():
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        description = child_text(node, ("description", "summary", "content", "encoded"))
        published_raw = child_text(node, ("pubdate", "published", "updated", "date"))
        if not title or not link:
            continue
        published = parse_date(published_raw)
        items.append({
            "id": hashlib.sha1(canonical_url(link).encode("utf-8")).hexdigest()[:12],
            "title": title,
            "summary": summary(description, title),
            "source": feed["name"],
            "published": published.isoformat(),
            "published_display": published.astimezone(BANGKOK).strftime("%m月%d日 %H:%M"),
            "url": canonical_url(link),
            "category": feed["category"],
            "priority": int(feed.get("priority", 3)),
        })
    return items


def normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.lower())


def dedupe(items: list[dict]) -> list[dict]:
    kept: list[dict] = []
    seen_urls: set[str] = set()
    for item in sorted(items, key=lambda x: (x["published"], x["priority"]), reverse=True):
        if item["url"] in seen_urls:
            continue
        needle = normalized_title(item["title"])
        if any(SequenceMatcher(None, needle, normalized_title(old["title"])).ratio() > 0.84 for old in kept[-80:]):
            continue
        seen_urls.add(item["url"])
        kept.append(item)
    return kept


def render(data: dict, archive_prefix: str = "data/") -> str:
    cards = []
    for key, label in CATEGORY_NAMES.items():
        stories = data["sections"].get(key, [])
        article_html = "".join(
            f'''<article class="story"><div class="story-meta"><span class="source">{html.escape(s["source"])}</span><time>{html.escape(s["published_display"])}</time></div><h3><a href="{html.escape(s["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(s["title"])}</a></h3><p>{html.escape(s["summary"])}</p><a class="read-more" href="{html.escape(s["url"], quote=True)}" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></article>'''
            for s in stories
        ) or '<p class="empty">今天暂时没有抓取到这一栏的内容。</p>'
        cards.append(f'<section id="{key}" class="news-section"><h2>{label}<span>{len(stories)} 条</span></h2><div class="story-grid">{article_html}</div></section>')
    archive = "".join(f'<a href="{archive_prefix}{d}.html">{d}</a>' for d in data["history"])
    return TEMPLATE.replace("{{DATE}}", data["date_display"]).replace("{{UPDATED}}", data["updated_display"]).replace("{{SECTIONS}}", "".join(cards)).replace("{{ARCHIVE}}", archive)


TEMPLATE = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="每日财经、科技与国际事实新闻简报"><title>晨间新闻 · {{DATE}}</title><link rel="stylesheet" href="../styles.css"></head><body><header class="hero"><div class="hero-inner"><p class="eyebrow">MORNING BRIEF · BANGKOK</p><h1>晨间新闻</h1><p class="date">{{DATE}}</p><p class="updated">更新时间：{{UPDATED}}（曼谷）</p><nav><a href="#international">国际</a><a href="#finance">财经</a><a href="#technology">科技</a><a href="#domestic">国内</a><a href="#other">其他</a></nav></div></header><main>{{SECTIONS}}<section class="history"><h2>最近 7 天</h2><div class="history-links">{{ARCHIVE}}</div></section></main><footer>内容来自公开 RSS，摘要仅用于快速浏览。重要信息请以原文为准。</footer></body></html>'''


def main() -> int:
    now = datetime.now(BANGKOK)
    feeds = json.loads((ROOT / "config" / "feeds.json").read_text(encoding="utf-8"))
    all_items, failures = [], []
    for feed in feeds:
        try:
            found = fetch(feed)
            all_items.extend(found)
            print(f"OK   {feed['name']}: {len(found)}")
        except Exception as exc:
            failures.append(f"{feed['name']}: {exc}")
            print(f"FAIL {feed['name']}: {exc}", file=sys.stderr)
    if not all_items:
        print("No feeds succeeded; existing site left untouched.", file=sys.stderr)
        return 1
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    fresh = [i for i in all_items if datetime.fromisoformat(i["published"]) >= cutoff]
    items = dedupe(fresh or all_items)
    sections = {key: [] for key in CATEGORY_NAMES}
    for item in items:
        bucket = sections[item["category"]]
        if len(bucket) < LIMITS[item["category"]]:
            bucket.append(item)
    DATA.mkdir(parents=True, exist_ok=True)
    date_key = now.strftime("%Y-%m-%d")
    existing = [p.stem for p in DATA.glob("20??-??-??.json")]
    history = sorted(set([date_key] + existing), reverse=True)[:7]
    payload = {
        "date": date_key,
        "date_display": now.strftime("%Y年%m月%d日 · %A").replace("Monday", "星期一").replace("Tuesday", "星期二").replace("Wednesday", "星期三").replace("Thursday", "星期四").replace("Friday", "星期五").replace("Saturday", "星期六").replace("Sunday", "星期日"),
        "updated": now.isoformat(),
        "updated_display": now.strftime("%H:%M"),
        "sections": sections,
        "history": history,
        "source_failures": failures,
    }
    json_path = DATA / f"{date_key}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_page = render(payload, archive_prefix="")
    (DATA / f"{date_key}.html").write_text(archive_page, encoding="utf-8")
    # The index is one directory shallower than archive pages.
    index_page = render(payload, archive_prefix="data/").replace('href="../styles.css"', 'href="styles.css"')
    (PUBLIC / "index.html").write_text(index_page, encoding="utf-8")
    for path in sorted(DATA.glob("20??-??-??.json"))[:-7]:
        path.unlink(missing_ok=True)
        path.with_suffix(".html").unlink(missing_ok=True)
    print(f"Generated {date_key}: {sum(map(len, sections.values()))} stories, {len(failures)} feed failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
