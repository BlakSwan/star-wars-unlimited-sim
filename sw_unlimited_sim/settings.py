"""Local settings loader for secrets and simulator options."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ENV_PATH = PROJECT_ROOT / ".env"


def load_local_env(path: str | Path = LOCAL_ENV_PATH):
    """Load KEY=VALUE pairs from a local .env file without overriding env vars."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_setting(name: str, default: str | None = None) -> str | None:
    load_local_env()
    return os.environ.get(name, default)
