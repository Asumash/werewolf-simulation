"""矛盾指摘あり/なしの勝率比較。"""
from __future__ import annotations
import shutil
from pathlib import Path
from collections import defaultdict
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

def run_batch(n: int, expose_enabled: bool) -> dict:
    tmp = f"_tmp_expose_{expose_enabled}"
    Path(tmp).mkdir(exist_ok=True)
    recorder = GameRecorder(output_dir=tmp)

    wins = defaultdict(int)
    wolf_executed = 0
    expose_count = 0

    # 矛盾指摘の有効/無効をモンキーパッチで切り替え
    import players.rule_based as rb
    original = rb.RuleBasedCP._find_contradiction
    if not expose_enabled:
        rb.RuleBasedCP._find_contradiction = lambda self, state: None

    try:
        for _ in range(n):
            players = [RuleBasedCP(pid) for pid in PLAYER_IDS]
            state   = GameState(player_ids=PLAYER_IDS)
            state.setup(ROLE_LIST)
            runner  = GameRunner(state, players, recorder, total_statements=10)
            result  = runner.run()
            wins[result["winner"]] += 1
            for pid in result["executed"]:
                if state.role_map[pid] == Role.WEREWOLF:
                    wolf_executed += 1
            if any("投票を勧めます" in t.statement or "投票を検討" in t.statement
                   or "どちらかが偽装" in t.statement
                   for t in state.discussion_log):
                expose_count += 1
    finally:
        rb.RuleBasedCP._find_contradiction = original
        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "village_win": wins["village"] / n,
        "wolf_win":    wins["werewolf"] / n,
        "wolf_executed_per_game": wolf_executed / n,
        "expose_rate": expose_count / n,
    }

if __name__ == "__main__":
    N = 1000
    print(f"{N}ゲームずつ計測中...\n")

    r_on  = run_batch(N, expose_enabled=True)
    print(f"矛盾指摘あり: 村人{r_on['village_win']:.1%} / 人狼{r_on['wolf_win']:.1%}  人狼処刑/G={r_on['wolf_executed_per_game']:.3f}  指摘発生={r_on['expose_rate']:.1%}")

    r_off = run_batch(N, expose_enabled=False)
    print(f"矛盾指摘なし: 村人{r_off['village_win']:.1%} / 人狼{r_off['wolf_win']:.1%}  人狼処刑/G={r_off['wolf_executed_per_game']:.3f}  指摘発生={r_off['expose_rate']:.1%}")

    print()
    dv = r_on["village_win"] - r_off["village_win"]
    dw = r_on["wolf_executed_per_game"] - r_off["wolf_executed_per_game"]
    print(f"差分（あり－なし）: 村人勝率 {dv:+.1%}  人狼処刑/G {dw:+.3f}")
