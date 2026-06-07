from __future__ import annotations
import random
from engine.game_state import GameState, Phase, Role, Turn
from players.base import PlayerInterface
from recorder.recorder import GameRecorder

NIGHT_ORDER = [Role.SEER, Role.WEREWOLF, Role.ROBBER]

class GameRunner:
    def __init__(
        self,
        state: GameState,
        players: list[PlayerInterface],
        recorder: GameRecorder,
        total_statements: int = 15,
    ):
        self.state = state
        self.players = {p.player_id: p for p in players}
        self.recorder = recorder
        self.total_statements = total_statements

    def run(self) -> dict:
        self._night_phase()
        self._discussion_phase()
        self._vote_phase()
        result = self.state.judge_result()
        self.recorder.save(self.state, result)
        return result

    def _night_phase(self):
        self.state.phase = Phase.NIGHT
        for role in NIGHT_ORDER:
            for pid, player in self.players.items():
                if self.state.role_map[pid] == role:
                    action = player.night_action(self.state)
                    self._apply_night_action(pid, action)

    def _apply_night_action(self, pid: str, action: dict):
        a = action.get("action")
        if a == "see_player":
            self.state.apply_seer_action(pid, action.get("target"))
        elif a == "see_graveyard":
            self.state.apply_seer_action(pid, None)
        elif a == "swap":
            self.state.apply_robber_action(pid, action.get("target"))
        elif a == "skip":
            self.state.apply_robber_action(pid, None)

    def _discussion_phase(self):
        """
        重要度スコアを重みとして確率的に話者を選ぶ。
        合計 total_statements 回の発言が行われるまで続ける。
        """
        self.state.phase = Phase.DISCUSSION
        for _ in range(self.total_statements):
            scores = {
                pid: player.get_urgency_score(self.state)
                for pid, player in self.players.items()
            }
            speaker_id = _weighted_choice(scores)
            player = self.players[speaker_id]
            statement, reasoning = player.make_statement(self.state)
            turn = Turn(
                player_id=speaker_id,
                statement=statement,
                reasoning=reasoning,
                is_lie=self._detect_lie(speaker_id, statement),
            )
            self.state.add_statement(turn)
            print(f"  {speaker_id}: {statement}")

    def _detect_lie(self, pid: str, statement: str) -> bool:
        """
        嘘発言の判定。信じている役職（believed_role）と発言内容を照合する。
        """
        from recorder.recorder import _believed_role
        believed = _believed_role(pid, self.state)

        # 「私は〇〇です」形式
        for role_name in ["人狼", "占い師", "怪盗", "村人"]:
            if f"私は{role_name}" in statement and role_name != believed:
                return True

        # 「〇〇です。〇〇を占いました」→ 占い師CO
        if ("占い師です" in statement) and "占い師" != believed:
            return True

        # 「怪盗です。〇〇と交換しました」→ 怪盗CO
        if ("怪盗です" in statement and "交換しました" in statement) and "怪盗" != believed:
            return True

        return False

    def _vote_phase(self):
        self.state.phase = Phase.VOTE
        for pid, player in self.players.items():
            target = player.vote(self.state)
            self.state.votes[pid] = target
            print(f"  {pid} → {target} に投票")


def _weighted_choice(scores: dict[str, float]) -> str:
    """スコアを重みとした確率的選択。"""
    total = sum(scores.values())
    if total <= 0:
        return random.choice(list(scores.keys()))
    r = random.random() * total
    cumsum = 0.0
    for pid, score in scores.items():
        cumsum += score
        if r <= cumsum:
            return pid
    return list(scores.keys())[-1]
