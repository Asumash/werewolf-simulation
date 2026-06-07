from __future__ import annotations
import json
import anthropic
from players.base import PlayerInterface
from engine.game_state import GameState
from prompts.templates import build_night_prompt, build_statement_prompt, build_vote_prompt

class LLMPlayer(PlayerInterface):
    def __init__(self, player_id: str, model: str = "claude-sonnet-4-6"):
        super().__init__(player_id)
        self.client = anthropic.Anthropic()
        self.model = model

    def _call(self, prompt: str) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        clean = text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(clean)

    def night_action(self, state: GameState) -> dict:
        prompt = build_night_prompt(self.player_id, state)
        return self._call(prompt)

    def make_statement(self, state: GameState) -> tuple[str, str]:
        prompt = build_statement_prompt(self.player_id, state)
        result = self._call(prompt)
        return result.get("statement", ""), result.get("reasoning", "")

    def vote(self, state: GameState) -> str:
        prompt = build_vote_prompt(self.player_id, state)
        result = self._call(prompt)
        return result.get("vote_target", "")
