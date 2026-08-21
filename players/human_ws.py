from __future__ import annotations
import asyncio
from players.base import PlayerInterface
from engine.game_state import GameState, Role


class HumanWSPlayer(PlayerInterface):
    """WebSocket 経由で人間の入力を受け取るプレイヤー。"""

    def __init__(self, player_id: str):
        super().__init__(player_id)
        self.night_queue: asyncio.Queue = asyncio.Queue()
        self.statement_queue: asyncio.Queue = asyncio.Queue()
        self.vote_queue: asyncio.Queue = asyncio.Queue()

    # ── 夜フェーズ ───────────────────────────────────────────────────────

    def night_action(self, state: GameState) -> dict:
        return {"action": "none"}

    async def night_action_async(self, state: GameState, send_private) -> dict:
        original_role = state.original_role_map[self.player_id]
        others = [p for p in state.player_ids if p != self.player_id]

        if original_role == Role.SEER:
            await send_private(self.player_id, {
                "type": "night_request",
                "role": "占い師",
                "players": others,
                "can_graveyard": True,
            })
            return await self.night_queue.get()

        if original_role == Role.ROBBER:
            await send_private(self.player_id, {
                "type": "night_request",
                "role": "怪盗",
                "players": others,
                "can_graveyard": False,
            })
            return await self.night_queue.get()

        return {"action": "none"}

    # ── 議論フェーズ ─────────────────────────────────────────────────────

    def get_urgency_score(self, state: GameState) -> float:
        # 人間プレイヤーは高めのスコアで選ばれやすくする
        return 3.0

    def make_statement(self, state: GameState) -> tuple[str, str]:
        return "（発言なし）", ""

    async def make_statement_async(self, state: GameState) -> tuple[str, str]:
        text = await self.statement_queue.get()
        return text, ""

    # ── 投票フェーズ ─────────────────────────────────────────────────────

    def vote(self, state: GameState) -> str:
        return state.player_ids[0]

    async def vote_async(self, state: GameState) -> str:
        return await self.vote_queue.get()
