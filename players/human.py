from __future__ import annotations
from players.base import PlayerInterface
from engine.game_state import GameState, Role

class HumanPlayer(PlayerInterface):

    def night_action(self, state: GameState) -> dict:
        role = state.role_map[self.player_id]
        if role == Role.SEER:
            print("\n[占い師] 誰かを占うか(p)、墓地を見るか(g)？")
            choice = input("> ").strip()
            if choice == "g":
                return {"action": "see_graveyard"}
            others = [p for p in state.player_ids if p != self.player_id]
            print(f"占う相手を選んでください: {others}")
            target = input("> ").strip()
            return {"action": "see_player", "target": target}

        elif role == Role.ROBBER:
            others = [p for p in state.player_ids if p != self.player_id]
            print(f"\n[怪盗] 交換する相手を選んでください（スキップ: enter）: {others}")
            target = input("> ").strip()
            if not target:
                return {"action": "skip"}
            return {"action": "swap", "target": target}

        return {"action": "none"}

    def get_urgency_score(self, state: GameState) -> float:
        """人間プレイヤーは常に一定スコア（ユーザーが任意に発言）。"""
        return 1.5

    def make_statement(self, state: GameState) -> tuple[str, str]:
        pub = state.get_public_state(self.player_id)
        print(f"\n[{self.player_id}の番] あなたの役職: {pub['my_role']}")
        print(f"知っている情報: {pub['my_knowledge']}")
        print("発言してください:")
        statement = input("> ").strip()
        return statement, ""

    def vote(self, state: GameState) -> str:
        others = [p for p in state.player_ids if p != self.player_id]
        print(f"\n[{self.player_id}] 投票先を選んでください: {others}")
        return input("> ").strip()
