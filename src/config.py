import json
from pathlib import Path
import os
import sys
from typing import Dict, Any


def load_config(use_live: bool = False, config_dir: str = "config") -> Dict[str, Any]:
    """
    Load either config.dev.json or config.live.json depending on `use_live`.
    Both config files should be fully populated (no merging behavior).
    """

    base_dir = Path(__file__).parent.parent  # Go up from src/ to project root
    filename = base_dir / ("config.live.json" if use_live else "config.dev.json")

    if not filename.exists():
        raise FileNotFoundError(f"Configuration file not found: {filename}")

    with open(filename, "r") as f:
        cfg = json.load(f)

    # Minimal validation
    if "accounts" not in cfg:
        raise KeyError("Config missing 'accounts' section")
    if "mt5" not in cfg:
        raise KeyError("Config missing 'mt5' section")
    if "server" not in cfg:
        # Provide a safe default if missing
        cfg.setdefault("server", {"host": "127.0.0.1", "port": 5100})
    return cfg


def detect_live_flag(argv=None) -> bool:
    """
    Simple detection of --live flag from CLI args.
    """
    if argv is None:
        argv = sys.argv[1:]
    return "--live" in argv or "-l" in argv
