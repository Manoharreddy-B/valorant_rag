from __future__ import annotations

from rag.retriever import RetrievedChange


def format_answer(question: str, matched_agents: list[str], changes: list[RetrievedChange]) -> str:
    if not changes:
        return (
            f"No matching changes were found for: {question}\n"
            "Try using an agent name (for example: Reyna, Harbor, Jett) or a topic like UI or gameplay."
        )

    lines: list[str] = []
    lines.append(f"Question: {question}")
    if matched_agents:
        lines.append(f"Detected agent(s): {', '.join(matched_agents)}")

    lines.append(f"Top {len(changes)} change(s):")
    for index, change in enumerate(changes, start=1):
        agents_suffix = ""
        if change.agents:
            agents_suffix = f" | Mentions: {', '.join(change.agents)}"
        lines.append(f"{index}. [{change.patch_id}] {change.section_name}: {change.text}{agents_suffix}")

    source_urls: list[str] = []
    for change in changes:
        if change.source_url and change.source_url not in source_urls:
            source_urls.append(change.source_url)

    if source_urls:
        lines.append("Sources:")
        for url in source_urls[:3]:
            lines.append(f"- {url}")

    return "\n".join(lines)
