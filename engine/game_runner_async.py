from __future__ import annotations
import asyncio
import random
import traceback
from typing import Callable, Awaitable
from engine.game_state import GameState, Phase, Role, Turn
from players.base import PlayerInterface
from engine.game_runner import NIGHT_ORDER


class AsyncGameRunner:
    def __init__(
        self,
        state: GameState,
        players: list[PlayerInterface],
        broadcast: Callable[[dict], Awaitable[None]],
        send_private: Callable[[str, dict], Awaitable[None]],
        discussion_seconds: int = 120,
    ):
        self.state = state
        self.players = {p.player_id: p for p in players}
        self.broadcast = broadcast
        self.send_private = send_private
        self.discussion_seconds = discussion_seconds
        self.discussion_active = False
        # リアルタイム発話スケジューリング用（モノトニック時刻）
        self._last_msg_time: float = 0.0        # 直近に誰かが発言した時刻
        self._last_spoke: dict[str, float] = {}  # CPUごとの直近発言時刻
        self._cpu_sched: dict[str, float] = {}   # CPUごとの次回発言予定時刻

    async def run(self) -> dict:
        await self.broadcast({"type": "phase", "phase": "night"})
        await self._night_phase()
        await self._send_night_results()
        await asyncio.sleep(2)

        await self.broadcast({
            "type": "phase",
            "phase": "discussion",
            "duration": self.discussion_seconds,
        })
        self.discussion_active = True
        await self._discussion_phase()
        self.discussion_active = False

        await self.broadcast({"type": "phase", "phase": "vote"})
        await self._vote_phase()

        return self.state.judge_result()

    # ── 夜フェーズ ───────────────────────────────────────────────────────

    async def _night_phase(self):
        self.state.phase = Phase.NIGHT
        for role in NIGHT_ORDER:
            for pid, player in self.players.items():
                if self.state.original_role_map[pid] == role:
                    if hasattr(player, "night_action_async"):
                        action = await player.night_action_async(self.state, self.send_private)
                    else:
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

    async def _send_night_results(self):
        for pid, player in self.players.items():
            if not hasattr(player, "night_queue"):
                continue
            original_role = self.state.original_role_map[pid]
            knowledge = self.state.knowledge.get(pid, {})
            payload: dict = {}
            if original_role == Role.SEER:
                if "saw_player" in knowledge:
                    target, role_val = list(knowledge["saw_player"].items())[0]
                    payload = {"type": "saw_player", "target": target, "role": role_val}
                elif "saw_graveyard" in knowledge:
                    payload = {"type": "saw_graveyard", "roles": knowledge["saw_graveyard"]}
            elif original_role == Role.ROBBER:
                if "new_role" in knowledge:
                    payload = {
                        "type": "swapped",
                        "with": knowledge.get("swapped_with", ""),
                        "new_role": knowledge["new_role"],
                    }
            elif original_role == Role.WEREWOLF:
                allies = [
                    p for p in self.state.player_ids
                    if self.state.original_role_map[p] == Role.WEREWOLF and p != pid
                ]
                payload = {"type": "allies", "allies": allies}
            await self.send_private(pid, {"type": "night_result", "knowledge": payload})

    # ── 議論フェーズ ─────────────────────────────────────────────────────

    def _now(self) -> float:
        return asyncio.get_running_loop().time()

    def _holds_info(self, pid: str) -> bool:
        """情報役職（占い師・怪盗）か（初回発話をやや前倒しする判定用）。"""
        return self.state.original_role_map[pid] in (Role.SEER, Role.ROBBER)

    async def _discussion_phase(self):
        self.state.phase = Phase.DISCUSSION
        now = self._now()
        self._last_msg_time = now

        cpu_players = [
            (pid, p) for pid, p in self.players.items()
            if not hasattr(p, "night_queue")  # CPU のみ
        ]

        # 初回発話予定：役職に依存しないランダム初期遅延（役職バレ防止）
        # 情報保持者は「決定的でない」程度に前倒し
        for pid, p in cpu_players:
            speed = getattr(p, "speed", 1.0)
            base = random.uniform(4, 16) * speed
            if self._holds_info(pid):
                base -= random.uniform(2, 6)
            self._cpu_sched[pid] = now + max(1.5, base)
            self._last_spoke[pid] = now - 999  # 初回はクールダウンに引っかからない

        cpu_tasks = [
            asyncio.create_task(self._cpu_speak_loop(pid, p), name=f"cpu-{pid}")
            for pid, p in cpu_players
        ]
        print(f"[Runner] 議論フェーズ開始 {self.discussion_seconds}秒 / CPUタスク数={len(cpu_tasks)}")

        await asyncio.sleep(self.discussion_seconds)

        print("[Runner] 議論フェーズ終了 → CPUタスクをキャンセル")
        for task in cpu_tasks:
            task.cancel()
        if cpu_tasks:
            await asyncio.wait(cpu_tasks, timeout=3.0)
        print("[Runner] 投票フェーズへ移行")

    async def _cpu_speak_loop(self, pid: str, player: PlayerInterface):
        """イベント駆動でCPUが発言するループ。

        短い間隔でティックし、そのたびに urge（話したい度）を再評価する。
        疑われた・質問された・矛盾を見つけた等のトリガーで発話予定を前倒しする。
        """
        try:
            while True:
                await asyncio.sleep(random.uniform(0.8, 1.6))  # ティック
                now = self._now()
                since_my_last = now - self._last_spoke.get(pid, now - 999)
                since_any = now - self._last_msg_time

                try:
                    urge, trigger = player.speak_urge(self.state, since_my_last, since_any)
                except Exception:
                    urge, trigger = 0.5, "base"

                # 反応トリガーは発話予定を前倒し（会話の「返し」）
                if trigger in ("expose", "defend", "rebut", "answer"):
                    pull = now + random.uniform(1.5, 4.0)
                    self._cpu_sched[pid] = min(self._cpu_sched.get(pid, pull), pull)
                elif trigger == "fill":
                    pull = now + random.uniform(0.0, 2.5)
                    self._cpu_sched[pid] = min(self._cpu_sched.get(pid, pull), pull)

                # まだ発話予定時刻に達していない
                if now < self._cpu_sched.get(pid, now):
                    continue

                # クールダウン（自分の直近発言からの最低間隔）
                min_cd = 2.5 if trigger in ("defend", "expose", "rebut") else 5.0
                if since_my_last < min_cd:
                    self._cpu_sched[pid] = now + random.uniform(1.5, 3.0)
                    continue

                # 低 urge のときは確率的に見送り、無言の「間」を作る
                if urge < 1.0 and random.random() < 0.5:
                    self._cpu_sched[pid] = now + random.uniform(5, 12)
                    continue

                # 発言生成（trigger に応じた文脈依存発言）
                # LLM は非同期メソッドを await（ブロックせず生成）
                is_llm = hasattr(player, "make_reactive_statement_async")
                try:
                    if is_llm:
                        statement, reasoning = await player.make_reactive_statement_async(
                            self.state, trigger)
                    else:
                        statement, reasoning = player.make_reactive_statement(
                            self.state, trigger)
                except Exception as e:
                    print(f"[{pid}] make_reactive_statement error: {e}")
                    traceback.print_exc()
                    try:
                        statement, reasoning = player.make_statement(self.state)
                    except Exception:
                        self._cpu_sched[pid] = now + random.uniform(5, 12)
                        continue

                if not statement:
                    self._cpu_sched[pid] = now + random.uniform(5, 12)
                    continue

                # 反復回避：直前の自分の発言と同一なら見送り
                if statement == self._my_last_text(pid):
                    self._cpu_sched[pid] = now + random.uniform(6, 12)
                    continue

                # LLM が返した構造化タグを belief に直結（infer_tags を通さない）
                tags = getattr(player, "last_tags", None)
                source = "llm" if is_llm else "cpu"
                if tags:
                    intent, target, result, basis = tags
                    await self._emit_statement(
                        pid, statement, reasoning, is_cpu=True, source=source,
                        intent=intent, target=target, result=result, basis=basis)
                    player.last_tags = None
                else:
                    await self._emit_statement(
                        pid, statement, reasoning, is_cpu=True, source=source)
                if hasattr(player, "remember_statement"):
                    player.remember_statement(statement)

                # 次回発話予定（発言回数が増えるほど間隔を延ばす）
                my_count = sum(
                    1 for t in self.state.discussion_log if t.player_id == pid
                )
                speed = getattr(player, "speed", 1.0)
                talk = getattr(player, "talkativeness", 1.0)
                gap = random.uniform(12, 26) * speed * (1 + my_count * 0.25) / max(0.5, talk)
                self._cpu_sched[pid] = now + gap
                print(f"[CPU {pid}] 発言({trigger}): {statement[:50]}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[CPU {pid}] 予期しないエラー: {e}")
            traceback.print_exc()

    def _my_last_text(self, pid: str) -> str | None:
        """指定プレイヤーの直近発言テキスト（無ければ None）。"""
        for t in reversed(self.state.discussion_log):
            if t.player_id == pid:
                return t.statement
        return None

    async def _emit_statement(
        self, pid: str, statement: str, reasoning: str, is_cpu: bool,
        intent: str | None = None, target: str = "", result: str = "",
        basis: list[str] | None = None, source: str = "cpu",
    ):
        """発言を GameState に追加し、タイミング情報を更新してブロードキャストする。

        CPU・人間の両方がこの経路を通ることで、沈黙判定や反応の基準時刻が
        一元管理される。
        """
        basis = basis or []
        if intent is None:
            # CPU 発言は論拠(basis)を付けない（basis は人間/LLM のみ供給）
            from players.rule_based import infer_tags
            intent, target, result = infer_tags(statement, self.state.player_ids, pid)

        try:
            is_lie = self._detect_lie(pid, statement)
        except Exception:
            is_lie = False

        self.state.add_statement(
            Turn(player_id=pid, statement=statement, reasoning=reasoning,
                 is_lie=is_lie, intent=intent, target=target, result=result,
                 basis=basis)
        )
        now = self._now()
        self._last_msg_time = now
        if is_cpu:
            self._last_spoke[pid] = now

        await self.broadcast({
            "type": "statement",
            "player": pid,
            "text": statement,
            "intent": intent,
            "target": target,
            "result": result,
            "basis": basis,
            "is_cpu": is_cpu,
            "source": source,
        })

    async def submit_human_statement(
        self, pid: str, text: str, intent: str = "none",
        target: str = "", result: str = "", basis: list[str] | None = None,
    ):
        """人間の発言を受け取り、CPUと同じ経路で処理する。"""
        await self._emit_statement(
            pid, text, "", is_cpu=False, source="human",
            intent=intent, target=target, result=result, basis=basis or [],
        )

    def _detect_lie(self, pid: str, statement: str) -> bool:
        from recorder.recorder import _believed_role
        believed = _believed_role(pid, self.state)
        for role_name in ["人狼", "占い師", "怪盗", "村人"]:
            if f"私は{role_name}" in statement and role_name != believed:
                return True
        if "占い師です" in statement and "占い師" != believed:
            return True
        if "怪盗です" in statement and "交換しました" in statement and "怪盗" != believed:
            return True
        return False

    # ── 投票フェーズ ────────────────────────────────────────────────────

    async def _vote_phase(self):
        self.state.phase = Phase.VOTE

        async def get_vote(pid: str, player: PlayerInterface):
            candidates = [p for p in self.state.player_ids if p != pid]
            if hasattr(player, "vote_async"):
                await self.send_private(pid, {
                    "type": "vote_request",
                    "candidates": candidates,
                })
                return pid, await player.vote_async(self.state)
            return pid, player.vote(self.state)

        results = await asyncio.gather(
            *[get_vote(pid, p) for pid, p in self.players.items()]
        )
        for pid, target in results:
            self.state.votes[pid] = target
            await self.broadcast({"type": "vote_cast", "voter": pid, "target": target})
            await asyncio.sleep(0.3)
