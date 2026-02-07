from __future__ import annotations

import argparse
import json
import re
from typing import Any
from urllib.parse import urljoin

from ingest.simple_html import parse_html

PATCH_NOTES_TAG_URL = "https://playvalorant.com/en-us/news/tags/patch-notes/"
BASE_URL = "https://playvalorant.com"
PATCH_ID_RE = re.compile(r"(\d{1,2})[-.](\d{1,2})")


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def parse_patch_id(value: str) -> tuple[int, int] | None:
    match = PATCH_ID_RE.search(value)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    return major, minor


def format_patch_id(parts: tuple[int, int] | None) -> str | None:
    if parts is None:
        return None
    return f"{parts[0]}.{parts[1]:02d}"


def extract_current_patch_link(html: str, base_url: str = BASE_URL) -> dict[str, Any]:
    parsed = parse_html(html)
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for index, anchor in enumerate(event for event in parsed.events if event.tag == "a"):
        href = anchor.attrs.get("href", "").strip()
        if not href:
            continue
        lowered_href = href.lower()
        if "patch-notes" not in lowered_href:
            continue
        if "/news/tags/patch-notes" in lowered_href:
            continue
        if "/news/" not in lowered_href:
            continue

        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = normalize_space(anchor.text)
        patch_tuple = parse_patch_id(url) or parse_patch_id(title)

        candidates.append(
            {
                "title": title or "Valorant Patch Notes",
                "url": url,
                "patch_tuple": patch_tuple,
                "order": index,
            }
        )

    if not candidates:
        raise ValueError("Could not find any patch-notes links on the tag page.")

    versioned = [item for item in candidates if item["patch_tuple"] is not None]
    if versioned:
        versioned.sort(
            key=lambda item: (
                item["patch_tuple"][0],  # major
                item["patch_tuple"][1],  # minor
                -item["order"],  # prefer earliest occurrence when version ties
            ),
            reverse=True,
        )
        selected = versioned[0]
    else:
        selected = min(candidates, key=lambda item: item["order"])

    patch_id = format_patch_id(selected["patch_tuple"])
    return {
        "title": selected["title"],
        "url": selected["url"],
        "patch_id": patch_id,
    }


def fetch_current_patch(tag_url: str = PATCH_NOTES_TAG_URL, timeout: int = 20) -> dict[str, Any]:
    import requests

    response = requests.get(tag_url, timeout=timeout)
    response.raise_for_status()
    return extract_current_patch_link(response.text, base_url=BASE_URL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Find the current Valorant patch notes URL.")
    parser.add_argument("--tag-url", default=PATCH_NOTES_TAG_URL, help="Patch notes tag page URL.")
    parser.add_argument("--out", help="Optional JSON file output path.")
    args = parser.parse_args()

    patch_info = fetch_current_patch(args.tag_url)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as file_obj:
            json.dump(patch_info, file_obj, indent=2)
        print(f"Wrote current patch metadata to {args.out}")
    else:
        print(json.dumps(patch_info, indent=2))


if __name__ == "__main__":
    main()
