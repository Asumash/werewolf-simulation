from __future__ import annotations
import json
from pathlib import Path

files = sorted(Path("data").glob("game_*.jsonl"))

hit_total = 0
hit_village_win = 0
miss_total = 0
miss_village_win = 0
no_seer_total = 0
no_seer_village_win = 0

for path in files:
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]
    meta = next((r for r in records if r["type"] == "meta"), None)
    if not meta:
        continue

    winner = meta["result"]["winner"]
    village_win = winner == "village"

    # 本物の占い師が人狼を占ったか確認
    seer_hit = False
    seer_miss = False
    has_seer = False

    for s in statements:
        if s["true_role"] != "占い師":
            continue
        has_seer = True
        if "占い師です" in s["statement"] and "人狼でした" in s["statement"]:
            seer_hit = True
        elif "占い師です" in s["statement"] and ("村人でした" in s["statement"]
              or "占い師でした" in s["statement"] or "怪盗でした" in s["statement"]
              or "墓地を見ました" in s["statement"]):
            seer_miss = True

    if seer_hit:
        hit_total += 1
        if village_win:
            hit_village_win += 1
    elif seer_miss or has_seer:
        miss_total += 1
        if village_win:
            miss_village_win += 1
    else:
        no_seer_total += 1
        if village_win:
            no_seer_village_win += 1

print(f"総ゲーム数: {len(files)}")
print()
print(f"【占い師が人狼を占った（ヒット）】")
print(f"  ゲーム数: {hit_total} ({hit_total/len(files)*100:.1f}%)")
print(f"  村人勝利: {hit_village_win} ({hit_village_win/hit_total*100:.1f}%)")
print(f"  人狼勝利: {hit_total-hit_village_win} ({(hit_total-hit_village_win)/hit_total*100:.1f}%)")
print()
print(f"【占い師が人狼を占わなかった（ミス）】")
print(f"  ゲーム数: {miss_total} ({miss_total/len(files)*100:.1f}%)")
print(f"  村人勝利: {miss_village_win} ({miss_village_win/miss_total*100:.1f}%)")
print(f"  人狼勝利: {miss_total-miss_village_win} ({(miss_total-miss_village_win)/miss_total*100:.1f}%)")
print()
if no_seer_total > 0:
    print(f"【占い師がCOしなかった】")
    print(f"  ゲーム数: {no_seer_total} ({no_seer_total/len(files)*100:.1f}%)")
    print(f"  村人勝利: {no_seer_village_win} ({no_seer_village_win/no_seer_total*100:.1f}%)")
