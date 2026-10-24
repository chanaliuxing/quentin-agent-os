import re

def sanitize_user_facing_text(text: str) -> str:
    """
    P5 Port: sanitizeUserFacingText.
    Strips LLM narration, Markdown blocks, and common noise to get clean content.
    """
    if not text:
        return ""
    
    # 1. Strip common markdown blocks
    # Try to extract content inside ```json ... ``` first if it's there
    json_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if json_match:
        text = json_match.group(1).strip()
    else:
        # Generic markdown code block strip
        text = re.sub(r"```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```", "", text)

    # 2. Strip <thought> tags (common in reasoning models)
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL | re.IGNORECASE)
    
    # 3. Strip leading/trailing narrations (best effort)
    # If the text starts with "Certainly!", "Here is", etc. and then has a newline
    lines = text.splitlines()
    if lines and len(lines) > 1:
        first = lines[0].lower().strip()
        if any(first.startswith(p) for p in ["certainly", "here is", "ok", "i will", "sure"]):
            # If the first line is short, it's likely narration
            if len(first) < 50:
                text = "\n".join(lines[1:]).strip()

    return text.strip()

def salvage_json_from_mess(text: str) -> str:
    """
    Attempts to find a JSON-like structure in a messy string.
    """
    # Find first '{' or '[' and last '}' or ']'
    first_obj = text.find('{')
    first_arr = text.find('[')
    
    start = -1
    if first_obj != -1 and first_arr != -1:
        start = min(first_obj, first_arr)
    elif first_obj != -1:
        start = first_obj
    elif first_arr != -1:
        start = first_arr
        
    last_obj = text.rfind('}')
    last_arr = text.rfind(']')
    
    end = -1
    if last_obj != -1 and last_arr != -1:
        end = max(last_obj, last_arr)
    elif last_obj != -1:
        end = last_obj
    elif last_arr != -1:
        end = last_arr
        
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
        
    return text
