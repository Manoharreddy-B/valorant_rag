from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingest.fetch_agents import fetch_agents
from ingest.fetch_current_patch import fetch_current_patch
from ingest.load_neo4j import DEFAULT_SCHEMA_FILE, load_to_neo4j
from ingest.parse_patch import parse_patch_notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end ingestion for the latest Valorant patch notes.")
    parser.add_argument("--output-dir", default="data", help="Directory to store fetched JSON artifacts.")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j Bolt URI.")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username.")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password.")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database.")
    parser.add_argument("--skip-agents", action="store_true", help="Skip fetching and loading agents.")
    parser.add_argument("--wipe", action="store_true", help="Delete all existing graph data before loading.")
    parser.add_argument("--skip-schema", action="store_true", help="Skip applying constraints/indexes.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    patch_meta = fetch_current_patch()
    patch_doc = parse_patch_notes(patch_meta["url"])

    patch_id = patch_doc["patch"]["id"]
    patch_meta_path = output_dir / "current_patch.json"
    patch_doc_path = output_dir / f"patch_{patch_id}.json"

    with open(patch_meta_path, "w", encoding="utf-8") as file_obj:
        json.dump(patch_meta, file_obj, indent=2)
    with open(patch_doc_path, "w", encoding="utf-8") as file_obj:
        json.dump(patch_doc, file_obj, indent=2)

    agents_doc = None
    agents_path = output_dir / "agents.json"
    if not args.skip_agents:
        agents_doc = fetch_agents()
        with open(agents_path, "w", encoding="utf-8") as file_obj:
            json.dump(agents_doc, file_obj, indent=2)

    stats = load_to_neo4j(
        patch_doc=patch_doc,
        agents_doc=agents_doc,
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        apply_schema_file=None if args.skip_schema else DEFAULT_SCHEMA_FILE,
        wipe=args.wipe,
    )

    print("Pipeline complete.")
    print(f"Patch metadata: {patch_meta_path}")
    print(f"Patch document: {patch_doc_path}")
    if not args.skip_agents:
        print(f"Agents document: {agents_path}")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
