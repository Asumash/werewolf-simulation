"""無人バッチ対戦ランナー（研究用のデータ生成・比較実験の土台）。

CPU / LLM の席構成を指定して多数の対戦を回し、各ゲームを data/ に記録しつつ、
プレイヤー種別ごとの勝率などを集計する。

使い方（リポジトリのルートから）:
    python -m dev.batch_run --games 200                 # 全CPU（無料）
    python -m dev.batch_run --games 50 --llm 1          # 1席をLLMに（要APIキー）
    python -m dev.batch_run --games 50 --llm 2 --model openai/gpt-4o-mini

- LLM席を使う場合は .env の OPENROUTER_API_KEY が必要（無い場合は中止）。
- 各ゲームは recorder により data/ に保存される（種別・モデル・行動タグ付き）。
"""
from __future__ import annotations
import argparse
import contextlib
import io
import os
import sys
from collections import Counter

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP
from players.llm_player import LLMPlayer
from recorder.recorder import GameRecorder, player_type

ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]
VILLAGE = {Role.VILLAGER, Role.SEER, Role.ROBBER}


def build_players(n_llm: int, model: str):
    players = []
    li = ci = 0
    for i in range(5):
        if i < n_llm:
            li += 1
            players.append(LLMPlayer(f"LLM-{li}", model=model))
        else:
            ci += 1
            players.append(RuleBasedCP(f"CPU-{ci}"))
    return players


def main():
    ap = argparse.ArgumentParser(description="無人バッチ対戦ランナー")
    ap.add_argument("--games", type=int, default=20, help="対戦数")
    ap.add_argument("--llm", type=int, default=0, help="LLM席の数（0〜5）")
    ap.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    ap.add_argument("--statements", type=int, default=15, help="1ゲームの総発言数")
    ap.add_argument("--out", default="data/", help="記録の出力先")
    args = ap.parse_args()

    n_llm = max(0, min(5, args.llm))
    if n_llm > 0 and not os.environ.get("OPENROUTER_API_KEY"):
        print("✗ LLM席を使うには OPENROUTER_API_KEY が必要です（.env に設定）。")
        sys.exit(1)
    if n_llm > 0:
        print(f"⚠ LLM {n_llm}席 × {args.games}ゲーム = API呼び出しが発生します（コスト注意）。\n")

    recorder = GameRecorder(output_dir=args.out)

    village_win = 0
    type_win = Counter()
    type_total = Counter()
    llm_errors = 0

    for g in range(args.games):
        players = build_players(n_llm, args.model)
        ids = [p.player_id for p in players]
        state = GameState(player_ids=ids)
        state.setup(ROLE_LIST)
        with contextlib.redirect_stdout(io.StringIO()):
            res = GameRunner(state, players, recorder,
                             total_statements=args.statements).run()
        winner = res["winner"]
        if winner == "village":
            village_win += 1
        # プレイヤー種別ごとに「自分の陣営が勝ったか」を集計
        for p in players:
            side = "village" if state.role_map[p.player_id] in VILLAGE else "werewolf"
            t = player_type(p)
            type_total[t] += 1
            if side == winner:
                type_win[t] += 1
            llm_errors += len(getattr(p, "errors", []) or [])
        if (g + 1) % 20 == 0:
            print(f"  ... {g + 1}/{args.games}")

    print("\n=== 集計 ===")
    comp = f"LLM×{n_llm} + CPU×{5 - n_llm}" + (f" / model={args.model}" if n_llm else "")
    print(f"構成: {comp}　対戦数: {args.games}")
    print(f"村人陣営 勝率: {village_win / args.games * 100:.1f}%")
    print("プレイヤー種別ごとの『自陣営が勝った割合』:")
    for t in sorted(type_total):
        w, n = type_win[t], type_total[t]
        print(f"  {t:6s}: {w}/{n} = {w / n * 100:.1f}%")
    if n_llm > 0:
        print(f"LLM APIエラー総数: {llm_errors}")
    print(f"\n記録: {args.out} に {args.games} ゲーム分を保存しました。")


if __name__ == "__main__":
    main()
