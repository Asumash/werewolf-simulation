"""学習データ書き出し：対戦ログの発言を、LLM 学習用に変換する。

出力:
  1) SFT用 JSONL（messages形式）… fine-tune に使える
  2) few-shot 例バンク（JSON）… プロンプトに差し込んで口調を模倣させる

既定では human の発言のみを対象にする（人間らしさの学習が目的のため）。
人間データがまだ無い場合は --types llm,cpu で形式確認ができる。

使い方（ルートから）:
    python -m dev.export_training --types human
    python -m dev.export_training --types llm,cpu --out data/train/
"""
from __future__ import annotations
import argparse
import json
import os

from dev.dataset import iter_statements


def to_sft_example(rec: dict) -> dict:
    system = ("あなたは5人で遊ぶ人狼ゲームのプレイヤーです。"
              "人間らしく、短く自然な口語で1つだけ発言してください。")
    user = (f"あなたの役職: {rec.get('role')}\n"
            f"【これまでの議論】\n{rec['context']}\n\n"
            f"次のあなたの発言を一つ、短く:")
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": rec["statement"]},
    ]}


def main():
    ap = argparse.ArgumentParser(description="学習データの書き出し")
    ap.add_argument("--dir", default="data/")
    ap.add_argument("--types", default="human",
                    help="対象のplayer_type（カンマ区切り。例: human / llm,cpu）")
    ap.add_argument("--out", default="data/train/")
    ap.add_argument("--max-fewshot", type=int, default=40, help="few-shot例の最大数")
    args = ap.parse_args()

    types = {t.strip() for t in args.types.split(",") if t.strip()}
    os.makedirs(args.out, exist_ok=True)
    tag = "_".join(sorted(types))

    sft_path = os.path.join(args.out, f"sft_{tag}.jsonl")
    bank_path = os.path.join(args.out, f"fewshot_{tag}.json")

    n = 0
    bank = []
    seen = set()
    with open(sft_path, "w", encoding="utf-8") as f:
        for rec in iter_statements(args.dir, types=types):
            st = rec["statement"].strip()
            if not st:
                continue
            f.write(json.dumps(to_sft_example(rec), ensure_ascii=False) + "\n")
            n += 1
            # few-shot バンク（短め・重複なし）
            if len(bank) < args.max_fewshot and 6 <= len(st) <= 60 and st not in seen:
                seen.add(st)
                bank.append({"role": rec.get("role"), "statement": st})

    with open(bank_path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"対象 player_type: {sorted(types)}")
    print(f"SFT例: {n} 件 → {sft_path}")
    print(f"few-shot例: {len(bank)} 件 → {bank_path}")
    if n == 0:
        print("\n※ 対象の発言がありません。human データはまだ無い可能性があります。"
              "Web対戦で人間が参加すると記録され、ここから学習データを作れます。"
              "（形式確認は --types llm,cpu で可能）")
    else:
        print("\nfine-tune（OpenAI等）には SFT の JSONL を、"
              "プロンプト流用には few-shot バンクを使えます。")


if __name__ == "__main__":
    main()
