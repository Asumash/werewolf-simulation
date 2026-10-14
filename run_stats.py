from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP
from recorder.recorder import GameRecorder
import sys
import io

def run_game():
    player_ids = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    players = [RuleBasedCP(p) for p in player_ids]
    role_list = [
        Role.WEREWOLF, Role.WEREWOLF,
        Role.SEER, Role.ROBBER, Role.VILLAGER,
        Role.VILLAGER, Role.VILLAGER,
    ]
    state = GameState(player_ids=player_ids)
    state.setup(role_list)
    recorder = GameRecorder(output_dir="data/")
    # 出力を抑制
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    runner = GameRunner(state, players, recorder)
    result = runner.run()
    sys.stdout = old_stdout
    return result

if __name__ == "__main__":
    N = 1000
    counts = {"village": 0, "werewolf": 0}

    for i in range(N):
        result = run_game()
        counts[result["winner"]] += 1
        if (i + 1) % 100 == 0:
            print(f"{i+1}/{N} 完了...")

    print()
    print("=== 1000ゲーム 勝率集計 ===")
    print(f"村人陣営 勝利: {counts['village']} 回  ({counts['village']/N*100:.1f}%)")
    print(f"人狼陣営 勝利: {counts['werewolf']} 回  ({counts['werewolf']/N*100:.1f}%)")
