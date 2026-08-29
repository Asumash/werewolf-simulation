from __future__ import annotations
import json
from pathlib import Path

files = sorted(Path("data").glob("game_*.jsonl"))[-1000:]

p3_count = 0
p3_wolf_win = 0

for path in files:
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]
    meta = next((r for r in records if r["type"] == "meta"), None)
    if not meta:
        continue

    has_p3 = any("どちらかが人狼" in s["statement"] or
                 ("本物の占い師なら" in s["statement"] and "人狼です" in s["statement"])
                 for s in statements)

    if has_p3:
        p3_count += 1
        if meta["result"]["winner"] == "werewolf":
            p3_wolf_win += 1

print(f"パターン3（どちらかが人狼）発生: {p3_count}/1000 ({p3_count/10:.1f}%)")
if p3_count > 0:
    vw = p3_count - p3_wolf_win
    print(f"  村人勝利: {vw} ({vw/p3_count*100:.1f}%)")
    print(f"  人狼勝利: {p3_wolf_win} ({p3_wolf_win/p3_count*100:.1f}%)")
