"""ゲームログを匿名化する。

プレイヤー名を P1〜P5 に置換し、players_meta の type/model 情報を除去する。
匿名化ログを output_dir に保存し、正解ラベルを ground_truth.jsonl に書き出す。

使い方:
    python -m dev.anonymize                            # data/ → data/anon/
    python -m dev.anonymize --input data/ --output data/anon/
    python -m dev.anonymize --games 20261013           # 日付フィルタ
"""
from __future__ import annotations
import argparse
import json
import random
import re
import shutil
from pathlib import Path


def anonymize_game(records: list[dict]) -> tuple[list[dict], dict] | None:
    """1ゲームを匿名化して (anonymized_records, ground_truth) を返す。
    meta レコードがなければ None を返す。

    ground_truth:
        {"game_id": str, "map": {"P1": {"real_name": str, "type": str}}, ...}
    """
    meta = next((r for r in records if r.get("type") == "meta"), None)
    if not meta or "players_meta" not in meta:
        return None

    players: list[str] = meta["players"]
    pmeta: dict = meta["players_meta"]

    # ─ シャッフルして P1〜P5 に割り当て ─
    shuffled = players[:]
    random.shuffle(shuffled)
    name_to_p: dict[str, str] = {name: f"P{i+1}" for i, name in enumerate(shuffled)}
    p_to_name: dict[str, str] = {v: k for k, v in name_to_p.items()}

    # 正解ラベル
    truth = {
        "game_id": meta["game_id"],
        "map": {
            p_label: {
                "real_name": real_name,
                "type": pmeta.get(real_name, {}).get("type", "unknown"),
            }
            for p_label, real_name in p_to_name.items()
        },
    }

    # ─ 全テキスト中の実名を置換する関数 ─
    def sub(text: str) -> str:
        if not isinstance(text, str):
            return text
        # 長い名前から順に置換（短い名前が長い名前の部分文字列になるケース対策）
        # 大文字・小文字どちらでも一致するよう re.sub + IGNORECASE を使用
        for real in sorted(name_to_p, key=len, reverse=True):
            text = re.sub(re.escape(real), name_to_p[real], text, flags=re.IGNORECASE)
        return text

    def sub_list(lst) -> list:
        return [sub(x) if isinstance(x, str) else x for x in (lst or [])]

    def sub_dict_keys(d: dict) -> dict:
        return {sub(k): v for k, v in d.items()}

    # ─ 各レコードを匿名化 ─
    anon_records: list[dict] = []
    for rec in records:
        t = rec.get("type")

        if t == "meta":
            anon = {
                "type": "meta",
                "schema_version": rec.get("schema_version"),
                "game_id": rec["game_id"],
                "timestamp": rec.get("timestamp"),
                "players": [name_to_p[p] for p in players],
                # type/model を除去したメタ（人数情報のみ残す）
                "players_meta": {
                    name_to_p[p]: {"index": i}
                    for i, p in enumerate(shuffled)
                },
                # 役職は判定の参考のため含める（開示情報として扱う）
                "role_map": {name_to_p[p]: v for p, v in rec.get("role_map", {}).items()},
                "original_role_map": {
                    name_to_p[p]: v for p, v in rec.get("original_role_map", {}).items()
                },
                "graveyard": rec.get("graveyard", []),
                "result": {
                    "winner": rec["result"]["winner"],
                    "executed": [name_to_p.get(p, p) for p in rec["result"].get("executed", [])],
                },
            }

        elif t == "statement":
            pid = rec.get("player_id", "")
            anon = {
                "type": "statement",
                "game_id": rec["game_id"],
                "order": rec.get("order"),
                "player_id": name_to_p.get(pid, pid),
                # player_type / model は除去
                "statement": sub(rec.get("statement", "")),
                "intent": rec.get("intent", ""),
                "target": sub(rec.get("target", "")),
                "result": rec.get("result", ""),
                "basis": sub_list(rec.get("basis", [])),
                # reasoning / knowledge / is_lie は推定の手がかりになるため除去
            }

        elif t == "vote":
            voter = rec.get("voter", "")
            target = rec.get("target", "")
            anon = {
                "type": "vote",
                "game_id": rec["game_id"],
                "voter": name_to_p.get(voter, voter),
                "target": name_to_p.get(target, target),
                # voter_type / voter_role は除去
            }

        else:
            anon = rec  # その他はそのまま

        anon_records.append(anon)

    return anon_records, truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/")
    ap.add_argument("--output", default="data/anon/")
    ap.add_argument("--games", default=None,
                    help="ファイル名に含まれる文字列でフィルタ（例: 20261013）")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob("game_*.jsonl"))
    if args.games:
        files = [f for f in files if args.games in f.name]

    truth_path = out_dir / "ground_truth.jsonl"
    truth_path.unlink(missing_ok=True)

    ok = skip = 0
    for fp in files:
        records = [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
        result = anonymize_game(records)
        if result is None:
            print(f"[skip] {fp.name} (meta なし)")
            skip += 1
            continue

        anon_records, truth = result
        out_path = out_dir / fp.name
        with open(out_path, "w", encoding="utf-8") as f:
            for r in anon_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(truth_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(truth, ensure_ascii=False) + "\n")

        types = [truth["map"][p]["type"] for p in sorted(truth["map"])]
        print(f"[ok] {fp.name} → {out_path.name}  types={types}")
        ok += 1

    print(f"\n完了: {ok} ゲーム匿名化 / {skip} スキップ")
    print(f"正解ラベル: {truth_path}")


if __name__ == "__main__":
    main()
