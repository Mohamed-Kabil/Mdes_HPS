"""
env_store.py — reads/writes mc_divergence/.env for the Parametres page.
Preserves comments and layout: only the matched KEY=... lines are rewritten,
everything else (comments, blank lines) passes through untouched. Keys not
already present in the file are appended at the end.

mc_divergence/.env is gitignored (real secrets) -- this only ever touches
the local file, never anything checked into version control.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), "mc_divergence", ".env")


def read_env():
    values = {}
    if not os.path.exists(ENV_PATH):
        return values
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(updates):
    """updates: {key: value}. A value of None (or missing from updates)
    leaves that key's existing line untouched -- used so the password field
    can be left blank in the form without wiping the saved one."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.readlines()

    seen = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates and updates[key] is not None:
                out.append(f"{key}={updates[key]}\n")
                seen.add(key)
                continue
        out.append(line)

    for key, value in updates.items():
        if key not in seen and value is not None:
            out.append(f"{key}={value}\n")

    os.makedirs(os.path.dirname(ENV_PATH), exist_ok=True)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(out)
