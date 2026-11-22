"""Repository locations used across the package. Every path is absolute, so commands work from any directory."""
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(REPO, "data")             # manifest paths are relative to this directory
CASES = os.path.join(DATA, "cases")           # one folder per case: manifest, case_input, profile, variants, meta
GOLD = os.path.join(DATA, "gold")
CONFIG = os.path.join(REPO, "config")
PROMPTS = os.path.join(REPO, "prompts")
SCHEMAS = os.path.join(REPO, "schemas")
CACHE = os.path.join(REPO, ".cache")


def gold_file() -> str:
    """The detailed local gold labels when present (gitignored), otherwise the public label-only file."""
    local = os.path.join(GOLD, "groups.local.json")
    return local if os.path.exists(local) else os.path.join(GOLD, "groups.json")
