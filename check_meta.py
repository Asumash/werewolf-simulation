from __future__ import annotations
import json
from pathlib import Path

path = sorted(Path("data").glob("game_*.jsonl"))[0]
records = [json.loads(l) for l in open(path, encoding="utf-8")]
for r in records:
    if r["type"] == "meta":
        print(r)
        break
