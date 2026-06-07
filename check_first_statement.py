from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

# 役職ごとの「初発言が何番目の発言か」を集計
first_turn: dict[str, list[int]] = defaultdict(list)

for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]

    # ゲーム内で各プレイヤーが初めて発言した順番を記録
    seen = {}
    for i, s in enumerate(statements, start=1):
        pid = s["player_id"]
        if pid not in seen:
            seen[pid] = i
            first_turn[s["role"]].append(i)

ROLES = ["占い師", "怪盗", "人狼", "村人"]
print(f"{'役職':8} {'平均':>5} {'中央':>5}  分布（発言番号ごとの割合）")
print("─" * 70)
for role in ROLES:
    turns = first_turn[role]
    if not turns:
        continue
    avg = sum(turns) / len(turns)
    sorted_t = sorted(turns)
    med = sorted_t[len(sorted_t) // 2]

    # 分布（1〜15番目）
    dist = defaultdict(int)
    for t in turns:
        dist[t] += 1
    total = len(turns)

    bars = ""
    for n in range(1, 16):
        pct = dist[n] / total * 100
        if pct >= 1:
            bars += f"{n}:{pct:.0f}% "

    print(f"{role:8} {avg:5.1f} {med:5}  {bars}")
