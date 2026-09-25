import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional


class EntityMemory:
    """
    Persistent JSON-backed memory for objects and their last known locations.
    Thread-safe for concurrent access from the agent thread pool.

    File schema (~/.omnibot/entity_memory.json):
    {
      "objects": {
        "red_cup": {
          "last_seen_location": "kitchen",
          "last_seen_time": "2026-04-18T10:23:00",
          "description": "A red ceramic coffee cup on the counter"
        }
      },
      "location_annotations": {
        "kitchen": {
          "objects_present": ["red_cup", "coffee_maker"],
          "last_visited": "2026-04-18T10:22:00"
        }
      }
    }
    """

    def __init__(self, path: str):
        self._path = os.path.expanduser(path)
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {"objects": {}, "location_annotations": {}}
        self._load()

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self._data = loaded
            except (json.JSONDecodeError, IOError):
                pass  # Start fresh on file corruption

    def _save(self) -> None:
        # Must be called inside self._lock
        tmp = self._path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self._path)  # Atomic write

    def remember_object(
        self, object_name: str, location: str, description: str = ""
    ) -> None:
        with self._lock:
            self._data["objects"][object_name] = {
                "last_seen_location": location,
                "last_seen_time": datetime.now().isoformat(),
                "description": description,
            }
            loc_data = self._data["location_annotations"].setdefault(location, {})
            objects_list: List[str] = loc_data.setdefault("objects_present", [])
            if object_name not in objects_list:
                objects_list.append(object_name)
            loc_data["last_visited"] = datetime.now().isoformat()
            self._save()

    def recall_object(self, object_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data["objects"].get(object_name)

    def get_objects_at_location(self, location: str) -> List[str]:
        with self._lock:
            loc_data = self._data["location_annotations"].get(location, {})
            return loc_data.get("objects_present", [])

    def get_summary(self) -> str:
        with self._lock:
            if not self._data["objects"]:
                return "No objects remembered yet."
            lines = []
            for obj, data in self._data["objects"].items():
                ts = data.get("last_seen_time", "")[:10]
                loc = data.get("last_seen_location", "unknown")
                desc = data.get("description", "")
                line = f"- {obj}: last seen at {loc} ({ts})"
                if desc:
                    line += f" — {desc}"
                lines.append(line)
            return "\n".join(lines)

    def clear(self) -> None:
        with self._lock:
            self._data = {"objects": {}, "location_annotations": {}}
            self._save()
