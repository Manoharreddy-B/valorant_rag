# Valorant Patch GraphRAG Prototype

Local prototype for asking questions about the current Valorant patch using Python + Neo4j.

## What this prototype does

- Fetches the latest patch-notes URL from the official patch-notes listing page.
- Parses the patch article into `Patch -> Section -> Change` nodes.
- Optionally ingests agents from Valorant-API and links changes with `MENTIONS_AGENT`.
- Loads everything into Neo4j with constraints + full-text indexes.
- Provides a CLI to query:
  - Agent-first traversal when the question mentions an agent/ability.
  - Full-text fallback for general questions.

## Prerequisites

- Docker Desktop
- Python 3.10+
- Internet access (for live fetches)

## Setup

1. Start Neo4j:

```bash
docker compose up -d
```

2. Create virtualenv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run ingestion pipeline

This fetches current patch + agents, writes JSON artifacts under `data/`, and loads Neo4j.

```bash
python -m ingest.run_pipeline --neo4j-password password --wipe
```

If you want patch-only ingest:

```bash
python -m ingest.run_pipeline --neo4j-password password --skip-agents --wipe
```

## Query the graph

Single query:

```bash
python -m rag.cli --neo4j-password password --query "What changed for Reyna this patch?"
```

Interactive mode:

```bash
python -m rag.cli --neo4j-password password
```

## Useful direct scripts

- Fetch current patch URL:

```bash
python -m ingest.fetch_current_patch
```

- Parse a specific patch URL to JSON:

```bash
python -m ingest.parse_patch --url "https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-12-02/" --out data/patch.json
```

- Load parsed JSON into Neo4j:

```bash
python -m ingest.load_neo4j --patch-json data/patch.json --agents-json data/agents.json --neo4j-password password
```

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```
