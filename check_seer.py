"""占い師の夜行動の実態を集計する。"""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

saw_player = 0
saw_graveyard = 0
no_result = 0

for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    for r in records:
        if r["type"] != "statement":
            continue
        if r["role"] != "占い師":
            continue
        k = r["knowledge"]
        if "saw_player" in k:
            saw_player += 1
            break
        elif "saw_graveyard" in k:
            saw_graveyard += 1
            break
        else:
            no_result += 1
            break   # 1ゲームにつき1人の占い師を対象

total = saw_player + saw_graveyard + no_result
print(f"占い師の夜行動（ゲーム単位）:")
print(f"  人を占った    : {saw_player:4} ({saw_player/total*100:.1f}%)")
print(f"  墓地を見た    : {saw_graveyard:4} ({saw_graveyard/total*100:.1f}%)")
print(f"  占い師が墓地行き: {no_result:4} ({no_result/total*100:.1f}%)")
print(f"  合計          : {total}")

# 墓地を見た発言サンプル
print("\n--- 墓地情報のCO発言サンプル ---")
found = 0
for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    for r in records:
        if r["type"] == "statement" and "saw_graveyard" in r["knowledge"]:
            print(f"  {r['player_id']}({r['role']}): {r['statement']}")
            found += 1
            if found >= 5:
                break
    if found >= 5:
        break
