"""
議論の長さ（total_statements）を変えて勝敗・投票精度を比較する。
各設定で n_games ゲームを実行し、結果を表形式で出力する。
"""
from __future__ import annotations
import json, sys, os, shutil
from pathlib import Path
from collections import defaultdict
from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP
from recorder.recorder import GameRecorder

PLAYER_IDS = ["Alice", "Bob", "Carol", "Dave", "Eve"]
ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]

def run_batch(n_games: int, total_statements: int, tmp_dir: str) -> dict:
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    recorder = GameRecorder(output_dir=tmp_dir)

    wins = defaultdict(int)
    executed_roles = defaultdict(int)
    correct_votes = defaultdict(int)
    total_votes   = defaultdict(int)
    expose_count  = 0
    swap_wolf     = 0

    for _ in range(n_games):
        players = [RuleBasedCP(pid) for pid in PLAYER_IDS]
        state   = GameState(player_ids=PLAYER_IDS)
        state.setup(ROLE_LIST)
        runner  = GameRunner(state, players, recorder,
                             total_statements=total_statements)
        result  = runner.run()

        wins[result["winner"]] += 1

        for pid in result["executed"]:
            executed_roles[state.role_map[pid].value] += 1

        # 投票精度
        for voter, target in state.votes.items():
            vr = next(
                (s["role"] for s in
                 [json.loads(l) for l in open(
                     sorted(Path(tmp_dir).glob("game_*.jsonl"))[-1],
                     encoding="utf-8")]
                 if s.get("type") == "statement" and s.get("player_id") == voter),
                "不明"
            )
            total_votes[vr] += 1
            if state.role_map[target] == Role.WEREWOLF:
                correct_votes[vr] += 1

        # 確定指摘
        if any("断言します" in t.statement or "矛盾しています" in t.statement
               for t in state.discussion_log):
            expose_count += 1

        # 怪盗→人狼スワップ
        orig = state.original_role_map
        robber_pid = next((p for p, r in orig.items() if r == Role.ROBBER), None)
        if robber_pid and state.role_map[robber_pid] == Role.WEREWOLF:
            swap_wolf += 1

    shutil.rmtree(tmp_dir, ignore_errors=True)

    vr_acc  = correct_votes["村人"] / total_votes["村人"] if total_votes["村人"] else 0
    se_acc  = correct_votes["占い師"] / total_votes["占い師"] if total_votes["占い師"] else 0
    rob_acc = correct_votes["怪盗"] / total_votes["怪盗"] if total_votes["怪盗"] else 0
    wf_acc  = correct_votes["人狼"] / total_votes["人狼"] if total_votes["人狼"] else 0

    return {
        "statements": total_statements,
        "village_win": wins["village"] / n_games,
        "wolf_win":    wins["werewolf"] / n_games,
        "wolf_executed": executed_roles.get("人狼", 0) / n_games,
        "villager_executed": (executed_roles.get("村人", 0) + executed_roles.get("占い師", 0) + executed_roles.get("怪盗", 0)) / n_games,
        "expose_rate": expose_count / n_games,
        "vote_acc_villager": vr_acc,
        "vote_acc_seer":     se_acc,
        "vote_acc_robber":   rob_acc,
        "vote_acc_wolf":     wf_acc,
        "swap_wolf_rate":    swap_wolf / n_games,
    }

if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    LENGTHS = [5, 8, 10, 12, 15, 20, 25, 30]

    print(f"各設定 {N} ゲームで計測中...\n")

    results = []
    for length in LENGTHS:
        print(f"  total_statements={length:2d} ... ", end="", flush=True)
        r = run_batch(N, length, f"_tmp_{length}")
        results.append(r)
        print(f"村人勝率={r['village_win']:.1%}  人狼処刑率={r['wolf_executed']:.2f}")

    # ── テーブル出力 ──
    print()
    H = ("発言数", "村人勝率", "人狼勝率", "人狼処刑/G", "指摘発生率",
         "投票精度(村)", "投票精度(占)", "投票精度(怪)", "狼SW率")
    FMT = "{:>6} {:>8} {:>8} {:>10} {:>10} {:>12} {:>12} {:>12} {:>8}"
    print(FMT.format(*H))
    print("─" * 92)
    for r in results:
        print(FMT.format(
            r["statements"],
            f"{r['village_win']:.1%}",
            f"{r['wolf_win']:.1%}",
            f"{r['wolf_executed']:.3f}",
            f"{r['expose_rate']:.1%}",
            f"{r['vote_acc_villager']:.1%}",
            f"{r['vote_acc_seer']:.1%}",
            f"{r['vote_acc_robber']:.1%}",
            f"{r['swap_wolf_rate']:.1%}",
        ))
