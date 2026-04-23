import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)


class SettingsStore:
    """Persistent per-(plugin_uuid, context) settings storage.

    Backed by a JSON file on disk. Concurrent writes are serialized by a lock.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, dict]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            with self.path.open() as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._data = raw
        except Exception as e:
            log.warning("failed to load settings store %s: %s", self.path, e)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w") as f:
            json.dump(self._data, f, indent=2)
        tmp.replace(self.path)

    def get(self, plugin_uuid: str, context_token: str) -> dict:
        with self._lock:
            return dict(self._data.get(plugin_uuid, {}).get(context_token, {}))

    def set(self, plugin_uuid: str, context_token: str, settings: dict) -> None:
        with self._lock:
            self._data.setdefault(plugin_uuid, {})[context_token] = dict(settings or {})
            try:
                self._save()
            except OSError as e:
                log.warning("failed to persist settings to %s: %s", self.path, e)
