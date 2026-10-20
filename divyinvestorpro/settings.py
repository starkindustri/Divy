"""User settings, stored as JSON in the app's data folder (never in the project)."""
import json
import os

from .portfolio import data_dir


def path():
    return data_dir() / "settings.json"


def load() -> dict:
    try:
        return json.loads(path().read_text())
    except (OSError, ValueError):
        return {}


def save(values: dict) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(values, indent=2))
    try:
        os.chmod(p, 0o600)  # holds an API key: owner-only on Mac/Linux
    except OSError:
        pass


def massive_key() -> str:
    """Massive API key from Settings, or the MASSIVE_API_KEY environment variable."""
    return (load().get("massive_api_key") or os.environ.get("MASSIVE_API_KEY", "")).strip()
