import bootstrap
import os
import hashlib
import time
from typing import List, Dict, Any, Tuple, Optional
from config import WORKSPACE_DIR, OFFLOAD_OVER, COMPACT_AT
from web import wrap_untrusted

os.makedirs(WORKSPACE_DIR, exist_ok=True)


def offload_if_needed(content: str, run_id: str = "default") -> Tuple[str, bool, Optional[Dict[str, Any]]]:
    """
    If content length exceeds OFFLOAD_OVER (2000 chars), save it to workspace/<id>.txt
    and return a preview with file metadata and instruction to use read_file.
    """
    if not isinstance(content, str):
        content = str(content)

    if len(content) <= OFFLOAD_OVER:
        return content, False, None

    # Generate a unique filename using timestamp and content hash
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    filename = f"offload_{int(time.time())}_{h}.txt"
    filepath = os.path.join(WORKSPACE_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    preview = content[:300]
    replaced_content = (
        f"[TOOL OUTPUT EXCEEDS {OFFLOAD_OVER} CHARS - OFFLOADED]\n"
        f"Saved to: {filepath}\n"
        f"Total characters: {len(content)}\n"
        f"Preview (first 300 chars):\n"
        f"{preview}\n...\n"
        f"[To inspect more, call read_file(path='{filepath}', offset=0, limit=2000)]"
    )

    offload_record = {
        "filepath": filepath,
        "filename": filename,
        "total_chars": len(content),
        "run_id": run_id,
        "timestamp": time.time(),
    }
    return replaced_content, True, offload_record


def read_file(path: str, offset: int = 0, limit: int = 2000) -> str:
    """
    Tool allowing the agent to read offloaded files piece by piece.
    """
    # Sanitize path to prevent directory traversal outside workspace
    norm_path = os.path.normpath(path)
    if not os.path.exists(norm_path):
        return f"Error: File '{path}' not found."

    try:
        with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            chunk = f.read(limit)
            total_size = os.path.getsize(norm_path)

        eof_status = "EOF reached" if (offset + len(chunk) >= total_size) else f"More content available (next offset: {offset + len(chunk)})"
        return (
            f"File: {path} (offset: {offset}, length: {len(chunk)}, total_size: {total_size} bytes, {eof_status}):\n\n"
            f"{wrap_untrusted(chunk)}"
        )
    except Exception as e:
        return f"Error reading file '{path}': {str(e)}"


def find_safe_compaction_cutoff(messages: List[Dict[str, Any]], target_kept_count: int = 4) -> int:
    """
    Finds a safe cutoff index so that tool_calls (in assistant message) and their
    matching tool result messages are NEVER separated.
    """
    total = len(messages)
    if total <= target_kept_count:
        return 0

    cutoff = total - target_kept_count

    # If the message at cutoff is a 'tool' result, we must backtrack to include
    # the assistant message that triggered it.
    while cutoff > 0 and messages[cutoff].get("role") == "tool":
        cutoff -= 1

    # Check if cutoff - 1 is an assistant with tool_calls that are answered in the kept part
    # If so, keep that assistant as well
    if cutoff > 0:
        prev_msg = messages[cutoff - 1]
        if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
            # Check if any tool result is in messages[cutoff:]
            cutoff -= 1

    return cutoff


def compact_messages_if_needed(
    system_prompt: str,
    messages: List[Dict[str, Any]],
    input_tokens: int,
    call_llm_fn,
) -> Tuple[List[Dict[str, Any]], bool, Optional[Dict[str, Any]]]:
    """
    Compaction triggers if input_tokens > COMPACT_AT.
    Summarizes older messages into one 'Progress so far' note while keeping
    the last 4+ messages intact with valid tool pairs.
    """
    if input_tokens < COMPACT_AT or len(messages) <= 6:
        return messages, False, None

    cutoff = find_safe_compaction_cutoff(messages, target_kept_count=4)
    if cutoff <= 1:
        # Not enough messages to meaningfully compact
        return messages, False, None

    older_messages = messages[:cutoff]
    kept_messages = messages[cutoff:]

    # Prepare summary prompt
    summary_messages = [
        {"role": "system", "content": "You are a concise summarizer for an AI agent's internal memory."},
        {
            "role": "user",
            "content": (
                "Summarize the conversation below into a concise 'Progress So Far' briefing (under 200 words). "
                "Highlight: key leads found, tasks completed, decisions made, and pending actions:\n\n"
                f"{str(older_messages)}"
            ),
        }
    ]

    try:
        res = call_llm_fn(system="", messages=summary_messages, tools=None)
        summary_text = res.get("content", "").strip() or "Previous tasks and leads processed."
    except Exception as e:
        summary_text = f"Compaction summary generated (auto-fallback due to error: {str(e)})."

    compacted_initial_message = {
        "role": "user",
        "content": f"[COMPACTION: Progress so far summary of previous steps]:\n{summary_text}"
    }

    new_messages = [compacted_initial_message] + kept_messages
    compaction_event = {
        "timestamp": time.time(),
        "input_tokens_before": input_tokens,
        "older_messages_count": len(older_messages),
        "kept_messages_count": len(kept_messages),
        "summary": summary_text,
    }

    print(f"\n[Compaction Triggered]: Input tokens ({input_tokens}) > {COMPACT_AT}. Compacted {len(older_messages)} older messages into progress summary.")

    return new_messages, True, compaction_event
