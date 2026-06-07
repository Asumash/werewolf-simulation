from __future__ import annotations
import json
from pathlib import Path

game_files = list(Path("data").glob("game_*.jsonl"))
print(f"ゲームファイル数: {len(game_files)}")

samples = []
with open("data/finetune_dataset.jsonl", encoding="utf-8") as f:
    for line in f:
        samples.append(json.loads(line))

print(f"学習サンプル数: {len(samples)}")

# 役職別サンプル数を集計
role_counts: dict[str, int] = {}
lie_count = 0
with open("data/finetune_dataset.jsonl", encoding="utf-8") as f:
    pass  # already loaded above

# ゲームファイルから詳細集計
total_lies = 0
total_statements = 0
role_dist: dict[str, int] = {}
for path in game_files:
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["type"] == "statement":
                total_statements += 1
                role = r["role"]
                role_dist[role] = role_dist.get(role, 0) + 1
                if r["is_lie"]:
                    total_lies += 1

print(f"\n発言総数: {total_statements}")
print(f"  うち嘘発言: {total_lies} ({total_lies/total_statements*100:.1f}%)")
print(f"\n役職別発言数:")
for role, cnt in sorted(role_dist.items(), key=lambda x: -x[1]):
    print(f"  {role}: {cnt}")

print("\n--- サンプル例（人狼の発言）---")
for s in samples:
    content = s["messages"][0]["content"]
    ans = json.loads(s["messages"][1]["content"])
    if "人狼" in content and ans.get("reasoning"):
        print("[user入力（抜粋）]")
        print(content[:200])
        print("[assistant出力]")
        print(json.dumps(ans, ensure_ascii=False, indent=2))
        break
