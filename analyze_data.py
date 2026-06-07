"""生成データの統計分析。"""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

games = []
statements_all = []
votes_all = []

for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    meta   = next(r for r in records if r["type"] == "meta")
    stmts  = [r for r in records if r["type"] == "statement"]
    votes  = [r for r in records if r["type"] == "vote"]
    games.append(meta)
    statements_all.extend(stmts)
    votes_all.extend(votes)

n = len(games)

# ── 勝敗 ──
wins = defaultdict(int)
for g in games:
    wins[g["result"]["winner"]] += 1

# ── 処刑結果 ──
executed_roles = defaultdict(int)   # 処刑された true_role の集計
no_exec = 0
for g in games:
    ex = g["result"]["executed"]
    if not ex:
        no_exec += 1
    for pid in ex:
        executed_roles[g["role_map"][pid]] += 1

# ── スワップ発生率 ──
swap_wolf   = 0   # 怪盗が人狼と交換
swap_other  = 0   # 怪盗がそれ以外と交換（必ず発生するはずだが念のため）
for g in games:
    orig = g["original_role_map"]
    curr = g["role_map"]
    # 怪盗プレイヤーを特定（配布時に怪盗だった人）
    robber_pid = next((p for p, r in orig.items() if r == "怪盗"), None)
    if robber_pid:
        # 交換後に人狼になっていれば wolf swap
        if curr[robber_pid] == "人狼":
            swap_wolf += 1
        else:
            swap_other += 1

# ── 役職別発言数・嘘発言数 ──
role_stmts = defaultdict(int)
role_lies  = defaultdict(int)
for s in statements_all:
    role_stmts[s["role"]] += 1
    if s["is_lie"]:
        role_lies[s["role"]] += 1

# ── 役職別投票先（village視点での正解率） ──
# 「投票先が真の人狼だったか」を集計
correct_votes = defaultdict(int)
total_votes   = defaultdict(int)
for v in votes_all:
    vr = v["voter_role"]
    total_votes[vr] += 1
    # 投票先の true_role を取得
    # votes_all には game_id があるので meta から role_map を引く
for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    meta  = next(r for r in records if r["type"] == "meta")
    for v in (r for r in records if r["type"] == "vote"):
        target_true_role = meta["role_map"].get(v["target"], "不明")
        if target_true_role == "人狼":
            correct_votes[v["voter_role"]] += 1

# ── 発言数分布 ──
stmt_counts = defaultdict(int)
for g in games:
    game_stmts = [s for s in statements_all if s["game_id"] == g["game_id"]]
    stmt_counts[len(game_stmts)] += 1

# ── 矛盾指摘発生ゲーム数 ──
EXPOSE_SIGNALS = (
    "断言します", "矛盾しています",
    "投票を勧めます", "投票を検討", "どちらかが偽装", "嘘をついていると思います",
    "食い違っています",
)
expose_games = sum(
    1 for g in games
    if any(any(sig in s["statement"] for sig in EXPOSE_SIGNALS)
           for s in statements_all if s["game_id"] == g["game_id"])
)

# ── 表示 ──
SEP = "─" * 52

print(SEP)
print(f"  分析対象: {n} ゲーム / {len(statements_all)} 発言 / {len(votes_all)} 票")
print(SEP)

print("\n【勝敗】")
print(f"  村人陣営  : {wins['village']:4} 勝  ({wins['village']/n*100:.1f}%)")
print(f"  人狼陣営  : {wins['werewolf']:4} 勝  ({wins['werewolf']/n*100:.1f}%)")

print("\n【処刑結果】")
print(f"  処刑なし（全票バラバラ）: {no_exec} ゲーム ({no_exec/n*100:.1f}%)")
for role, cnt in sorted(executed_roles.items(), key=lambda x: -x[1]):
    print(f"  {role:6} が処刑された   : {cnt:4} 回")

print("\n【怪盗スワップ】")
print(f"  人狼と交換  : {swap_wolf:4} ゲーム ({swap_wolf/n*100:.1f}%)")
print(f"  それ以外と交換: {swap_other:4} ゲーム ({swap_other/n*100:.1f}%)")

print("\n【役職別 発言数 / 嘘発言数 / 嘘率】")
for role in ["人狼", "占い師", "怪盗", "村人"]:
    s = role_stmts[role]
    l = role_lies[role]
    pct = l / s * 100 if s else 0
    print(f"  {role:5}: {s:5} 発言 / {l:4} 嘘 ({pct:5.1f}%)")

print("\n【役職別 投票精度（投票先が真の人狼だった割合）】")
for role in ["村人", "占い師", "怪盗", "人狼"]:
    t = total_votes[role]
    c = correct_votes[role]
    pct = c / t * 100 if t else 0
    print(f"  {role:5}: {c:4}/{t:4} ({pct:5.1f}%)")

print("\n【確定情報の指摘が発生したゲーム数】")
print(f"  {expose_games} / {n} ゲーム ({expose_games/n*100:.1f}%)")

print("\n【発言数の分布（ゲームあたり）】")
for cnt in sorted(stmt_counts):
    bar = "█" * (stmt_counts[cnt] // 5)
    print(f"  {cnt:3} 発言: {stmt_counts[cnt]:4} ゲーム {bar}")

print(SEP)
