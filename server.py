from __future__ import annotations
import asyncio
import json
import os
import random
import string
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from engine.game_state import GameState, Role
from engine.game_runner_async import AsyncGameRunner
from players.rule_based import RuleBasedCP
from players.human_ws import HumanWSPlayer
from players.llm_player import AsyncLLMPlayer

app = FastAPI()

ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]

rooms: dict[str, "Room"] = {}


def gen_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=4))


class Room:
    def __init__(self, code: str, host: str):
        self.code = code
        self.host = host
        self.connections: dict[str, WebSocket] = {}
        self.human_players: dict[str, HumanWSPlayer] = {}
        self.runner: AsyncGameRunner | None = None
        self.started = False
        self.llm_count = 0  # AI席のうち LLM にする人数（ホストが設定）

    async def broadcast(self, msg: dict):
        data = json.dumps(msg, ensure_ascii=False)
        dead: list[str] = []
        for name, ws in self.connections.items():
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(name)
        for name in dead:
            self.connections.pop(name, None)

    async def send_private(self, player_id: str, msg: dict):
        ws = self.connections.get(player_id)
        if ws:
            try:
                await ws.send_text(json.dumps(msg, ensure_ascii=False))
            except Exception:
                pass

    def player_list(self) -> list[str]:
        return list(self.connections.keys())


# ── エンドポイント ──────────────────────────────────────────────────────────

static_dir = Path(__file__).parent / "web" / "static"


@app.get("/")
async def index():
    return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))


@app.get("/room/create")
async def create_room(host: str):
    code = gen_code()
    while code in rooms:
        code = gen_code()
    rooms[code] = Room(code, host)
    return {"code": code}


@app.websocket("/ws/{room_code}/{player_name}")
async def ws_endpoint(ws: WebSocket, room_code: str, player_name: str):
    await ws.accept()

    if room_code not in rooms:
        await ws.send_text(json.dumps({"type": "error", "message": "ルームが存在しません"}))
        await ws.close()
        return

    room = rooms[room_code]

    if room.started:
        await ws.send_text(json.dumps({"type": "error", "message": "ゲームはすでに開始されています"}))
        await ws.close()
        return

    if len(room.connections) >= 5:
        await ws.send_text(json.dumps({"type": "error", "message": "ルームが満員です（最大5人）"}))
        await ws.close()
        return

    room.connections[player_name] = ws
    await room.broadcast({
        "type": "player_joined",
        "name": player_name,
        "players": room.player_list(),
        "host": room.host,
    })

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            await _handle_message(room, player_name, msg)
    except WebSocketDisconnect:
        room.connections.pop(player_name, None)
        if room.started:
            # ゲーム中に切断された場合、待機中のフェーズ（夜・投票）が止まらないよう
            # デフォルト行動を投入して進行を継続させる。
            _release_disconnected_player(room, player_name)
            await room.broadcast({
                "type": "system",
                "message": f"{player_name} が切断しました（以降は自動進行）",
            })
        else:
            await room.broadcast({
                "type": "player_left",
                "name": player_name,
                "players": room.player_list(),
                "host": room.host,
            })
        if not room.connections and not room.started:
            rooms.pop(room_code, None)


# ── メッセージハンドラ ──────────────────────────────────────────────────────

async def _handle_message(room: Room, player_name: str, msg: dict):
    mtype = msg.get("type")

    if mtype == "start_game":
        if player_name != room.host or room.started:
            return
        asyncio.create_task(_run_game(room))

    elif mtype == "set_llm_count":
        # ホストのみ・開始前。AI席のうち LLM にする人数を設定
        if player_name == room.host and not room.started:
            try:
                n = int(msg.get("count", 0))
            except (TypeError, ValueError):
                n = 0
            room.llm_count = max(0, min(4, n))
            await room.broadcast({
                "type": "lobby_config",
                "llm_count": room.llm_count,
                "host": room.host,
            })

    elif mtype == "night_action":
        player = room.human_players.get(player_name)
        if player:
            await player.night_queue.put(msg.get("action", {"action": "none"}))

    elif mtype == "statement":
        # 議論中なら即座に処理（チャット形式）
        if room.runner and room.runner.discussion_active:
            text = msg.get("text", "").strip()
            if not text:
                return
            intent = msg.get("intent", "none") or "none"
            target = msg.get("target", "") or ""
            result = msg.get("result", "") or ""
            basis = msg.get("basis", []) or []
            if not isinstance(basis, list):
                basis = []
            # ランナー経由で追加（CPUの反応・沈黙判定の基準時刻も更新される）
            await room.runner.submit_human_statement(
                player_name, text, intent=intent, target=target,
                result=result, basis=basis,
            )

    elif mtype == "vote":
        player = room.human_players.get(player_name)
        if player:
            await player.vote_queue.put(msg.get("target"))


def _release_disconnected_player(room: "Room", player_name: str):
    """ゲーム中に切断された人間の待機フェーズ（夜・投票）を止めないよう、
    デフォルト行動をキューに投入して進行を継続させる。"""
    player = room.human_players.get(player_name)
    if not player:
        return
    others = [p for p in (room.runner.state.player_ids if room.runner else [])
              if p != player_name]
    # 夜行動＝なし、投票＝ランダムな他プレイヤー（未行動なら消費され、行動済みなら無害）
    try:
        player.night_queue.put_nowait({"action": "none"})
    except Exception:
        pass
    try:
        player.vote_queue.put_nowait(random.choice(others) if others else player_name)
    except Exception:
        pass


# ── ゲーム実行 ──────────────────────────────────────────────────────────────

async def _run_game(room: Room):
    room.started = True
    await room.broadcast({"type": "game_starting"})
    await asyncio.sleep(1)

    human_ids = room.player_list()
    ai_slots = max(0, 5 - len(human_ids))

    # AI席を LLM と ルールベースCP に振り分ける
    llm_n = min(room.llm_count, ai_slots)
    if llm_n > 0 and not os.environ.get("OPENROUTER_API_KEY"):
        await room.broadcast({
            "type": "system",
            "message": "OPENROUTER_API_KEY が未設定のため、LLMをCPUに置き換えました。",
        })
        llm_n = 0
    llm_ids = [f"LLM-{i + 1}" for i in range(llm_n)]
    cpu_ids = [f"CPU-{i + 1}" for i in range(ai_slots - llm_n)]
    all_ids = (human_ids + llm_ids + cpu_ids)[:5]

    players = []
    room.human_players = {}
    for pid in all_ids:
        if pid in human_ids:
            p = HumanWSPlayer(pid)
            room.human_players[pid] = p
        elif pid.startswith("LLM-"):
            p = AsyncLLMPlayer(pid)
        else:
            p = RuleBasedCP(pid)
        players.append(p)

    state = GameState(player_ids=all_ids)
    state.setup(ROLE_LIST)

    for pid in human_ids:
        if pid in all_ids:
            await room.send_private(pid, {
                "type": "role_assigned",
                "role": state.original_role_map[pid].value,
                "all_players": all_ids,
            })

    runner = AsyncGameRunner(
        state=state,
        players=players,
        broadcast=room.broadcast,
        send_private=room.send_private,
    )
    room.runner = runner
    result = await runner.run()
    room.runner = None

    await room.broadcast({
        "type": "game_over",
        "winner": result["winner"],
        "executed": result.get("executed", []),
        "roles": {pid: state.role_map[pid].value for pid in all_ids},
        "original_roles": {pid: state.original_role_map[pid].value for pid in all_ids},
        "votes": state.votes,
    })

    room.started = False
    room.human_players = {}


if __name__ == "__main__":
    import uvicorn
    import socket
    host_ip = socket.gethostbyname(socket.gethostname())
    print(f"\n同じ Wi-Fi 内の端末は http://{host_ip}:8000 でアクセスできます\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
