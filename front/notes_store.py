"""
notes_store.py — free-form per-endpoint notes (networks/_notes.html), a
feature the old dashboard didn't have at all. JSON-file backed, one file
per network so predig/mdescs notes never collide.

Shape on disk: {endpoint_name: [{"texte": str, "auteur": str, "date": str}, ...]}
"""

import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _path(network_key):
    return os.path.join(DATA_DIR, f"notes_{network_key}.json")


def load_notes(network_key):
    path = _path(network_key)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def add_note(network_key, endpoint_name, texte, auteur):
    notes = load_notes(network_key)
    notes.setdefault(endpoint_name, []).append({
        "texte": texte, "auteur": auteur or None,
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    with open(_path(network_key), "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)
