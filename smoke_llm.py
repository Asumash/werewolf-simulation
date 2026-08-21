"""LLM プレイヤーの疎通スモークテスト（同期・オフライン1ゲーム）。

LLM 1体 + ルールベースCP 4体で1ゲームを回し、
- API 疎通
- 構造化出力（intent/target/result/basis）の妥当性
- 1ゲーム完走
を確認する。

事前準備:
  1) cp .env.example .env
  2) .env に OPENROUTER_API_KEY を記入
  3) python smoke_llm.py
"""
from __future__ import annotations
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP
from players.llm_player import LLMPlayer

ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]
IDS = ["LLM", "CPU-1", "CPU-2", "CPU-3", "CPU-4"]


class _Rec:
    def save(self, *a, **k):
        pass


def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("✗ OPENROUTER_API_KEY が未設定です。")
        print("  cp .env.example .env  → .env にキーを記入してください。")
        sys.exit(1)

    model = os.environ.get("OPENROUTER_MODEL", LLMPlayer.DEFAULT_MODEL)
    print(f"モデル: {model}\n")

    llm = LLMPlayer("LLM")
    players = [llm] + [RuleBasedCP(i) for i in IDS[1:]]

    state = GameState(player_ids=IDS)
    state.setup(ROLE_LIST)
    print("役職:", {i: state.original_role_map[i].value for i in IDS})
    print(f"LLMの役職: {state.original_role_map['LLM'].value}\n")

    # 発言数を絞ってコストを抑える
    runner = GameRunner(state, players, _Rec(), total_statements=8)
    result = runner.run()

    print("\n=== 結果 ===")
    print("勝者:", result["winner"], "/ 処刑:", result.get("executed"))

    print("\n=== LLM の構造化出力 ===")
    if not llm.action_log:
        print("  （LLMは発言に選ばれませんでした）")
    for i, a in enumerate(llm.action_log, 1):
        print(f"  [{i}] intent={a.get('intent')} target={a.get('target')} "
              f"result={a.get('result')} basis={a.get('basis')}")
        print(f"      発言: {a.get('statement')}")

    if llm.errors:
        print("\n⚠️ API エラー:")
        for e in llm.errors:
            print("  -", e)
    else:
        print("\n✓ API エラーなし・1ゲーム完走")


if __name__ == "__main__":
    main()
