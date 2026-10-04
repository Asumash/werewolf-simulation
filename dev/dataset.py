"""対戦ログ（data/*.jsonl）を発言単位で読み出す共通ローダ。

turing_eval（人間らしさ評価）と export_training（学習データ出力）が共有する。
各発言を「それまでの議論（文脈）」付きで取り出せる。
"""
from __future__ import annotations
import glob
import json
import os

VILLAGE = {"村人", "占い師", "怪盗"}


def iter_statements(directory: str = "data/", min_schema: int = 2,
                    types: set | None = None, limit_games: int | None = None):
    """各ゲームの発言を、直前までの文脈つきで yield する。

    types を指定すると、その player_type（human/cpu/llm）だけを返す。
    yield される dict:
      game_id, order, player_id, player_type, model, role,
      statement, context(それまでの発言ログ文字列), others(他プレイヤーID)
    """
    files = sorted(glob.glob(os.path.join(directory, "game_*.jsonl")),
                   key=os.path.getmtime, reverse=True)
    ng = 0
    for fp in files:
        try:
            recs = [json.loads(l) for l in open(fp, encoding="utf-8") if l.strip()]
        except Exception:
            continue
        meta = next((r for r in recs if r.get("type") == "meta"), None)
        if not meta or meta.get("schema_version", 1) < min_schema:
            continue
        all_players = meta.get("players", [])
        stmts = [r for r in recs if r.get("type") == "statement"]
        prior: list[str] = []
        for s in stmts:
            rec = {
                "game_id": s.get("game_id"),
                "order": s.get("order"),
                "player_id": s.get("player_id"),
                "player_type": s.get("player_type", "cpu"),
                "model": s.get("model"),
                "role": s.get("role"),
                "statement": s.get("statement", ""),
                "context": "\n".join(prior) if prior else "（まだ発言なし）",
                "others": [p for p in all_players if p != s.get("player_id")],
            }
            if types is None or rec["player_type"] in types:
                yield rec
            prior.append(f"  {s.get('player_id')}: {s.get('statement','')}")
        ng += 1
        if limit_games and ng >= limit_games:
            break


def count_by_type(directory: str = "data/", min_schema: int = 2) -> dict:
    """player_type ごとの発言数を数える（データの把握用）。"""
    counts: dict[str, int] = {}
    for rec in iter_statements(directory, min_schema=min_schema):
        counts[rec["player_type"]] = counts.get(rec["player_type"], 0) + 1
    return counts
