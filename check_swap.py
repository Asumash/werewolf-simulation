from __future__ import annotations
import json
from pathlib import Path

found = 0
for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    meta = next(r for r in records if r["type"] == "meta")
    statements = [r for r in records if r["type"] == "statement"]

    # 怪盗→人狼スワップが起きたゲームを検出
    swap_case = any(
        "元怪盗→人狼" in r.get("reasoning", "")
        for r in statements
    )
    if not swap_case:
        continue

    found += 1
    print(f"=== {path.name} ===")
    print(f"役職配布: {meta['role_map']}")
    print("--- 発言ログ ---")
    for s in statements:
        lie = " [嘘]" if s["is_lie"] else ""
        print(f"  {s['player_id']}({s['role']}){lie}: {s['statement']}")
        if s.get("reasoning"):
            print(f"    ↳ reasoning: {s['reasoning']}")
    votes = [r for r in records if r["type"] == "vote"]
    print("--- 投票 ---")
    for v in votes:
        print(f"  {v['voter']}({v['voter_role']}) → {v['target']}")
    print(f"結果: {meta['result']}")
    print()
    if found >= 3:
        break

if found == 0:
    print("怪盗→人狼スワップのゲームが見つかりませんでした（データ数を増やしてください）")
