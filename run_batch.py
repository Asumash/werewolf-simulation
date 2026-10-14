from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP
from recorder.recorder import GameRecorder


def run_game(i):
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
    runner = GameRunner(state, players, recorder)
    result = runner.run()
    print(f"Game {i+1}: winner={result['winner']} executed={result['executed']}")
    print()


if __name__ == "__main__":
    for i in range(10):
        run_game(i)
