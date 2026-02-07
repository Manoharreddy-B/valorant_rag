from __future__ import annotations

import argparse
import json
import re
from typing import Any

from ingest.simple_html import ElementEvent, ParsedHTML, normalize_space, parse_html

PATCH_ID_RE = re.compile(r"\b(\d{1,2})[.-](\d{1,2})\b")
NOISE_HEADINGS = {
    "share",
    "copy link",
    "riot games",
    "news",
    "play now",
    "related articles",
}
NOISE_CHANGES = {
    "share",
    "copy link",
    "read more",
    "learn more",
}

def find_patch_id(*values: str) -> str | None:
    for value in values:
        match = PATCH_ID_RE.search(value or "")
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            return f"{major}.{minor:02d}"
    return None


def scoped_events(parsed: ParsedHTML) -> list[ElementEvent]:
    if any("article" in event.parents for event in parsed.events):
        return [event for event in parsed.events if "article" in event.parents]
    if any("main" in event.parents for event in parsed.events):
        return [event for event in parsed.events if "main" in event.parents]
    return parsed.events


def extract_meta(parsed: ParsedHTML, key: str, value: str) -> str | None:
    for meta in parsed.metas:
        if meta.get(key) == value:
            content = normalize_space(meta.get("content", ""))
            if content:
                return content
    return None


def extract_title(parsed: ParsedHTML, events: list[ElementEvent]) -> str:
    og_title = extract_meta(parsed, "property", "og:title")
    if og_title:
        return og_title

    for event in events:
        if event.tag == "h1" and event.text:
            return event.text

    if parsed.title:
        return parsed.title

    return "Valorant Patch Notes"


def extract_published_at(parsed: ParsedHTML, events: list[ElementEvent]) -> str | None:
    published = extract_meta(parsed, "property", "article:published_time")
    if published:
        return published

    for event in events:
        if event.tag != "time":
            continue
        if event.attrs.get("datetime"):
            return normalize_space(event.attrs["datetime"])
        if event.text:
            return event.text

    return None


def should_keep_heading(text: str) -> bool:
    normalized = text.lower().strip()
    if not normalized:
        return False
    return normalized not in NOISE_HEADINGS


def should_keep_change(text: str) -> bool:
    normalized = text.lower().strip()
    if not normalized:
        return False
    if normalized in NOISE_CHANGES:
        return False
    if normalized.startswith("related articles"):
        return False
    if "game updates" in normalized and "patch notes" in normalized:
        return False
    if re.search(r"\d{4}-\d{2}-\d{2}t\d{2}:\d{2}", normalized):
        return False
    if len(normalized) < 12:
        return False
    if len(normalized) > 500:
        return False
    return True


def parse_patch_notes_html(html: str, source_url: str) -> dict[str, Any]:
    parsed = parse_html(html)
    events = scoped_events(parsed)
    title = extract_title(parsed, events)
    patch_id = find_patch_id(title, source_url) or "latest"
    published_at = extract_published_at(parsed, events)

    raw_sections: list[dict[str, Any]] = [
        {
            "name": "General",
            "changes": [],
        }
    ]
    current_section = raw_sections[0]
    seen_changes: set[tuple[str, str]] = set()

    for event in events:
        if event.tag not in {"h2", "h3", "li", "p"}:
            continue

        text = normalize_space(event.text)
        if not text:
            continue

        if event.tag in {"h2", "h3"}:
            heading_normalized = text.lower().strip()
            if heading_normalized == "related articles":
                break
            if should_keep_heading(text):
                current_section = {"name": text, "changes": []}
                raw_sections.append(current_section)
            continue

        if event.tag == "p" and "li" in event.parents:
            continue

        if should_keep_change(text):
            dedupe_key = (current_section["name"], text)
            if dedupe_key not in seen_changes:
                current_section["changes"].append(text)
                seen_changes.add(dedupe_key)

    sections: list[dict[str, Any]] = []
    for section_index, raw_section in enumerate(raw_sections):
        if not raw_section["changes"]:
            continue

        section_id = f"{patch_id}-s{len(sections)}"
        section_name = raw_section["name"]
        changes: list[dict[str, Any]] = []
        for change_index, change_text in enumerate(raw_section["changes"]):
            change_id = f"{section_id}-c{change_index}"
            changes.append(
                {
                    "id": change_id,
                    "text": change_text,
                    "section_name": section_name,
                    "source_url": source_url,
                    "order": change_index,
                }
            )

        sections.append(
            {
                "id": section_id,
                "name": section_name,
                "order": section_index,
                "changes": changes,
            }
        )

    return {
        "patch": {
            "id": patch_id,
            "title": title,
            "url": source_url,
            "published_at": published_at,
        },
        "sections": sections,
    }


def fetch_patch_html(url: str, timeout: int = 20) -> str:
    import requests

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_patch_notes(url: str) -> dict[str, Any]:
    html = fetch_patch_html(url)
    return parse_patch_notes_html(html, source_url=url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a Valorant patch-notes article into sections/changes.")
    parser.add_argument("--url", help="Patch notes URL to fetch and parse.")
    parser.add_argument("--html-file", help="Local HTML file path to parse.")
    parser.add_argument("--source-url", help="Source URL used in output when --html-file is provided.")
    parser.add_argument("--out", help="Optional JSON file output path.")
    args = parser.parse_args()

    if not args.url and not args.html_file:
        parser.error("Provide either --url or --html-file.")

    if args.url and args.html_file:
        parser.error("Use either --url or --html-file, not both.")

    if args.url:
        doc = parse_patch_notes(args.url)
    else:
        with open(args.html_file, "r", encoding="utf-8") as file_obj:
            html = file_obj.read()
        source_url = args.source_url or "local://patch-notes.html"
        doc = parse_patch_notes_html(html, source_url=source_url)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as file_obj:
            json.dump(doc, file_obj, indent=2)
        print(f"Wrote parsed patch document to {args.out}")
    else:
        print(json.dumps(doc, indent=2))


if __name__ == "__main__":
    main()
