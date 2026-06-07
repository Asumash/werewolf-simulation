"""
勝敗判定が正しく交換後の役職を見ているか検証する。
怪盗と人狼が交換したゲームを抽出し、
  - 処刑されたプレイヤーの「元の役職」と「交換後の役職」
  - 実際の勝敗
を並べて表示する。
"""
from __future__ import annotations
import json
from pathlib import Path

records_all = []
for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    meta = next(r for r in records if r["type"] == "meta")
    statements = [r for r in records if r["type"] == "statement"]
    votes = [r for r in records if r["type"] == "vote"]

    # 怪盗→人狼スワップが起きたゲームを検出
    # "元怪盗→人狼" または "人狼なので" を reasoning に持ち role が 怪盗 なプレイヤーを探す
    swap_occurred = any(
        "元怪盗→人狼" in r.get("reasoning", "")
        for r in statements
    )
    original_wolf_acts_as_wolf = any(
        "人狼なので" in r.get("reasoning", "") and r["role"] == "怪盗"
        for r in statements
    )
    if not (swap_occurred or original_wolf_acts_as_wolf):
        continue

    executed = meta["result"]["executed"]
    winner = meta["result"]["winner"]
    role_map_current = meta["role_map"]  # 交換後（recorder保存時点）

    # original_role は recorder に保存していないので knowledge から逆算
    # knowledge["swapped_with"] があるプレイヤーが怪盗側
    knowledge_map = {r["player_id"]: r["knowledge"] for r in statements
                     if r["type"] == "statement"}
    # 重複除去
    knowledge_map = {}
    for r in statements:
        knowledge_map.setdefault(r["player_id"], r["knowledge"])

    print(f"=== {path.name} ===")
    print(f"交換後 role_map: {role_map_current}")
    print(f"処刑: {executed}  →  勝者: {winner}")
    for pid in executed:
        current_role = role_map_current[pid]
        k = knowledge_map.get(pid, {})
        swapped_with = k.get("swapped_with")
        new_role = k.get("new_role")
        if swapped_with:
            print(f"  {pid}: 怪盗として{swapped_with}と交換 → 現在{new_role}")
        else:
            # 元人狼の可能性: any statement with role!=人狼 but reasoning like 人狼
            acts_as_wolf = any(
                "人狼なので" in r.get("reasoning", "")
                for r in statements if r["player_id"] == pid
            )
            print(f"  {pid}: current_role={current_role}"
                  + (" ← 人狼として行動（元人狼、交換されたことを知らない）" if acts_as_wolf else ""))

    # 検証: 処刑プレイヤーに現在WEREWOLFがいれば village が正解
    wolf_executed = any(role_map_current.get(p) == "人狼" for p in executed)
    expected = "village" if wolf_executed else "werewolf"
    ok = "✓" if expected == winner else "✗ BUG"
    print(f"  wolf_executed={wolf_executed} → expected={expected}, actual={winner} {ok}")
    print()
    records_all.append(ok)
    if len(records_all) >= 10:
        break

bugs = [r for r in records_all if "BUG" in r]
print(f"検査件数: {len(records_all)}, バグ: {len(bugs)}")
