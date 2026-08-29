"""矛盾検出が発動しているか直接確認する。"""
from __future__ import annotations
from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP, _parse_seer_claims, _parse_robber_claims
from recorder.recorder import GameRecorder

PLAYER_IDS = ["Alice", "Bob", "Carol", "Dave", "Eve"]
ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]

found = 0
for _ in range(500):
    players = [RuleBasedCP(pid) for pid in PLAYER_IDS]
    state   = GameState(player_ids=PLAYER_IDS)
    state.setup(ROLE_LIST)
    recorder = GameRecorder(output_dir="data/")
    runner   = GameRunner(state, players, recorder, total_statements=10)
    runner.run()

    # 各発言から矛盾検出状況を確認
    for turn in state.discussion_log:
        pid = turn.player_id
        player = next(p for p in players if p.player_id == pid)
        result = player._find_contradiction(state)
        if result and (
            "投票を勧めます" in result[0]
            or "投票を検討" in result[0]
        ):
            found += 1
            print(f"矛盾検出: {result[0][:80]}")
            print(f"  発言者: {pid} (role={player._get_believed_role(state).value})")
            # ログ表示
            for t in state.discussion_log:
                print(f"  {t.player_id}: {t.statement}")
            print()
            break
    if found >= 3:
        break

print(f"\n500ゲーム中 矛盾検出あり: {found} 件")
# 矛盾しやすい状況を集計
seer_double = robber_double = result_mismatch = 0
for turn in state.discussion_log:
    sc = _parse_seer_claims(state)
    rc = _parse_robber_claims(state)
    if len({c for c,_,_ in sc}) >= 2:
        seer_double += 1
    if len({c for c,_,_ in rc}) >= 2:
        robber_double += 1

print(f"最終ゲーム: 占いCO複数={seer_double}, 怪盗CO複数={robber_double}")
