from __future__ import annotations
import asyncio
import json
import os
import random
import urllib.request
import urllib.error

from players.base import PlayerInterface
from engine.game_state import GameState, Role
from prompts.templates import (
    build_night_prompt, build_statement_prompt, build_vote_prompt,
)

# 有効な intent（LLM 出力のサニタイズ用）
_VALID_INTENTS = {
    "seer_result", "robber_result", "suspect", "vote_suggest",
    "contradict", "vouch", "ask", "none",
}

# .env があれば読み込む（python-dotenv 利用可能な場合）
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class LLMPlayer(PlayerInterface):
    """OpenAI 互換 Chat Completions API（OpenRouter / OpenAI 直）で駆動するプレイヤー。

    - base_url と api_key_env を差し替えるだけで OpenRouter / OpenAI を切替可能。
    - 標準ライブラリ urllib のみで実装（追加依存なし・Python 3.8対応）。
    - API 失敗時は安全なフォールバック（発言スキップ・ランダム投票）で
      ゲームを止めない。
    - LLM が返した構造化タグ（intent/target/result/basis）は last_action /
      action_log に保持し、将来の非同期・belief 連携に使う。
    """

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "openai/gpt-4o-mini"

    def __init__(
        self,
        player_id: str,
        model: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        temperature: float = 0.7,
        timeout: float = 30.0,
    ):
        super().__init__(player_id)
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL")
                         or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = (model or os.environ.get("OPENROUTER_MODEL")
                      or self.DEFAULT_MODEL)
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.timeout = timeout
        self.last_action: dict = {}
        self.action_log: list[dict] = []   # 構造化出力の履歴（検証・学習データ用）
        self.errors: list[str] = []

    # ---------- HTTP ----------

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"環境変数 {self.api_key_env} が未設定です（.env か export で設定してください）"
            )
        return key

    def _chat(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": 500,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
                # OpenRouter 推奨（任意）
                "HTTP-Referer": "http://localhost",
                "X-Title": "werewolf-cpu-study",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _extract_json(text: str) -> dict:
        """LLM 出力から最初の JSON オブジェクトを取り出してパースする。"""
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")
            if t.lower().startswith("json"):
                t = t[4:]
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            t = t[i:j + 1]
        return json.loads(t)

    def _call_json(self, prompt: str) -> dict:
        raw = self._chat(prompt)
        return self._extract_json(raw)

    # ---------- 夜行動 ----------

    def night_action(self, state: GameState) -> dict:
        role = state.original_role_map[self.player_id]
        if role not in (Role.SEER, Role.ROBBER):
            return {"action": "none"}
        others = [p for p in state.player_ids if p != self.player_id]
        try:
            data = self._call_json(build_night_prompt(self.player_id, state))
        except Exception as e:
            self.errors.append(f"night: {e}")
            # フォールバック：占い=誰か / 怪盗=交換
            if role == Role.SEER:
                return {"action": "see_player", "target": random.choice(others)}
            return {"action": "swap", "target": random.choice(others)}

        action = data.get("action", "none")
        target = data.get("target", "")
        if action in ("see_player", "swap") and target not in others:
            target = random.choice(others)
        if action == "see_player":
            return {"action": "see_player", "target": target}
        if action == "see_graveyard":
            return {"action": "see_graveyard"}
        if action == "swap":
            return {"action": "swap", "target": target}
        if action == "skip":
            return {"action": "skip"}
        return {"action": "none"}

    # ---------- 発言重要度（API を呼ばない軽量ヒューリスティック）----------

    def get_urgency_score(self, state: GameState) -> float:
        my = sum(1 for t in state.discussion_log if t.player_id == self.player_id)
        return 2.0 if my == 0 else max(0.3, 1.5 * (0.6 ** my))

    # ---------- 発言生成 ----------

    def make_statement(self, state: GameState) -> tuple[str, str]:
        try:
            data = self._call_json(build_statement_prompt(self.player_id, state))
        except Exception as e:
            self.errors.append(f"statement: {e}")
            return "少し様子を見ます。", "API失敗のためフォールバック"
        # 構造化タグを保持（intent/target/result/basis）
        self.last_action = data
        self.action_log.append(data)
        statement = str(data.get("statement", "")).strip()
        reasoning = str(data.get("reasoning", "")).strip()
        if not statement:
            statement = "少し様子を見ます。"
        return statement, reasoning

    # ---------- 投票 ----------

    def vote(self, state: GameState) -> str:
        others = [p for p in state.player_ids if p != self.player_id]
        try:
            data = self._call_json(build_vote_prompt(self.player_id, state))
        except Exception as e:
            self.errors.append(f"vote: {e}")
            return random.choice(others)
        target = str(data.get("vote_target", "")).strip()
        return target if target in others else random.choice(others)


class AsyncLLMPlayer(LLMPlayer):
    """非同期ランナー（リアルタイムweb対戦）向けの LLM プレイヤー。

    - ブロッキングな urllib 呼び出しを run_in_executor でスレッドに逃がし、
      イベントループ（他プレイヤーの発話ループ）を止めない。
    - night_queue を持たないため、ランナーは「自律発話プレイヤー」として扱う。
    - 発話タイミング(speak_urge)は API を呼ばない軽量ヒューリスティック。
    - 発話内容は LLM が返す構造化タグ {intent,target,result,basis} を
      last_tags に格納し、belief へ直結させる。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_tags: tuple | None = None

    async def _chat_async(self, prompt: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._chat, prompt)

    async def _call_json_async(self, prompt: str) -> dict:
        return self._extract_json(await self._chat_async(prompt))

    # ── 夜行動（非同期）──
    async def night_action_async(self, state: GameState, send_private=None) -> dict:
        role = state.original_role_map[self.player_id]
        if role not in (Role.SEER, Role.ROBBER):
            return {"action": "none"}
        others = [p for p in state.player_ids if p != self.player_id]
        try:
            data = await self._call_json_async(build_night_prompt(self.player_id, state))
        except Exception as e:
            self.errors.append(f"night: {e}")
            if role == Role.SEER:
                return {"action": "see_player", "target": random.choice(others)}
            return {"action": "swap", "target": random.choice(others)}
        action = data.get("action", "none")
        target = data.get("target", "")
        if action in ("see_player", "swap") and target not in others:
            target = random.choice(others)
        if action == "see_player":
            return {"action": "see_player", "target": target}
        if action == "see_graveyard":
            return {"action": "see_graveyard"}
        if action == "swap":
            return {"action": "swap", "target": target}
        if action == "skip":
            return {"action": "skip"}
        return {"action": "none"}

    # ── 発話タイミング（API を呼ばない）──
    def speak_urge(self, state: GameState, since_my_last: float,
                   since_any_msg: float) -> tuple[float, str]:
        log = state.discussion_log
        me = self.player_id
        my_idxs = [i for i, t in enumerate(log) if t.player_id == me]
        recent = log[(my_idxs[-1] + 1) if my_idxs else 0:]
        for t in recent:
            if t.player_id == me:
                continue
            intent = getattr(t, "intent", "") or ""
            tgt = getattr(t, "target", "") or ""
            if intent in ("suspect", "vote_suggest", "contradict") and tgt == me:
                return 4.0, "defend"
            if intent == "ask" and tgt == me:
                return 3.0, "answer"
        my = len(my_idxs)
        role = state.original_role_map.get(me)
        if my == 0 and role in (Role.SEER, Role.ROBBER):
            return 2.5, "co"
        if my == 0:
            return 1.5, "open"
        if since_any_msg > 8.0:
            return 1.3, "fill"
        return max(0.4, 1.5 * (0.6 ** my)), "base"

    def _sanitize_tags(self, state: GameState, data: dict) -> tuple:
        others = [p for p in state.player_ids if p != self.player_id]
        intent = data.get("intent", "none")
        if intent not in _VALID_INTENTS:
            intent = "none"
        target = str(data.get("target", "") or "")
        if target not in others:
            target = ""
        result = str(data.get("result", "") or "")
        if intent not in ("seer_result", "robber_result"):
            result = ""
        basis = [b for b in (data.get("basis") or []) if b in state.player_ids]
        return (intent, target, result, basis)

    # ── 発話内容（非同期・構造化タグ付き）──
    async def make_reactive_statement_async(
        self, state: GameState, trigger: str
    ) -> tuple[str, str]:
        hint = {
            "defend": "直前にあなたは疑われています。必要なら反論してください。",
            "answer": "直前にあなたは質問されています。答えてください。",
            "co": "あなたは情報役職です。結果をCOすると有利です。",
        }.get(trigger, "")
        try:
            data = await self._call_json_async(
                build_statement_prompt(self.player_id, state, hint=hint)
            )
        except Exception as e:
            self.errors.append(f"statement: {e}")
            self.last_tags = ("none", "", "", [])
            return "少し様子を見ます。", "API失敗のためフォールバック"
        self.last_action = data
        self.action_log.append(data)
        self.last_tags = self._sanitize_tags(state, data)
        statement = str(data.get("statement", "")).strip() or "少し様子を見ます。"
        reasoning = str(data.get("reasoning", "")).strip()
        return statement, reasoning

    # ── 投票（非同期）──
    async def vote_async(self, state: GameState) -> str:
        others = [p for p in state.player_ids if p != self.player_id]
        try:
            data = await self._call_json_async(build_vote_prompt(self.player_id, state))
        except Exception as e:
            self.errors.append(f"vote: {e}")
            return random.choice(others)
        target = str(data.get("vote_target", "")).strip()
        return target if target in others else random.choice(others)
