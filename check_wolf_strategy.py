from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

# 最新1000ゲームのみ対象
files = sorted(Path("data").glob("game_*.jsonl"))[-1000:]

results = {
    "seer":    {"total": 0, "wolf_win": 0},
    "robber":  {"total": 0, "wolf_win": 0},
    "villager":{"total": 0, "wolf_win": 0},
    "mixed":   {"total": 0, "wolf_win": 0},  # 2人の人狼が異なる戦略
}

for path in files:
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]
    meta = next((r for r in records if r["type"] == "meta"), None)
    if not meta:
        continue

    winner = meta["result"]["winner"]
    wolf_pids = [p for p, r in meta["role_map"].items() if r == "人狼"]

    # 各人狼の戦略を判定
    wolf_strategies = {}
    for pid in wolf_pids:
        stmts = [s["statement"] for s in statements if s["player_id"] == pid]
        strategy = "villager"  # デフォルト
        for s in stmts:
            if "占い師です" in s or "私は占い師" in s:
                strategy = "seer"
                break
            if "怪盗です" in s and "交換しました" in s:
                strategy = "robber"
                break
        wolf_strategies[pid] = strategy

    # ゲーム全体の戦略を分類
    strats = set(wolf_strategies.values())
    if len(strats) == 1:
        key = list(strats)[0]
    else:
        key = "mixed"

    results[key]["total"] += 1
    if winner == "werewolf":
        results[key]["wolf_win"] += 1

print(f"人狼の偽装戦略ごとの勝率（最新1000ゲーム）\n")
print(f"{'戦略':12} {'ゲーム数':>8} {'人狼勝利':>8} {'人狼勝率':>8} {'村人勝率':>8}")
print("─" * 52)
labels = {
    "seer":     "占い師偽装",
    "robber":   "怪盗偽装",
    "villager": "村人潜伏",
    "mixed":    "混合戦略",
}
for key in ["seer", "robber", "villager", "mixed"]:
    d = results[key]
    t = d["total"]
    w = d["wolf_win"]
    if t == 0:
        continue
    wolf_rate = w / t * 100
    village_rate = (t - w) / t * 100
    print(f"{labels[key]:12} {t:>8} {w:>8} {wolf_rate:>7.1f}% {village_rate:>7.1f}%")
