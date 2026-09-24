"""対戦ログ（data/*.jsonl）から研究用の評価指標を自動集計する。

算出する指標:
  - 全体勝率（村人陣営 / 人狼陣営）
  - 配布役職ごとの自陣営勝率
  - プレイヤー種別（human/cpu/llm）ごとの:
        自陣営が勝った割合 / 投票精度 / 情報役職のCO率 / 平均発言数
  - LLM のモデルごとの同指標（モデル比較）
  - 種別ごとの intent（行動）分布

使い方（リポジトリのルートから）:
    python -m dev.analyze_games                 # data/ をすべて集計
    python -m dev.analyze_games --dir data/ --limit 500
"""
from __future__ import annotations
import argparse
import glob
import json
import os
from collections import Counter, defaultdict

VILLAGE = {"村人", "占い師", "怪盗"}
WOLF = "人狼"


def load_games(directory: str, limit: int | None, min_schema: int):
    files = sorted(glob.glob(os.path.join(directory, "game_*.jsonl")),
                   key=os.path.getmtime, reverse=True)
    games = []
    skipped_old = 0
    for fp in files:
        try:
            recs = [json.loads(l) for l in open(fp, encoding="utf-8") if l.strip()]
        except Exception:
            continue
        meta = next((r for r in recs if r.get("type") == "meta"), None)
        if not meta or "result" not in meta:
            continue
        if meta.get("schema_version", 1) < min_schema:
            skipped_old += 1
            continue
        stmts = [r for r in recs if r.get("type") == "statement"]
        votes = [r for r in recs if r.get("type") == "vote"]
        games.append((meta, stmts, votes))
        if limit and len(games) >= limit:
            break
    return games, skipped_old


def pct(w, n):
    return f"{w / n * 100:5.1f}%" if n else "   -  "


def main():
    ap = argparse.ArgumentParser(description="対戦ログの評価指標を集計")
    ap.add_argument("--dir", default="data/")
    ap.add_argument("--limit", type=int, default=None, help="新しい順に最大N件")
    ap.add_argument("--all", action="store_true",
                    help="旧スキーマ(タグ無し)も含める（既定は現行 schema>=2 のみ）")
    args = ap.parse_args()

    min_schema = 1 if args.all else 2
    games, skipped_old = load_games(args.dir, args.limit, min_schema)
    N = len(games)
    if N == 0:
        msg = f"{args.dir} に集計対象のログがありません。"
        if skipped_old:
            msg += f"（旧スキーマ {skipped_old} 件は除外。--all で含められます）"
        print(msg)
        return

    village_win = sum(1 for m, _, _ in games if m["result"]["winner"] == "village")

    role_win = defaultdict(lambda: [0, 0])           # 配布役職 -> [win, total]
    side = defaultdict(lambda: [0, 0])               # key -> [win, total]
    role_side = defaultdict(lambda: [0, 0])          # (key, 配布役職) -> [win, total]
    vote_acc = defaultdict(lambda: [0, 0])           # key -> [correct, total]（村側投票）
    co = defaultdict(lambda: [0, 0])                 # key -> [co, info役職数]
    stmts_per = defaultdict(lambda: [0, 0])          # key -> [発言数, 人数]
    intents = defaultdict(Counter)                   # key -> intent分布
    key_kinds = ("type", "model")

    for meta, stmts, votes in games:
        winner = meta["result"]["winner"]
        rolemap = meta["role_map"]                    # 交換後の真の役職
        origmap = meta.get("original_role_map", {})
        pmeta = meta.get("players_meta", {})

        def keys_of(pid):
            t = pmeta.get(pid, {}).get("type", "cpu")
            ks = [("type", t)]
            m = pmeta.get(pid, {}).get("model")
            if t == "llm" and m:
                ks.append(("model", m))
            return ks

        by_player = defaultdict(list)
        for s in stmts:
            by_player[s["player_id"]].append(s)

        for pid in meta["players"]:
            final = rolemap.get(pid)
            sd = "village" if final in VILLAGE else "werewolf"
            win = int(sd == winner)
            # 配布役職別（全体）
            orig = origmap.get(pid)
            if orig:
                role_win[orig][0] += win
                role_win[orig][1] += 1
            mystmts = by_player.get(pid, [])
            believed = {s.get("role") for s in mystmts}
            is_info = ("占い師" in believed or "怪盗" in believed
                       or (not mystmts and orig in ("占い師", "怪盗")))
            did_co = any(s.get("intent") in ("seer_result", "robber_result")
                         for s in mystmts)
            for k in keys_of(pid):
                side[k][0] += win
                side[k][1] += 1
                if orig:
                    role_side[(k, orig)][0] += win
                    role_side[(k, orig)][1] += 1
                stmts_per[k][0] += len(mystmts)
                stmts_per[k][1] += 1
                for s in mystmts:
                    intents[k][s.get("intent") or "none"] += 1
                if is_info:
                    co[k][0] += int(did_co)
                    co[k][1] += 1

        for v in votes:
            if v.get("voter_true_role") not in VILLAGE:
                continue
            correct = int(rolemap.get(v.get("target")) == WOLF)
            voter = v["voter"]
            for k in keys_of(voter):
                vote_acc[k][0] += correct
                vote_acc[k][1] += 1

    # ── 出力 ──
    note = f"（旧スキーマ {skipped_old} 件を除外）" if skipped_old and not args.all else ""
    print(f"=== 集計対象: {N} ゲーム（{args.dir}）{note} ===\n")
    print("【全体勝率】")
    print(f"  村人陣営 {pct(village_win, N)}   人狼陣営 {pct(N - village_win, N)}\n")

    print("【配布役職ごとの自陣営勝率】")
    for role in ("占い師", "怪盗", "村人", "人狼"):
        w, n = role_win[role]
        print(f"  {role:4s}: {pct(w, n)}  (n={n})")
    print()

    def dump(kind, title):
        rows = sorted(k for k in side if k[0] == kind)
        if not rows:
            return
        print(f"【{title}】")
        print(f"  {'':14s} 自陣営勝率  投票精度  情報CO率  平均発言")
        for k in rows:
            name = k[1]
            sp = stmts_per[k]
            avg = f"{sp[0] / sp[1]:.1f}" if sp[1] else "-"
            print(f"  {name:14s} {pct(*side[k])}   {pct(*vote_acc[k])}  "
                  f"{pct(*co[k])}   {avg}")
        print()

    dump("type", "プレイヤー種別ごとの指標")
    dump("model", "LLMモデルごとの指標（モデル比較）")

    def dump_roles(kind, title):
        rows = sorted(k for k in side if k[0] == kind)
        if not rows:
            return
        roles = ("占い師", "怪盗", "村人", "人狼")
        print(f"【{title}】")
        print("  " + " " * 14 + "".join(f"{r:>12s}" for r in roles))
        for k in rows:
            cells = []
            for r in roles:
                w, n = role_side.get((k, r), [0, 0])
                cells.append(f"{w / n * 100:.0f}%({n})" if n else "-")
            print(f"  {k[1]:14s}" + "".join(f"{c:>12s}" for c in cells))
        print()

    dump_roles("type", "種別×配布役職ごとの自陣営勝率（弱点の切り分け）")
    dump_roles("model", "モデル×配布役職ごとの自陣営勝率")

    print("【intent（行動）分布：種別ごと・上位】")
    for k in sorted(k for k in intents if k[0] == "type"):
        total = sum(intents[k].values()) or 1
        top = intents[k].most_common(6)
        s = " ".join(f"{it}:{c / total * 100:.0f}%" for it, c in top)
        print(f"  {k[1]:6s}  {s}")

    print("\n※ 投票精度＝村側の投票が実際の人狼に入った割合。"
          "情報CO率＝占い/怪盗が結果をCOした割合。")


if __name__ == "__main__":
    main()
