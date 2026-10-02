import bootstrap
import os
import json
import time
from typing import Dict, Any, List, Optional
from config import RUNS_DIR


class TraceLogger:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.run_dir = os.path.join(RUNS_DIR, run_id)
        os.makedirs(self.run_dir, exist_ok=True)
        self.trace_file = os.path.join(self.run_dir, "trace.jsonl")
        
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.step_count = 0

    def log_step(
        self,
        step: int,
        llm_response: Dict[str, Any],
        tool_executions: List[Dict[str, Any]],
        compactions: Optional[List[Dict[str, Any]]] = None,
        offloads: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        usage = llm_response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        cost = llm_response.get("cost", 0.0)

        self.step_count = step
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += tokens
        self.total_cost += cost

        record = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "step": step,
            "llm_content": (llm_response.get("content") or "")[:200],
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "step_total": tokens,
                "cumulative_total": self.total_tokens,
            },
            "cost": {
                "step_cost": round(cost, 6),
                "cumulative_cost": round(self.total_cost, 6),
            },
            "tool_calls": [
                {
                    "name": tc.get("name"),
                    "args": tc.get("args"),
                    "is_error": tc.get("is_error", False),
                    "result_preview": str(tc.get("result", ""))[:200],
                }
                for tc in tool_executions
            ],
            "compactions": compactions or [],
            "offloads": offloads or [],
        }

        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        record = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event_type,
            "data": data,
        }
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def print_summary(self) -> None:
        print("\n" + "=" * 50)
        print(f"Run {self.run_id} Finished")
        print(f"Total Steps: {self.step_count}")
        print(f"Total Tokens: {self.total_tokens} (Prompt: {self.total_prompt_tokens}, Completion: {self.total_completion_tokens})")
        print(f"Total Cost: ${self.total_cost:.6f}")
        print(f"Trace saved to: {self.trace_file}")
        print("=" * 50 + "\n")
