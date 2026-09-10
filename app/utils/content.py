def _content_to_text(content):
    """Flatten a langchain/Google message `content` into a plain string.

    langchain-google-genai returns Gemini content as a list of blocks like
    [{"type": "text", "text": "...", "extras": {"signature": "..."}}]. Extract
    the text parts so the agent's `answer` is always a JSON string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)
