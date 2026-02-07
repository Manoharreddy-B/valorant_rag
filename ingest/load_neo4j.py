from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Session

DEFAULT_SCHEMA_FILE = Path(__file__).resolve().parents[1] / "cypher" / "constraints_and_indexes.cypher"


def normalize_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def apply_schema(session: Session, schema_path: Path = DEFAULT_SCHEMA_FILE) -> None:
    cypher_text = schema_path.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in cypher_text.split(";") if stmt.strip()]
    for statement in statements:
        session.run(statement)


def upsert_agents(session: Session, agents: list[dict[str, Any]]) -> None:
    if not agents:
        return
    session.run(
        """
        UNWIND $rows AS row
        MERGE (a:Agent {uuid: row.uuid})
        SET
            a.name = row.name,
            a.role = row.role,
            a.icon_url = row.icon_url,
            a.abilities = row.abilities,
            a.aliases = row.aliases
        """,
        rows=agents,
    )


def clear_patch_subgraph(session: Session, patch_id: str) -> None:
    session.run(
        """
        MATCH (p:Patch {id: $patch_id})-[:HAS_SECTION]->(s:Section)
        OPTIONAL MATCH (s)-[:HAS_CHANGE]->(c:Change)
        OPTIONAL MATCH (c)-[r:MENTIONS_AGENT]->(:Agent)
        DELETE r
        DETACH DELETE c, s
        """,
        patch_id=patch_id,
    )


def upsert_patch(session: Session, patch_doc: dict[str, Any]) -> tuple[int, int]:
    patch = patch_doc["patch"]
    sections = patch_doc.get("sections", [])

    session.run(
        """
        MERGE (p:Patch {id: $id})
        SET
            p.title = $title,
            p.url = $url,
            p.published_at = $published_at
        """,
        id=patch["id"],
        title=patch.get("title"),
        url=patch.get("url"),
        published_at=patch.get("published_at"),
    )

    clear_patch_subgraph(session, patch["id"])

    section_count = 0
    change_count = 0
    for section in sections:
        section_count += 1
        session.run(
            """
            MATCH (p:Patch {id: $patch_id})
            MERGE (s:Section {id: $id})
            SET
                s.name = $name,
                s.order = $order,
                s.patch_id = $patch_id
            MERGE (p)-[:HAS_SECTION]->(s)
            """,
            patch_id=patch["id"],
            id=section["id"],
            name=section["name"],
            order=section.get("order", section_count - 1),
        )

        changes = section.get("changes", [])
        change_count += len(changes)
        if not changes:
            continue

        session.run(
            """
            MATCH (s:Section {id: $section_id})
            UNWIND $changes AS change
            MERGE (c:Change {id: change.id})
            SET
                c.text = change.text,
                c.section_name = change.section_name,
                c.source_url = change.source_url,
                c.order = change.order
            MERGE (s)-[:HAS_CHANGE]->(c)
            """,
            section_id=section["id"],
            changes=changes,
        )

    return section_count, change_count


def detect_agent_mentions(change_text: str, agents: list[dict[str, Any]]) -> list[str]:
    normalized_text = f" {normalize_for_match(change_text)} "
    if not normalized_text.strip():
        return []

    matched_uuids: list[str] = []
    for agent in agents:
        uuid = agent.get("uuid")
        if not uuid:
            continue

        aliases = agent.get("aliases") or [agent.get("name")]
        for alias in aliases:
            alias_normalized = normalize_for_match(alias or "")
            if len(alias_normalized) < 3:
                continue
            if f" {alias_normalized} " in normalized_text:
                matched_uuids.append(uuid)
                break

    return sorted(set(matched_uuids))


def relink_patch_agent_mentions(session: Session, patch_id: str, agents: list[dict[str, Any]]) -> int:
    if not agents:
        return 0

    session.run(
        """
        MATCH (p:Patch {id: $patch_id})-[:HAS_SECTION]->(:Section)-[:HAS_CHANGE]->(c:Change)-[r:MENTIONS_AGENT]->(:Agent)
        DELETE r
        """,
        patch_id=patch_id,
    )

    records = session.run(
        """
        MATCH (p:Patch {id: $patch_id})-[:HAS_SECTION]->(:Section)-[:HAS_CHANGE]->(c:Change)
        RETURN c.id AS change_id, c.text AS text
        """,
        patch_id=patch_id,
    )

    links_created = 0
    for record in records:
        change_id = record["change_id"]
        text = record["text"] or ""
        mentioned_agent_uuids = detect_agent_mentions(text, agents)
        if not mentioned_agent_uuids:
            continue

        session.run(
            """
            MATCH (c:Change {id: $change_id})
            UNWIND $agent_uuids AS uuid
            MATCH (a:Agent {uuid: uuid})
            MERGE (c)-[:MENTIONS_AGENT]->(a)
            """,
            change_id=change_id,
            agent_uuids=mentioned_agent_uuids,
        )
        links_created += len(mentioned_agent_uuids)

    return links_created


def load_to_neo4j(
    patch_doc: dict[str, Any],
    agents_doc: dict[str, Any] | None,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str = "neo4j",
    apply_schema_file: Path | None = DEFAULT_SCHEMA_FILE,
    wipe: bool = False,
) -> dict[str, int]:
    agents = (agents_doc or {}).get("agents", [])
    patch_id = patch_doc["patch"]["id"]

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        with driver.session(database=neo4j_database) as session:
            if wipe:
                session.run("MATCH (n) DETACH DELETE n")

            if apply_schema_file is not None:
                apply_schema(session, apply_schema_file)

            upsert_agents(session, agents)
            section_count, change_count = upsert_patch(session, patch_doc)
            links_created = relink_patch_agent_mentions(session, patch_id=patch_id, agents=agents)

        return {
            "sections": section_count,
            "changes": change_count,
            "agents": len(agents),
            "agent_links": links_created,
        }
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load parsed patch data into Neo4j.")
    parser.add_argument("--patch-json", required=True, help="Path to parsed patch JSON.")
    parser.add_argument("--agents-json", help="Path to agents JSON (optional).")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j Bolt URI.")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username.")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password.")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database.")
    parser.add_argument("--schema-file", default=str(DEFAULT_SCHEMA_FILE), help="Cypher schema file path.")
    parser.add_argument("--skip-schema", action="store_true", help="Skip applying constraints/indexes.")
    parser.add_argument("--wipe", action="store_true", help="Delete all nodes before loading.")
    args = parser.parse_args()

    with open(args.patch_json, "r", encoding="utf-8") as file_obj:
        patch_doc = json.load(file_obj)

    agents_doc = None
    if args.agents_json:
        with open(args.agents_json, "r", encoding="utf-8") as file_obj:
            agents_doc = json.load(file_obj)

    schema_path = None if args.skip_schema else Path(args.schema_file)
    stats = load_to_neo4j(
        patch_doc=patch_doc,
        agents_doc=agents_doc,
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        apply_schema_file=schema_path,
        wipe=args.wipe,
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
