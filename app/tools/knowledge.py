from langchain.tools import tool

import app.clients.internal as _client


@tool
def search_knowledge(query: str) -> str:
    """
    Search the Carhist knowledge base for automotive information,
    including error codes, diagnostics, parts, maintenance,
    taxes, and regulations.
    Strict RAG: caller must not answer from parametric knowledge.
    """

    print(f">>> search_knowledge: {query}")

    data = _client._internal_post("/internal/knowledge_base/search", {"query": query})

    context = (data.get("context") or "").strip()
    if not context:
        return "NO_KNOWLEDGE_FOUND: no document matched query. Do not answer from general knowledge. You must refuse."

    return context
