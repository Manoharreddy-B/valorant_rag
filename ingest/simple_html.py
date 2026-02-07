from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


def normalize_space(value: str) -> str:
    return " ".join(value.split())


@dataclass
class ElementEvent:
    tag: str
    attrs: dict[str, str]
    text: str
    parents: tuple[str, ...]


@dataclass
class ParsedHTML:
    title: str | None
    metas: list[dict[str, str]]
    events: list[ElementEvent]


class _Collector(HTMLParser):
    INTERESTING_TAGS = {"a", "h1", "h2", "h3", "p", "li", "time", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str] = []
        self._capture_stack: list[dict[str, Any]] = []
        self.events: list[ElementEvent] = []
        self.metas: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: (value or "") for key, value in attrs}
        self._stack.append(tag)

        if tag == "meta":
            self.metas.append(attrs_dict)

        if tag in self.INTERESTING_TAGS:
            self._capture_stack.append(
                {
                    "tag": tag,
                    "attrs": attrs_dict,
                    "parents": tuple(self._stack[:-1]),
                    "text_parts": [],
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if self._capture_stack and self._capture_stack[-1]["tag"] == tag:
            capture = self._capture_stack.pop()
            text = normalize_space("".join(capture["text_parts"]))
            self.events.append(
                ElementEvent(
                    tag=capture["tag"],
                    attrs=capture["attrs"],
                    text=text,
                    parents=capture["parents"],
                )
            )

        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index] == tag:
                del self._stack[index]
                break

    def handle_data(self, data: str) -> None:
        if not data or not self._capture_stack:
            return
        for capture in self._capture_stack:
            capture["text_parts"].append(f" {data} ")


def parse_html(html: str) -> ParsedHTML:
    collector = _Collector()
    collector.feed(html)
    collector.close()

    title = None
    for event in collector.events:
        if event.tag == "title" and event.text:
            title = event.text
            break

    return ParsedHTML(title=title, metas=collector.metas, events=collector.events)
