"""学習データ一括生成スクリプト。"""
from __future__ import annotations
import sys
import json
import time
from pathlib import Path
from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP
from recorder.recorder import GameRecorder

PLAYER_IDS = ["Alice", "Bob", "Carol", "Dave", "Eve"]
ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]

def run_once(recorder: GameRecorder) -> dict:
    players = [RuleBasedCP(pid) for pid in PLAYER_IDS]
    state = GameState(player_ids=PLAYER_IDS)
    state.setup(ROLE_LIST)
    runner = GameRunner(state, players, recorder)
    return runner.run()

def main(n: int):
    recorder = GameRecorder(output_dir="data/")
    results = {"village": 0, "werewolf": 0}
    start = time.time()

    for i in range(n):
        result = run_once(recorder)
        results[result["winner"]] += 1
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            remaining = (n - i - 1) / rate
            print(
                f"[{i+1:>5}/{n}] 村人{results['village']}勝 / 人狼{results['werewolf']}勝"
                f"  ({rate:.1f}game/s, 残り約{remaining:.0f}秒)"
            )

    elapsed = time.time() - start
    print(f"\n完了: {n}ゲーム / {elapsed:.1f}秒")
    print(f"村人{results['village']}勝 / 人狼{results['werewolf']}勝")

    # 全JSONLをファインチューニング形式に変換してまとめる
    print("\nファインチューニング形式に変換中...")
    all_samples = []
    for path in sorted(Path("data").glob("game_*.jsonl")):
        samples = recorder.to_finetuning_format(str(path))
        all_samples.extend(samples)

    out_path = Path("data") / "finetune_dataset.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for sample in all_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"学習サンプル数: {len(all_samples)}")
    print(f"出力先: {out_path}")

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    main(n)
