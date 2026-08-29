from __future__ import annotations
import json
from pathlib import Path

total = 0
wolf_wins = 0
village_wins = 0

for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]
    meta = next((r for r in records if r["type"] == "meta"), None)
    if not meta:
        continue

    # 人狼が占いCOで誰かを「人狼」と判定した発言があるか
    has_wolf_accuse = any(
        s["true_role"] == "人狼"
        and "占い師です" in s["statement"]
        and "人狼でした" in s["statement"]
        for s in statements
    )

    if has_wolf_accuse:
        total += 1
        if meta["result"]["winner"] == "werewolf":
            wolf_wins += 1
        else:
            village_wins += 1

print(f"人狼が誰かを人狼と判定したゲーム数: {total}")
if total > 0:
    print(f"  人狼勝利: {wolf_wins} ({wolf_wins/total*100:.1f}%)")
    print(f"  村人勝利: {village_wins} ({village_wins/total*100:.1f}%)")
