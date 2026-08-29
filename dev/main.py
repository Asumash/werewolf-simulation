from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.human import HumanPlayer
from players.rule_based import RuleBasedCP
from players.llm_player import LLMPlayer
from recorder.recorder import GameRecorder

def main():
    player_ids = ["Alice", "Bob", "Carol", "Dave", "Eve"]

    # ここを変えるだけで構成変更
    players = [
        HumanPlayer("Alice"),
        RuleBasedCP("Bob"),
        RuleBasedCP("Carol"),
        LLMPlayer("Dave"),
        RuleBasedCP("Eve"),
    ]

    # 5人用構成: 人狼×2, 占い師×1, 怪盗×1, 村人×1 + 墓地(村人×2)
    role_list = [
        Role.WEREWOLF, Role.WEREWOLF,
        Role.SEER, Role.ROBBER, Role.VILLAGER,
        Role.VILLAGER, Role.VILLAGER,  # 墓地2枚
    ]

    state = GameState(player_ids=player_ids)
    state.setup(role_list)

    recorder = GameRecorder(output_dir="data/")
    runner = GameRunner(state, players, recorder)

    result = runner.run()
    print(f"\n=== 結果: {result['winner']} の勝利 ===")
    print(f"処刑: {result['executed']}")

if __name__ == "__main__":
    main()
