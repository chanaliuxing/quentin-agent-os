def prune_text(text: str, max_chars: int = 1000) -> str:
    if len(text) <= max_chars:
        return text
    
    half = max_chars // 2
    prefix = text[:half]
    suffix = text[-half:]
    return f"{prefix}\n... [PRUNED {len(text) - max_chars} CHARS] ...\n{suffix}"

def prune_messages(messages: list, max_tokens: int = 4000) -> list:
    # Basic message pruning logic
    if len(messages) <= 5:
        return messages
    return messages[:1] + messages[-4:]

# Alias for Executor
pruner = prune_messages
