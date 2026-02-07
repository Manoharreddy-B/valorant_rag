from __future__ import annotations

import json
import unittest
from pathlib import Path

from ingest.fetch_agents import parse_agents_payload
from ingest.fetch_current_patch import extract_current_patch_link
from ingest.parse_patch import parse_patch_notes_html

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class IngestTests(unittest.TestCase):
    def test_extract_current_patch_link(self) -> None:
        html = (FIXTURE_DIR / "sample_patch_listing.html").read_text(encoding="utf-8")
        patch = extract_current_patch_link(html)

        self.assertEqual(patch["patch_id"], "12.02")
        self.assertIn("12-02", patch["url"])

    def test_parse_patch_notes_html(self) -> None:
        html = (FIXTURE_DIR / "sample_patch_article.html").read_text(encoding="utf-8")
        doc = parse_patch_notes_html(
            html=html,
            source_url="https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-12-02/",
        )

        self.assertEqual(doc["patch"]["id"], "12.02")
        self.assertEqual(doc["patch"]["published_at"], "2026-02-03")
        self.assertGreaterEqual(len(doc["sections"]), 2)

        all_change_text = json.dumps(doc["sections"])
        self.assertIn("Reyna", all_change_text)
        self.assertIn("Harbor", all_change_text)

    def test_parse_agents_payload(self) -> None:
        payload = {
            "data": [
                {
                    "uuid": "123",
                    "displayName": "Reyna",
                    "isPlayableCharacter": True,
                    "role": {"displayName": "Duelist"},
                    "displayIcon": "https://example.com/reyna.png",
                    "abilities": [
                        {"displayName": "Leer"},
                        {"displayName": "Dismiss"},
                    ],
                }
            ]
        }

        parsed = parse_agents_payload(payload)
        self.assertEqual(len(parsed["agents"]), 1)
        agent = parsed["agents"][0]
        self.assertEqual(agent["name"], "Reyna")
        self.assertIn("Leer", agent["aliases"])


if __name__ == "__main__":
    unittest.main()
