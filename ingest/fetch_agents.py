from __future__ import annotations

import argparse
import json
from typing import Any

AGENTS_API_URL = "https://valorant-api.com/v1/agents?isPlayableCharacter=true"


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def parse_agents_payload(payload: dict[str, Any]) -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        if not item.get("isPlayableCharacter", False):
            continue

        name = normalize_space(item.get("displayName", ""))
        if not name:
            continue

        role_name = normalize_space(item.get("role", {}).get("displayName", "")) or None
        icon_url = item.get("displayIcon") or item.get("fullPortrait") or item.get("bustPortrait")

        abilities: list[str] = []
        aliases = {name}
        for ability in item.get("abilities", []):
            ability_name = normalize_space(ability.get("displayName", ""))
            if not ability_name:
                continue
            abilities.append(ability_name)
            aliases.add(ability_name)

        agents.append(
            {
                "uuid": item.get("uuid"),
                "name": name,
                "role": role_name,
                "icon_url": icon_url,
                "abilities": sorted(set(abilities), key=str.lower),
                "aliases": sorted(aliases, key=str.lower),
            }
        )

    agents = [agent for agent in agents if agent.get("uuid")]
    agents.sort(key=lambda agent: agent["name"].lower())
    return {"agents": agents}


def fetch_agents(api_url: str = AGENTS_API_URL, timeout: int = 20) -> dict[str, Any]:
    import requests

    response = requests.get(api_url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    return parse_agents_payload(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Valorant agents from Valorant-API.")
    parser.add_argument("--api-url", default=AGENTS_API_URL, help="Agents API URL.")
    parser.add_argument("--out", help="Optional JSON file output path.")
    args = parser.parse_args()

    agents = fetch_agents(api_url=args.api_url)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as file_obj:
            json.dump(agents, file_obj, indent=2)
        print(f"Wrote agent metadata to {args.out}")
    else:
        print(json.dumps(agents, indent=2))


if __name__ == "__main__":
    main()
