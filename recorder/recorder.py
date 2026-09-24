from __future__ import annotations
import json
import uuid
from pathlib import Path
from datetime import datetime
from engine.game_state import GameState, Role


def _believed_role(pid: str, state: GameState) -> str:
    """
    プレイヤーが「自分の役職」だと信じている役職を返す。
    RuleBasedCP._get_believed_role() と同じロジック。

    - 怪盗として交換し、人狼を得た場合 → "人狼"（スワップを隠して人狼行動）
    - 怪盗として交換し、それ以外を得た場合 → "怪盗"（怪盗としてCOして行動）
    - 交換された側（通知なし）        → original_role_map の値
    """
    knowledge = state.knowledge[pid]
    if "new_role" in knowledge:
        if knowledge["new_role"] == Role.WEREWOLF.value:
            return Role.WEREWOLF.value   # 人狼として行動
        return Role.ROBBER.value         # 怪盗として行動（スワップCO）
    return state.original_role_map[pid].value


def player_type(player) -> str:
    """プレイヤーオブジェクトの種別を推定する（human / llm / cpu）。

    プレイヤークラスを import せず、特徴（ダックタイピング）で判定する。
    """
    if hasattr(player, "night_queue"):
        return "human"
    if hasattr(player, "model"):
        return "llm"
    return "cpu"


class GameRecorder:
    SCHEMA_VERSION = 2

    def __init__(self, output_dir: str = "data/"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: GameState, result: dict, players: dict | None = None) -> Path:
        """1ゲームを JSONL で保存する。

        players: {player_id: プレイヤーオブジェクト} を渡すと、各プレイヤーの
        種別（human/cpu/llm）とモデル名も記録する（human/CPU/LLM 共通スキーマ）。
        """
        game_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"game_{timestamp}_{game_id}.jsonl"

        # プレイヤー種別・モデル名
        players = players or {}
        players_meta = {
            pid: {
                "type": player_type(p),
                "model": getattr(p, "model", None),
            }
            for pid, p in players.items()
        }

        def _ptype(pid):
            return players_meta.get(pid, {}).get("type", "cpu")

        def _pmodel(pid):
            return players_meta.get(pid, {}).get("model")

        records = []

        # ゲームメタデータ
        records.append({
            "type": "meta",
            "schema_version": self.SCHEMA_VERSION,
            "game_id": game_id,
            "timestamp": timestamp,
            "players": state.player_ids,
            "players_meta": players_meta,
            # 交換後の真の役職（勝敗判定はこれに基づく）
            "role_map": {pid: role.value for pid, role in state.role_map.items()},
            # 配布時の役職（参照用）
            "original_role_map": {
                pid: role.value for pid, role in state.original_role_map.items()
            },
            "graveyard": [r.value for r in state.graveyard],
            "result": result,
        })

        # 発言ログ（学習データ・分析用）
        for order, turn in enumerate(state.discussion_log):
            pid = turn.player_id
            records.append({
                "type": "statement",
                "game_id": game_id,
                "order": order,
                "player_id": pid,
                "player_type": _ptype(pid),
                "model": _pmodel(pid),
                # 学習データのラベル: プレイヤーが信じている役職
                "role": _believed_role(pid, state),
                # 参照用: 交換後の真の役職
                "true_role": state.role_map[pid].value,
                # 参照用: 配布時の役職
                "original_role": state.original_role_map[pid].value,
                "statement": turn.statement,
                # 構造化された行動タグ（人間/CPU/LLM 共通の行動言語）
                "intent": getattr(turn, "intent", "") or "",
                "target": getattr(turn, "target", "") or "",
                "result": getattr(turn, "result", "") or "",
                "basis": getattr(turn, "basis", []) or [],
                "reasoning": turn.reasoning,
                "is_lie": turn.is_lie,
                "knowledge": state.knowledge[pid],
            })

        # 投票ログ
        for voter, target in state.votes.items():
            records.append({
                "type": "vote",
                "game_id": game_id,
                "voter": voter,
                "voter_type": _ptype(voter),
                # 投票者が信じている自分の役職
                "voter_role": _believed_role(voter, state),
                "voter_true_role": state.role_map[voter].value,
                "target": target,
            })

        with open(filepath, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        print(f"[Recorder] 保存: {filepath}")
        return filepath

    def to_finetuning_format(self, jsonl_path: str) -> list[dict]:
        """
        JSONLファイルをファインチューニング用のmessages形式に変換する。
        role フィールドは「プレイヤーが信じている役職」を使用。
        """
        samples = []
        with open(jsonl_path, encoding="utf-8") as f:
            records = [json.loads(line) for line in f]

        statements = [r for r in records if r["type"] == "statement"]

        for i, stmt in enumerate(statements):
            prior_log = "\n".join(
                f"  {s['player_id']}: {s['statement']}"
                for s in statements[:i]
            ) or "  （まだ発言なし）"

            user_content = (
                f"人狼ゲーム。あなたは「{stmt['player_id']}」"
                f"（役職: {stmt['role']}）です。\n"
                f"【夜に得た情報】{stmt['knowledge'] or 'なし'}\n"
                f"【これまでの議論】\n{prior_log}\n\n"
                f"発言とその理由をJSONで返してください。"
            )

            assistant_content = json.dumps({
                "statement": stmt["statement"],
                "reasoning": stmt["reasoning"],
            }, ensure_ascii=False)

            samples.append({
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ]
            })

        return samples
