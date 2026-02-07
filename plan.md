Got it: **users ask anything about the *current* patch**, and you want a **quick local GraphRAG prototype** in **Python + Neo4j (Docker Desktop)**, without time-aware complexity.

Below is a plan that gets you to a working demo fast by ingesting just:

* **Latest official patch notes page** (single source of truth for “current patch”). As of now, the latest patch notes listed are **12.02 (2026-02-03)**. ([VALORANT][1])
* Optional “entity dictionary” (agents, etc.) from **Valorant-API** to do cheap entity linking + show icons. ([Valorant API][2])

---

## 1) Minimal scope (fast prototype)

**Ingest only the latest patch notes** (one page) and build a graph that supports:

* “What changed in this patch?”
* “What changed for Reyna/Harbor/etc?”
* “Summarize changes to UI / gameplay / agents”

No historical patch comparisons. No complex time logic.

**Why this is enough:** the current patch notes already contain structured sections and bullet points (perfect for nodes + relationships). ([VALORANT][1])

---

## 2) Data sources (quick + low friction)

### A) Current patch notes (official)

* Patch notes listing page → pick the first entry (latest). ([VALORANT][3])
* Patch notes article page (example: 12.02). ([VALORANT][1])

### B) Optional: Agent metadata (for entity matching + icons)

* `https://valorant-api.com/v1/agents` gives names, roles, ability names, and icons. ([Valorant API][2])
  (You can skip weapons/maps for MVP if you want—agent-only already makes the demo feel “smart”.)

---

## 3) Graph schema (small but GraphRAG-friendly)

Use **patch-note bullets** as your core “document units”.

### Nodes

* `(:Patch {id:"12.02", title, url, published_at})`
* `(:Section {name, order})`  (e.g., “Harbor ability adjustments”)
* `(:Change {id, text, section_name, source_url})`
* `(:Agent {uuid, name, role, icon_url})` (optional, from Valorant-API)

### Relationships

* `(p:Patch)-[:HAS_SECTION]->(s:Section)`
* `(s:Section)-[:HAS_CHANGE]->(c:Change)`
* `(c:Change)-[:MENTIONS_AGENT]->(a:Agent)`  (only if agent name/ability matched)
* (Optional later) `(c)-[:TAGGED {label:"UI"|"Balance"|"Bugfix"}]->(:Tag {name})`

This gives you:

* **Graph traversal** (entity → related changes)
* **RAG grounding** (Change nodes contain the text you cite back)

---

## 4) Ingestion pipeline (1 script)

### Step 4.1 Find “current patch” URL

Scrape the patch notes tag page and take the first link. ([VALORANT][3])

### Step 4.2 Parse the patch notes article

Extract:

* Title / patch id (e.g., “12.02”) ([VALORANT][1])
* Sections (H2/H3 headers)
* Bullets/paragraphs under each section → create `Change` nodes

### Step 4.3 Entity linking (keep it dumb + reliable)

For MVP:

* Build a dictionary of `Agent.name` and `Ability.displayName` from Valorant-API. ([Valorant API][2])
* For each `Change.text`, do:

  * exact/substring match (fast)
  * optional fuzzy match with `rapidfuzz` for robustness

If a match hits, attach `(Change)-[:MENTIONS_AGENT]->(Agent)`.

---

## 5) Indexing for retrieval (full-text + vectors)

You have two simple options; do **A first**, add **B** if you want better “semantic” matching.

### A) Full-text index (fastest MVP)

* Full-text index on `Change.text` and `Section.name`
* Retrieval = `db.index.fulltext.queryNodes(...)` + optional graph expansion

### B) Vector index (better “ask anything” feel)

Neo4j supports **vector indexes over embeddings stored as LIST<FLOAT>**. ([Graph Database & Analytics][4])

* Compute embeddings for `Change.text` using a **local** model (`sentence-transformers`)
* Store `c.embedding = [..floats..]`
* Create a vector index and query it for top-k similar changes

(Neo4j’s docs also call out embeddings can be produced by open-source generators like sentence-transformers. ([Graph Database & Analytics][4]))

---

## 6) GraphRAG query flow (the “prototype chatbot”)

When user asks: “What changed about Reyna this patch?”

1. **Retriever (hybrid)**

   * If query mentions an entity (Reyna/Harbor): resolve to `Agent` node, traverse to connected `Change` nodes
   * Else: full-text / vector search over `Change.text` for top-k

2. **Context pack**

   * Return the bullet texts + their section names + source URL
   * (Optional) Include agent role/ability names for extra context

3. **Generator**

   * Use an LLM to summarize *only from retrieved context* + cite links

Neo4j’s official GraphRAG Python package is designed exactly for “Retriever + LLM” pipelines and is LangChain-compatible. ([Graph Database & Analytics][5])

---

## 7) Local stack (Docker Desktop) — quick setup

### docker-compose (Neo4j)

Run Neo4j locally with a mounted volume so you can iterate safely.

```yaml
services:
  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password
    volumes:
      - neo4j_data:/data
volumes:
  neo4j_data:
```

### Python deps (minimal)

* `neo4j` (driver)
* `requests`, `beautifulsoup4`
* `rapidfuzz` (optional)
* `sentence-transformers` (optional embeddings)
* Optional: `neo4j-graphrag` (if you want the “official” GraphRAG wiring) ([Graph Database & Analytics][5])

---

## 8) Repo structure (keeps you moving fast)

```
valorant-graphrag/
  docker-compose.yml
  ingest/
    fetch_current_patch.py
    parse_patch.py
    load_neo4j.py
  rag/
    retriever.py
    answer.py
    cli.py
  cypher/
    constraints_and_indexes.cypher
```

---

## 9) Build milestones (fast)

### Milestone 1 (MVP: 2–4 hours)

* Neo4j up via docker-compose
* Ingest latest patch notes → `Patch/Section/Change`
* Full-text search over Change.text
* CLI: ask question → print top matched bullets + link

### Milestone 2 (GraphRAG feel: +2–4 hours)

* Ingest agents from Valorant-API (`Agent` nodes + icons) ([Valorant API][2])
* Entity-link changes to agents
* Query: if agent detected → graph traverse first, else full-text

### Milestone 3 (Semantic search: +2–6 hours)

* Add sentence-transformers embeddings
* Add Neo4j vector index + vector retrieval ([Graph Database & Analytics][4])
* Hybrid rank: (graph hits boosted) + (vector hits)

---

## 10) Defaults I’m choosing for speed (you can override)

* **English patch notes** (`/en-us/…`)
* **Only latest patch** is ingested (re-run ingest when patch changes)
* **Agent-only entity linking** (skip weapons/maps until later)
* **Full-text first**, embeddings later if you want

---