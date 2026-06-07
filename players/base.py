from __future__ import annotations
from abc import ABC, abstractmethod
from engine.game_state import GameState, Role

class PlayerInterface(ABC):
    def __init__(self, player_id: str):
        self.player_id = player_id

    @abstractmethod
    def night_action(self, state: GameState) -> dict:
        """
        夜フェーズの行動を返す。
        戻り値例:
          占い師: {"action": "see_player", "target": "player_2"}
          占い師: {"action": "see_graveyard"}
          怪盗:  {"action": "swap", "target": "player_1"}
          怪盗:  {"action": "skip"}
          村人・人狼: {"action": "none"}
        """
        pass

    @abstractmethod
    def get_urgency_score(self, state: GameState) -> float:
        """
        このターンに発言したい度合いを返す（高いほど発言を優先）。
        発言ループは全プレイヤーのスコアを重みとして確率的に話者を選ぶ。
        """
        pass

    @abstractmethod
    def make_statement(self, state: GameState) -> tuple[str, str]:
        """
        議論フェーズの発言を返す。
        戻り値: (発言内容, 内部思考reasoning)
        reasoningは学習データ用で、実際には表示しない。
        """
        pass

    @abstractmethod
    def vote(self, state: GameState) -> str:
        """投票対象のplayer_idを返す。"""
        pass
