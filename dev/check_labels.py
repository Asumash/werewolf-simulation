"""交換が起きたゲームの発言レコードで3種のroleフィールドを表示する。"""
from __future__ import annotations
import json
from pathlib import Path

for path in sorted(Path("data").glob("game_*.jsonl")):
    records = [json.loads(l) for l in open(path, encoding="utf-8")]
    statements = [r for r in records if r["type"] == "statement"]

    # 元人狼が怪盗ラベルで人狼として行動しているケースを探す
    target = next(
        (r for r in statements
         if r["original_role"] == "人狼"
         and r["true_role"] == "怪盗"
         and "人狼なので" in r.get("reasoning", "")),
        None,
    )
    if not target:
        continue

    meta = next(r for r in records if r["type"] == "meta")
    print(f"=== {path.name} ===")
    print(f"  original_role_map: {meta['original_role_map']}")
    print(f"  role_map(交換後):   {meta['role_map']}")
    print()
    print("  プレイヤー | role(信じている) | true_role(現在) | original_role(配布時)")
    for pid in meta["players"]:
        s = next((r for r in statements if r["player_id"] == pid), None)
        if s:
            print(f"  {pid:8} | {s['role']:16} | {s['true_role']:15} | {s['original_role']}")
    print()
    print(f"  結果: {meta['result']}")
    print()
    break
