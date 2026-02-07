from __future__ import annotations

import argparse

from rag.answer import format_answer
from rag.retriever import GraphRetriever


def run_single_query(retriever: GraphRetriever, query: str, k: int) -> str:
    result = retriever.retrieve(query=query, k=k)
    return format_answer(
        question=query,
        matched_agents=result["matched_agents"],
        changes=result["changes"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the local Valorant patch-notes graph.")
    parser.add_argument("--query", help="Ask one question and exit.")
    parser.add_argument("--top-k", type=int, default=8, help="Maximum number of changes to return.")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j Bolt URI.")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username.")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password.")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database.")
    args = parser.parse_args()

    with GraphRetriever(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
    ) as retriever:
        if args.query:
            print(run_single_query(retriever, query=args.query, k=args.top_k))
            return

        print("Interactive mode. Type 'exit' to quit.")
        while True:
            try:
                query = input("> ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break

            if not query:
                continue
            if query.lower() in {"exit", "quit"}:
                break

            print(run_single_query(retriever, query=query, k=args.top_k))
            print()


if __name__ == "__main__":
    main()
