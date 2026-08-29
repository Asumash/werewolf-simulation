"""全員RuleBasedCPで動作確認。引数でゲーム数を指定可能。"""
import sys
from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP
from recorder.recorder import GameRecorder

def run_once():
    player_ids = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    players = [RuleBasedCP(pid) for pid in player_ids]
    role_list = [
        Role.WEREWOLF, Role.WEREWOLF,
        Role.SEER, Role.ROBBER, Role.VILLAGER,
        Role.VILLAGER, Role.VILLAGER,
    ]
    state = GameState(player_ids=player_ids)
    state.setup(role_list)
    recorder = GameRecorder(output_dir="data/")
    runner = GameRunner(state, players, recorder)
    return runner.run()

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    results = {"village": 0, "werewolf": 0}
    for i in range(n):
        print(f"\n--- Game {i + 1} ---")
        result = run_once()
        results[result["winner"]] += 1
        print(f"勝者: {result['winner']}  処刑: {result['executed']}")
    if n > 1:
        print(f"\n=== {n}戦集計: 村人{results['village']}勝 / 人狼{results['werewolf']}勝 ===")
