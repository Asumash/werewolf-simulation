from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

# 最新1000ゲームのみ対象
files = sorted(Path("data").glob("game_*.jsonl"))[-1000:]
print(f"分析対象: {len(files)}ゲーム（最新）")

wins = {"village": 0, "werewolf": 0}
executed_roles = defaultdict(int)
vote_correct = defaultdict(lambda: [0, 0])  # [正解, 総投票]
wolf_accuse_total = 0
wolf_accuse_wolf_win = 0

for path in files:
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]
    votes = [r for r in records if r["type"] == "vote"]
    meta = next((r for r in records if r["type"] == "meta"), None)
    if not meta:
        continue

    winner = meta["result"]["winner"]
    wins[winner] += 1

    # 処刑役職
    for pid in meta["result"].get("executed", []):
        role = meta["role_map"].get(pid, "不明")
        executed_roles[role] += 1

    # 投票精度
    wolf_pids = [p for p, r in meta["role_map"].items() if r == "人狼"]
    for v in votes:
        role = v.get("voter_role", "不明")
        vote_correct[role][1] += 1
        if v["target"] in wolf_pids:
            vote_correct[role][0] += 1

    # 人狼が人狼判定した場合
    has_wolf_accuse = any(
        s["true_role"] == "人狼"
        and "占い師です" in s["statement"]
        and "人狼でした" in s["statement"]
        for s in statements
    )
    if has_wolf_accuse:
        wolf_accuse_total += 1
        if winner == "werewolf":
            wolf_accuse_wolf_win += 1

total = len(files)
print(f"\n【勝率】")
print(f"  村人勝利: {wins['village']} ({wins['village']/total*100:.1f}%)")
print(f"  人狼勝利: {wins['werewolf']} ({wins['werewolf']/total*100:.1f}%)")

print(f"\n【処刑結果】")
for role, cnt in sorted(executed_roles.items(), key=lambda x: -x[1]):
    print(f"  {role}: {cnt}回")

print(f"\n【投票精度】")
for role, (correct, total_v) in sorted(vote_correct.items(), key=lambda x: -x[1][0]/max(x[1][1],1)):
    if total_v > 0:
        print(f"  {role}: {correct}/{total_v} ({correct/total_v*100:.1f}%)")

print(f"\n【人狼が偽占いで人狼判定したゲーム】")
if wolf_accuse_total > 0:
    print(f"  該当ゲーム: {wolf_accuse_total} ({wolf_accuse_total/total*100:.1f}%)")
    print(f"  人狼勝利: {wolf_accuse_wolf_win} ({wolf_accuse_wolf_win/wolf_accuse_total*100:.1f}%)")
    print(f"  村人勝利: {wolf_accuse_total - wolf_accuse_wolf_win} ({(wolf_accuse_total-wolf_accuse_wolf_win)/wolf_accuse_total*100:.1f}%)")
