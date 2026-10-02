import os
import sys
import glob

# Auto-add local venv site-packages if running with system python
_venv_pkgs = glob.glob(os.path.join(os.path.dirname(__file__), ".venv/lib/python*/site-packages"))
if _venv_pkgs and _venv_pkgs[0] not in sys.path:
    sys.path.insert(0, _venv_pkgs[0])


def load_env(env_path: str = ".env") -> None:
    """Load key-value pairs from .env into os.environ if not already set."""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
            elif ":" in line:
                k, v = line.split(":", 1)
            else:
                continue
            key = k.strip()
            val = v.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = val


load_env()

# Core Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
EXA_API_KEY = os.getenv("EXA_API_KEY", "")

# Model settings
MODEL_NAME = "deepseek/deepseek-v4.1-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
EXA_SEARCH_URL = "https://api.exa.ai/search"
EXA_CONTENTS_URL = "https://api.exa.ai/contents"

# Cost estimation defaults for deepseek/deepseek-v4.1-flash (per 1M tokens)
# DeepSeek Flash typically ~$0.14/1M prompt, $0.28/1M completion
PRICE_PER_M_INPUT = 0.14
PRICE_PER_M_OUTPUT = 0.28

# Agent limits and thresholds
CONTEXT_BUDGET = 8000
COMPACT_AT = 6000  # 75% of context budget
OFFLOAD_OVER = 2000  # characters
MAX_STEPS = 40
COST_CAP_USD = 1.00
LOOKBACK_DAYS = 7

# Paths
DB_PATH = "scout.db"
WORKSPACE_DIR = "workspace"
RUNS_DIR = "runs"
DATA_DIR = "data"
EVAL_SET_PATH = os.path.join(DATA_DIR, "eval_set.json")
