"""チューリング評価：対戦ログの発言を LLM 審判に『人間 or AI』判定させ、
ソース（human/cpu/llm・モデル別）ごとの「人間らしさスコア」を算出する。

人間らしさスコア = 審判が「人間」と判定した割合。
  - human の発言 … 高いほど自然（サニティチェック）
  - llm / cpu の発言 … 高いほど人間らしい

使い方（ルートから。要 OPENROUTER_API_KEY）:
    python -m dev.turing_eval --limit 40
    python -m dev.turing_eval --dir data/exp1/ --limit 60 --judge openai/gpt-4o-mini
"""
from __future__ import annotations
import argparse
import os
import random
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from players.llm_player import LLMPlayer
from dev.dataset import iter_statements


def build_judge_prompt(rec: dict) -> str:
    ctx = rec["context"]
    # 文脈は直近6行程度に絞る
    lines = [l for l in ctx.splitlines() if l.strip()]
    if len(lines) > 6:
        ctx = "\n".join(["  …"] + lines[-6:])
    return f"""これは5人で遊ぶ人狼ゲームの議論の一場面です。
最後の発言の話者が「人間プレイヤー」か「AI(ボット)」か、どちらだと思いますか。
文体・自然さ・内容から直感で判定してください。

【これまでの議論】
{ctx}
【判定する発言】
  {rec['player_id']}: {rec['statement']}

JSONのみで返答:
{{"guess": "human" または "ai", "reason": "短い理由"}}"""


def sample_balanced(recs: list, limit: int):
    by_type = defaultdict(list)
    for r in recs:
        by_type[r["player_type"]].append(r)
    types = list(by_type)
    per = max(1, limit // max(1, len(types)))
    out = []
    for t in types:
        random.shuffle(by_type[t])
        out.extend(by_type[t][:per])
    random.shuffle(out)
    return out[:limit]


def main():
    ap = argparse.ArgumentParser(description="チューリング評価（人間らしさスコア）")
    ap.add_argument("--dir", default="data/")
    ap.add_argument("--limit", type=int, default=40, help="判定する発言数（API呼び出し数）")
    ap.add_argument("--judge", default=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("✗ OPENROUTER_API_KEY が必要です（.env に設定）。")
        return

    random.seed(args.seed)
    allrecs = [r for r in iter_statements(args.dir) if r["statement"].strip()]
    if not allrecs:
        print(f"{args.dir} に判定対象の発言がありません。")
        return
    sample = sample_balanced(allrecs, args.limit)
    print(f"判定対象 {len(sample)} 発言 / judge={args.judge}\n")

    judge = LLMPlayer("judge", model=args.judge)
    human_judged = defaultdict(lambda: [0, 0])   # key -> [human判定数, total]
    errors = 0

    for i, rec in enumerate(sample, 1):
        try:
            data = judge._call_json(build_judge_prompt(rec))
            guess = str(data.get("guess", "")).lower()
        except Exception:
            errors += 1
            continue
        is_human_guess = int("human" in guess)
        keys = [("type", rec["player_type"])]
        if rec["player_type"] == "llm" and rec.get("model"):
            keys.append(("model", rec["model"]))
        for k in keys:
            human_judged[k][0] += is_human_guess
            human_judged[k][1] += 1
        if i % 10 == 0:
            print(f"  ... {i}/{len(sample)}")

    def show(kind, title):
        rows = sorted(k for k in human_judged if k[0] == kind)
        if not rows:
            return
        print(f"\n【{title}】")
        for k in rows:
            h, n = human_judged[k]
            print(f"  {k[1]:16s} 人間らしさ(=人間と判定された割合): "
                  f"{h / n * 100:5.1f}%  (n={n})")

    show("type", "ソース種別ごとの人間らしさスコア")
    show("model", "LLMモデルごとの人間らしさスコア")
    if errors:
        print(f"\n審判API失敗: {errors} 件")
    # 人間データが無い場合の注記
    if not any(k[1] == "human" for k in human_judged):
        print("\n※ human の発言がまだありません。Web対戦で人間が参加すると"
              "（player_type=human として記録され）比較対象になります。")


if __name__ == "__main__":
    main()
