"""
conclave.cli.config
────────────────────
Persists per-user CLI configuration to ~/.conclave_config (JSON).

Currently manages:
  - server_url: the Conclave Server to connect to
"""

import os
import json

CONFIG_FILE = os.path.expanduser("~/.conclave_config")

_DEFAULTS = {
    "server_url": "http://127.0.0.1:8000",
}


def _load() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def _save(data: dict) -> None:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_server_url() -> str:
    """Return the configured server URL (with any trailing slash removed)."""
    env_url = os.getenv("CONCLAVE_SERVER_URL")
    if env_url:
        return env_url.rstrip("/")
    return _load().get("server_url", _DEFAULTS["server_url"]).rstrip("/")


def save_server_url(url: str) -> None:
    """Persist a new server URL to the config file."""
    data = _load()
    data["server_url"] = url.rstrip("/")
    _save(data)


def get_config() -> dict:
    """Return the full config dict."""
    return _load()
