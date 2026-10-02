import bootstrap
import json
import httpx
import os
from typing import Optional, List, Dict, Any
from config import OPENROUTER_API_KEY, OPENROUTER_URL, MODEL_NAME, PRICE_PER_M_INPUT, PRICE_PER_M_OUTPUT


def call_llm(
    system: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """
    Calls the OpenRouter chat completions API using plain httpx (no SDKs).
    Uses model: deepseek/deepseek-v4.1-flash.
    Returns parsed reply, tool_calls, usage, and cost.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set. Check your .env file.")

    formatted_messages = []
    if system:
        formatted_messages.append({"role": "system", "content": system})
    formatted_messages.extend(messages)

    payload: Dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": formatted_messages,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(OPENROUTER_URL, headers=headers, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"OpenRouter API error {response.status_code}: {response.text}")

        data = response.json()

    choice = data["choices"][0]
    msg = choice["message"]
    content = msg.get("content") or ""
    raw_tool_calls = msg.get("tool_calls") or []

    # Parse tool calls into a standardized format
    parsed_tool_calls = []
    for tc in raw_tool_calls:
        func = tc.get("function", {})
        func_name = func.get("name", "")
        args_raw = func.get("arguments", "{}")
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except Exception:
                args = {"raw": args_raw}
        else:
            args = args_raw

        parsed_tool_calls.append({
            "id": tc.get("id"),
            "name": func_name,
            "arguments": args,
        })

    usage_data = data.get("usage", {})
    prompt_tokens = usage_data.get("prompt_tokens", 0)
    completion_tokens = usage_data.get("completion_tokens", 0)
    total_tokens = usage_data.get("total_tokens", prompt_tokens + completion_tokens)

    # Use cost returned by OpenRouter or fallback to token-based calculation
    reported_cost = usage_data.get("cost")
    if reported_cost is not None and isinstance(reported_cost, (int, float)):
        cost = float(reported_cost)
    else:
        cost = (prompt_tokens / 1_000_000 * PRICE_PER_M_INPUT) + (completion_tokens / 1_000_000 * PRICE_PER_M_OUTPUT)

    # Print reply text and token usage as required by Day 1 specifications
    if content:
        print(f"\n[LLM Response]: {content.strip()}")
    if parsed_tool_calls:
        print(f"[LLM Tool Calls]: {[tc['name'] for tc in parsed_tool_calls]}")
    print(f"[Tokens]: in={prompt_tokens}, out={completion_tokens}, total={total_tokens} | Cost: ${cost:.6f}")

    return {
        "content": content,
        "tool_calls": parsed_tool_calls,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "cost": cost,
        "raw_message": msg,
    }


if __name__ == "__main__":
    test_res = call_llm(
        system="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Say hello in 3 words."}],
    )
    print("Test Output:", test_res["content"])
