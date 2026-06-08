from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

files = sorted(Path("data").glob("game_*.jsonl"))[-1000:]

# 占い師偽装: 判定内容別
seer_detail = {
    "人狼と判定":     {"total": 0, "wolf_win": 0},
    "村人と判定":     {"total": 0, "wolf_win": 0},
    "判定なし":       {"total": 0, "wolf_win": 0},
}
# 怪盗偽装: 交換後の偽役職別
robber_detail = {
    "村人になった":   {"total": 0, "wolf_win": 0},
    "占い師になった": {"total": 0, "wolf_win": 0},
    "その他":         {"total": 0, "wolf_win": 0},
}
# 村人潜伏: 疑惑の向け先（仲間を疑う / 非仲間を疑う）
villager_detail = {
    "非仲間を疑う":   {"total": 0, "wolf_win": 0},
    "仲間を疑う":     {"total": 0, "wolf_win": 0},
    "疑惑発言なし":   {"total": 0, "wolf_win": 0},
}

for path in files:
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]
    meta = next((r for r in records if r["type"] == "meta"), None)
    if not meta:
        continue

    winner = meta["result"]["winner"]
    wolf_win = winner == "werewolf"
    wolf_pids = [p for p, r in meta["role_map"].items() if r == "人狼"]

    for pid in wolf_pids:
        wolf_stmts = [s["statement"] for s in statements if s["player_id"] == pid]

        # 戦略判定
        strategy = "villager"
        for s in wolf_stmts:
            if "占い師です" in s or "私は占い師" in s:
                strategy = "seer"
                break
            if "怪盗です" in s and "交換しました" in s:
                strategy = "robber"
                break

        # ── 占い師偽装の詳細 ──
        if strategy == "seer":
            key = "判定なし"
            for s in wolf_stmts:
                if "人狼でした" in s:
                    key = "人狼と判定"
                    break
                if "村人でした" in s or "占い師でした" in s or "怪盗でした" in s:
                    key = "村人と判定"
                    break
            seer_detail[key]["total"] += 1
            if wolf_win:
                seer_detail[key]["wolf_win"] += 1

        # ── 怪盗偽装の詳細 ──
        elif strategy == "robber":
            key = "その他"
            for s in wolf_stmts:
                if "今村人" in s or "村人です" in s:
                    key = "村人になった"
                    break
                if "今占い師" in s or "占い師です" in s:
                    key = "占い師になった"
                    break
            robber_detail[key]["total"] += 1
            if wolf_win:
                robber_detail[key]["wolf_win"] += 1

        # ── 村人潜伏の詳細 ──
        else:
            key = "疑惑発言なし"
            accused_pids = set()
            for s in wolf_stmts:
                for other in meta["role_map"]:
                    if other == pid:
                        continue
                    if f"{other}さんが怪しい" in s or f"{other}が怪しい" in s \
                            or f"{other}さんの発言が" in s or f"{other}は人狼" in s \
                            or f"{other}さんが一番" in s:
                        accused_pids.add(other)

            if accused_pids:
                # 仲間を疑ったか
                accused_ally = any(p in wolf_pids for p in accused_pids)
                key = "仲間を疑う" if accused_ally else "非仲間を疑う"

            villager_detail[key]["total"] += 1
            if wolf_win:
                villager_detail[key]["wolf_win"] += 1


def print_table(title, data):
    print(f"\n【{title}】")
    print(f"{'内容':16} {'ゲーム数':>8} {'人狼勝利':>8} {'人狼勝率':>8} {'村人勝率':>8}")
    print("─" * 56)
    for key, d in data.items():
        t = d["total"]
        w = d["wolf_win"]
        if t == 0:
            continue
        print(f"{key:16} {t:>8} {w:>8} {w/t*100:>7.1f}% {(t-w)/t*100:>7.1f}%")

print_table("占い師偽装：判定内容別", seer_detail)
print_table("怪盗偽装：交換後の偽役職別", robber_detail)
print_table("村人潜伏：疑惑の向け先別", villager_detail)
