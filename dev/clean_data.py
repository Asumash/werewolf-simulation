from __future__ import annotations
import os
import glob

files = glob.glob("data/game_*.jsonl")
for f in files:
    os.remove(f)
print(f"{len(files)}件削除完了")
