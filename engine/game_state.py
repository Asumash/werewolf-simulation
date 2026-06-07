from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import random

class Phase(Enum):
    SETUP = "setup"
    NIGHT = "night"
    DISCUSSION = "discussion"
    VOTE = "vote"
    RESULT = "result"

class Role(Enum):
    WEREWOLF = "人狼"
    VILLAGER  = "村人"
    SEER      = "占い師"
    ROBBER    = "怪盗"

@dataclass
class Turn:
    player_id: str
    statement: str
    is_lie: bool = False
    reasoning: str = ""

@dataclass
class GameState:
    player_ids: list[str]
    phase: Phase = Phase.SETUP

    role_map: dict[str, Role] = field(default_factory=dict)
    # 夜フェーズ開始時点の役職スナップショット（怪盗交換前）
    original_role_map: dict[str, Role] = field(default_factory=dict)
    graveyard: list[Role] = field(default_factory=list)

    knowledge: dict[str, dict] = field(default_factory=dict)

    discussion_log: list[Turn] = field(default_factory=list)
    votes: dict[str, str] = field(default_factory=dict)

    def setup(self, role_list: list[Role]):
        """役職をシャッフルして配布。末尾2枚が墓地。"""
        shuffled = role_list[:]
        random.shuffle(shuffled)
        for i, pid in enumerate(self.player_ids):
            self.role_map[pid] = shuffled[i]
            self.knowledge[pid] = {}
        self.graveyard = shuffled[len(self.player_ids):]
        self.original_role_map = dict(self.role_map)
        self.phase = Phase.NIGHT

    def get_public_state(self, for_player_id: str) -> dict:
        """プレイヤーに見せてよい情報だけを返す。"""
        return {
            "my_role": self.role_map[for_player_id].value,
            "my_original_role": self.original_role_map[for_player_id].value,
            "my_knowledge": self.knowledge[for_player_id],
            "players": self.player_ids,
            "discussion_log": [
                {"player": t.player_id, "statement": t.statement}
                for t in self.discussion_log
            ],
            "phase": self.phase.value,
        }

    def apply_seer_action(self, player_id: str, target: str | None):
        """占い師の夜行動。target=Noneなら墓地を見る。"""
        if target:
            role = self.role_map[target]
            self.knowledge[player_id]["saw_player"] = {target: role.value}
        else:
            self.knowledge[player_id]["saw_graveyard"] = [r.value for r in self.graveyard]

    def apply_robber_action(self, player_id: str, target: str | None):
        """怪盗の夜行動。target=Noneなら交換しない。"""
        if target:
            self.role_map[player_id], self.role_map[target] = (
                self.role_map[target], self.role_map[player_id]
            )
            self.knowledge[player_id]["swapped_with"] = target
            self.knowledge[player_id]["new_role"] = self.role_map[player_id].value

    def add_statement(self, turn: Turn):
        self.discussion_log.append(turn)

    def tally_votes(self) -> dict[str, int]:
        counts: dict[str, int] = {pid: 0 for pid in self.player_ids}
        for target in self.votes.values():
            if target in counts:
                counts[target] += 1
        return counts

    def judge_result(self) -> dict:
        counts = self.tally_votes()
        max_votes = max(counts.values())
        executed = [p for p, v in counts.items() if v == max_votes]

        if len(executed) == len(self.player_ids):
            wolves = [p for p, r in self.role_map.items() if r == Role.WEREWOLF]
            winner = "village" if not wolves else "werewolf"
            return {"executed": [], "winner": winner}

        wolf_executed = any(self.role_map[p] == Role.WEREWOLF for p in executed)
        winner = "village" if wolf_executed else "werewolf"
        return {"executed": executed, "winner": winner}
