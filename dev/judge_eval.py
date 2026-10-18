"""LLM judge によるプレイヤー種別推定の性能評価。

匿名化ログ（dev/anonymize.py の出力）を複数の LLM judge に渡し、
各プレイヤーを human / cpu / llm に分類させて正解率を報告する。

使い方:
    python -m dev.judge_eval                         # data/anon/ を使用
    python -m dev.judge_eval --anon data/anon/ --limit 10
    python -m dev.judge_eval --models gpt-sol,opus  # モデルを絞る
"""
from __future__ import annotations
import argparse
import json
import os
import re
import time
from pathlib import Path
from collections import defaultdict
import httpx
from dotenv import load_dotenv

load_dotenv()

# ── judge モデル定義 ──────────────────────────────────────────────────────────
# OpenRouter モデル ID を実際のものに合わせて編集してください
JUDGE_MODELS: dict[str, str] = {
    "gpt-sol":   "openai/gpt-5.6-sol",
    "gpt-luna":  "openai/gpt-5.6-luna",
    "opus":      "anthropic/claude-opus-4.5",
    "haiku":     "anthropic/claude-haiku-4.5",
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TYPES = ("human", "cpu", "llm")


# ── プロンプト生成 ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
あなたはワンナイト人狼ゲームのプレイログを分析する専門家です。
ゲームのプレイヤーは3種類のうちいずれかです：
  - human  : 人間プレイヤー（自然な判断・感情・ためらいがある）
  - cpu    : ルールベースAI（決定論的・パターン化した発言・機械的な疑い方）
  - llm    : 大規模言語モデルAI（流暢だが紋切り型、役職に忠実すぎる傾向）

ゲームログを読んで、各プレイヤーの種別を判定してください。
"""

INTENT_LABEL = {
    "suspect": "疑う", "seer_result": "占い結果", "robber_result": "怪盗結果",
    "vote_suggest": "投票誘導", "contradict": "矛盾指摘", "vouch": "信頼",
    "ask": "質問", "none": "―",
}


def format_log(records: list[dict]) -> str:
    """匿名化レコードを judge に渡す文字列に変換する。"""
    meta = next((r for r in records if r["type"] == "meta"), None)
    stmts = [r for r in records if r["type"] == "statement"]
    votes = [r for r in records if r["type"] == "vote"]

    lines = []
    if meta:
        lines.append(f"=== ゲーム概要 ===")
        lines.append(f"プレイヤー: {', '.join(meta['players'])}")
        lines.append(f"配布役職（元）: " +
                     ", ".join(f"{p}={meta['original_role_map'].get(p,'?')}"
                               for p in meta["players"]))
        lines.append(f"最終役職: " +
                     ", ".join(f"{p}={meta['role_map'].get(p,'?')}"
                               for p in meta["players"]))
        lines.append(f"結果: {meta['result']['winner']}陣営勝利 "
                     f"処刑={meta['result'].get('executed', [])}")
        lines.append("")

    lines.append("=== 議論ログ ===")
    for s in stmts:
        intent = INTENT_LABEL.get(s.get("intent", "none"), s.get("intent", ""))
        target = s.get("target", "")
        result = s.get("result", "")
        tag = ""
        if intent and intent != "―":
            tag = f"[{intent}"
            if target:
                tag += f"→{target}"
            if result:
                tag += f"({result})"
            tag += "]"
        lines.append(f"{s['player_id']} {tag}: {s['statement']}")

    lines.append("")
    lines.append("=== 投票 ===")
    for v in votes:
        lines.append(f"{v['voter']} → {v['target']}")

    return "\n".join(lines)


USER_TEMPLATE = """\
以下のワンナイト人狼ゲームのログを分析してください。

{log}

---
上記ログの各プレイヤーについて、以下の3種別のいずれかを判定してください：
  human / cpu / llm

必ず以下のJSON形式のみで回答してください（説明文は不要）：
{{"P1": "human", "P2": "cpu", "P3": "llm", "P4": "...", "P5": "..."}}
プレイヤー数はゲームにより異なります。ログに登場したプレイヤー全員を含めてください。
"""


# ── API 呼び出し ─────────────────────────────────────────────────────────────

def call_judge(model_id: str, log_text: str, api_key: str,
               retries: int = 3) -> dict[str, str] | None:
    """judge モデルを呼び出し、{P1: type, ...} を返す。失敗時は None。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": USER_TEMPLATE.format(log=log_text)},
        ],
        "temperature": 0,
        # 推論(reasoning)モデルは思考トークンを消費するため余裕を持たせる
        # （これが小さいと content が空で返ることがある）
        "max_tokens": 2000,
    }
    for attempt in range(retries):
        try:
            resp = httpx.post(OPENROUTER_URL, headers=headers,
                              json=payload, timeout=90)
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            # 推論モデルは content が空で reasoning 側に出ることがあるので両方見る
            content = (msg.get("content") or msg.get("reasoning") or "").strip()
            if not content:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                print(f"  [warn] 空応答（content/reasoning とも無し）")
                return None
            # JSON 抽出（余分なテキストが混じっても対応）
            m = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if not m:
                print(f"  [warn] JSON が取得できませんでした: {content[:80]}")
                return None
            return json.loads(m.group())
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  [error] {model_id}: {e}")
                return None
    return None


# ── 評価 ─────────────────────────────────────────────────────────────────────

def evaluate(predictions: dict, truth_map: dict) -> dict:
    """predictions: {P_label: pred_type}, truth_map: {P_label: {type: ...}}
    {total, correct, per_type: {type: {tp, fp, fn}}} を返す。"""
    total = correct = 0
    per_type: dict[str, dict] = {t: {"tp": 0, "fp": 0, "fn": 0} for t in TYPES}
    for label, info in truth_map.items():
        true_type = info["type"]
        pred_type = predictions.get(label)
        if pred_type is None:
            continue
        total += 1
        if pred_type == true_type:
            correct += 1
            per_type[true_type]["tp"] += 1
        else:
            per_type[true_type]["fn"] += 1
            if pred_type in per_type:
                per_type[pred_type]["fp"] += 1
    return {"total": total, "correct": correct, "per_type": per_type}


def pct(n, d):
    return f"{n/d*100:.1f}%" if d else "  -  "


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anon", default="data/anon/")
    ap.add_argument("--truth", default=None,
                    help="ground_truth.jsonl のパス（省略時は --anon/ground_truth.jsonl）")
    ap.add_argument("--output", default="data/anon/judge_results.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--models", default=None,
                    help="カンマ区切りのキー名（例: gpt-sol,opus）。省略時は全モデル")
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY が未設定です。.env を確認してください。")
        return

    anon_dir = Path(args.anon)
    truth_path = Path(args.truth) if args.truth else anon_dir / "ground_truth.jsonl"

    if not truth_path.exists():
        print(f"ERROR: {truth_path} が見つかりません。先に dev/anonymize.py を実行してください。")
        return

    # 正解ラベルをロード
    truth_by_game: dict[str, dict] = {}
    for line in truth_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            t = json.loads(line)
            truth_by_game[t["game_id"]] = t["map"]

    # 匿名化ゲームをロード
    anon_files = sorted(anon_dir.glob("game_*.jsonl"))
    if args.limit:
        anon_files = anon_files[:args.limit]

    # 使用するモデルを絞る
    if args.models:
        keys = [k.strip() for k in args.models.split(",")]
        models = {k: JUDGE_MODELS[k] for k in keys if k in JUDGE_MODELS}
    else:
        models = JUDGE_MODELS

    print(f"匿名化ゲーム数: {len(anon_files)}")
    print(f"使用 judge モデル: {list(models.keys())}\n")

    # 結果の集計
    agg: dict[str, dict] = {k: {"total": 0, "correct": 0,
                                  "per_type": {t: {"tp": 0, "fp": 0, "fn": 0} for t in TYPES}}
                              for k in models}
    results_out = []

    for fp in anon_files:
        records = [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
        meta = next((r for r in records if r["type"] == "meta"), None)
        if not meta:
            continue
        game_id = meta["game_id"]
        truth_map = truth_by_game.get(game_id)
        if not truth_map:
            print(f"[skip] {fp.name}: ground_truth に未登録")
            continue

        log_text = format_log(records)
        game_result = {"game_id": game_id, "file": fp.name, "predictions": {}}

        for key, model_id in models.items():
            print(f"  {fp.name}  [{key}] ...", end="", flush=True)
            pred = call_judge(model_id, log_text, api_key)
            if pred is None:
                print(" FAIL")
                continue
            ev = evaluate(pred, truth_map)
            print(f" {ev['correct']}/{ev['total']}")

            # 集計
            agg[key]["total"]   += ev["total"]
            agg[key]["correct"] += ev["correct"]
            for t in TYPES:
                for k2 in ("tp", "fp", "fn"):
                    agg[key]["per_type"][t][k2] += ev["per_type"][t][k2]

            game_result["predictions"][key] = {
                "model": model_id,
                "pred": pred,
                "eval": ev,
            }

        results_out.append(game_result)

    # 結果保存
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ── サマリー出力 ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("【LLM Judge 性能評価 サマリー】")
    print("=" * 60)
    header = f"{'モデル':20s}  {'全体精度':>8s}  {'human精度':>9s}  {'cpu精度':>8s}  {'llm精度':>8s}"
    print(header)
    print("-" * 60)
    for key, model_id in models.items():
        a = agg[key]
        acc = pct(a["correct"], a["total"])
        rows = []
        for t in TYPES:
            tp = a["per_type"][t]["tp"]
            fp = a["per_type"][t]["fp"]
            fn = a["per_type"][t]["fn"]
            prec = tp / (tp + fp) if (tp + fp) else 0
            rec  = tp / (tp + fn) if (tp + fn) else 0
            f1   = 2*prec*rec / (prec+rec) if (prec+rec) else 0
            rows.append(f"{f1*100:.0f}%")
        print(f"{key:20s}  {acc:>8s}  {rows[0]:>9s}  {rows[1]:>8s}  {rows[2]:>8s}")
    print("-" * 60)
    print("※ 各種別精度は F1 スコア")
    print(f"\n詳細結果: {out_path}")


if __name__ == "__main__":
    main()
