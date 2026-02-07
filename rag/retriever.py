from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neo4j import GraphDatabase, Session
from neo4j.exceptions import Neo4jError


@dataclass
class RetrievedChange:
    change_id: str
    patch_id: str
    section_name: str
    text: str
    source_url: str | None
    score: float
    agents: list[str]


class GraphRetriever:
    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "password",
        neo4j_database: str = "neo4j",
    ) -> None:
        self.neo4j_database = neo4j_database
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    def close(self) -> None:
        self.driver.close()

    def __enter__(self) -> "GraphRetriever":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def retrieve(self, query: str, k: int = 8) -> dict[str, Any]:
        with self.driver.session(database=self.neo4j_database) as session:
            matched_agents = self._resolve_agents(session, query)
            if matched_agents:
                changes = self._query_by_agents(session, [agent["uuid"] for agent in matched_agents], k)
            else:
                changes = self._query_by_fulltext(session, query, k)

        return {
            "matched_agents": [agent["name"] for agent in matched_agents],
            "changes": changes,
        }

    def _resolve_agents(self, session: Session, query: str) -> list[dict[str, str]]:
        records = session.run(
            """
            MATCH (a:Agent)
            WHERE any(alias IN coalesce(a.aliases, [a.name]) WHERE toLower($search_text) CONTAINS toLower(alias))
            RETURN DISTINCT a.uuid AS uuid, a.name AS name
            ORDER BY size(name) DESC
            LIMIT 4
            """,
            search_text=query,
        )
        return [{"uuid": row["uuid"], "name": row["name"]} for row in records]

    def _query_by_agents(self, session: Session, agent_uuids: list[str], k: int) -> list[RetrievedChange]:
        records = session.run(
            """
            MATCH (a:Agent) WHERE a.uuid IN $agent_uuids
            MATCH (a)<-[:MENTIONS_AGENT]-(c:Change)
            WITH DISTINCT c
            MATCH (s:Section)-[:HAS_CHANGE]->(c)
            MATCH (p:Patch)-[:HAS_SECTION]->(s)
            OPTIONAL MATCH (c)-[:MENTIONS_AGENT]->(a2:Agent)
            WITH
                c,
                p,
                s,
                collect(DISTINCT a2.name) AS agents,
                s.order AS section_order,
                c.order AS change_order
            RETURN
                c.id AS change_id,
                p.id AS patch_id,
                s.name AS section_name,
                c.text AS text,
                c.source_url AS source_url,
                agents,
                10.0 AS score
            ORDER BY section_order ASC, change_order ASC
            LIMIT $k
            """,
            agent_uuids=agent_uuids,
            k=k,
        )
        return [self._record_to_change(row) for row in records]

    def _query_by_fulltext(self, session: Session, query: str, k: int) -> list[RetrievedChange]:
        try:
            records = session.run(
                """
                CALL db.index.fulltext.queryNodes('change_text_ft', $search_text) YIELD node, score
                WITH node, score
                WHERE node:Change
                MATCH (s:Section)-[:HAS_CHANGE]->(node)
                MATCH (p:Patch)-[:HAS_SECTION]->(s)
                OPTIONAL MATCH (node)-[:MENTIONS_AGENT]->(a:Agent)
                RETURN
                    node.id AS change_id,
                    p.id AS patch_id,
                    s.name AS section_name,
                    node.text AS text,
                    node.source_url AS source_url,
                    collect(DISTINCT a.name) AS agents,
                    score AS score
                ORDER BY score DESC
                LIMIT $k
                """,
                search_text=query,
                k=k,
            )
            return [self._record_to_change(row) for row in records]
        except Neo4jError:
            fallback_records = session.run(
                """
                MATCH (p:Patch)-[:HAS_SECTION]->(s:Section)-[:HAS_CHANGE]->(c:Change)
                WHERE toLower(c.text) CONTAINS toLower($search_text) OR toLower(s.name) CONTAINS toLower($search_text)
                OPTIONAL MATCH (c)-[:MENTIONS_AGENT]->(a:Agent)
                RETURN
                    c.id AS change_id,
                    p.id AS patch_id,
                    s.name AS section_name,
                    c.text AS text,
                    c.source_url AS source_url,
                    collect(DISTINCT a.name) AS agents,
                    1.0 AS score
                ORDER BY s.order ASC, c.order ASC
                LIMIT $k
                """,
                search_text=query,
                k=k,
            )
            return [self._record_to_change(row) for row in fallback_records]

    @staticmethod
    def _record_to_change(record: Any) -> RetrievedChange:
        return RetrievedChange(
            change_id=record["change_id"],
            patch_id=record["patch_id"],
            section_name=record["section_name"],
            text=record["text"],
            source_url=record["source_url"],
            score=float(record["score"]),
            agents=[agent for agent in (record["agents"] or []) if agent],
        )
