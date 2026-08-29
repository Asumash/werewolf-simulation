from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

p1_count = 0  # 偽の占い師
p2_count = 0  # 偽の怪盗
games_with_expose = 0
total_games = 0

for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]
    total_games += 1

    has_p1 = any("偽の占い師" in s["statement"] for s in statements)
    has_p2 = any("偽の怪盗" in s["statement"] for s in statements)

    if has_p1:
        p1_count += 1
    if has_p2:
        p2_count += 1
    if has_p1 or has_p2:
        games_with_expose += 1

print(f"総ゲーム数: {total_games}")
print(f"矛盾指摘あり: {games_with_expose} ({games_with_expose/total_games*100:.1f}%)")
print(f"  パターン1（偽の占い師）: {p1_count} ({p1_count/total_games*100:.1f}%)")
print(f"  パターン2（偽の怪盗）  : {p2_count} ({p2_count/total_games*100:.1f}%)")

# サンプル表示
print("\n--- パターン1 サンプル ---")
shown = 0
for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    for r in records:
        if r["type"] == "statement" and "偽の占い師" in r["statement"]:
            print(f"  {r['player_id']}: {r['statement']}")
            shown += 1
            break
    if shown >= 2:
        break

print("\n--- パターン2 サンプル ---")
shown = 0
for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    for r in records:
        if r["type"] == "statement" and "偽の怪盗" in r["statement"]:
            print(f"  {r['player_id']}: {r['statement']}")
            shown += 1
            break
    if shown >= 2:
        break
