"""パターン1（2名占いCO）の発動条件を確認。"""
from __future__ import annotations
from engine.game_state import GameState, Role
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP, _parse_seer_claims
from recorder.recorder import GameRecorder

PLAYER_IDS = ["Alice", "Bob", "Carol", "Dave", "Eve"]
ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]

two_seer_co = 0
pattern1_condition = 0
pattern1_fired = 0

for _ in range(500):
    players = [RuleBasedCP(pid) for pid in PLAYER_IDS]
    state   = GameState(player_ids=PLAYER_IDS)
    state.setup(ROLE_LIST)
    recorder = GameRecorder(output_dir="data/")
    runner   = GameRunner(state, players, recorder, total_statements=10)
    runner.run()

    sc = _parse_seer_claims(state)
    claimants = {c for c, _, _ in sc}
    if len(claimants) >= 2:
        two_seer_co += 1
        # 条件チェック
        for claimer, target, result in sc:
            if target in claimants and result != "人狼":
                pattern1_condition += 1
                break

    # 実際の発言に偽の占い師メッセージが含まれるか
    if any("偽の占い師" in t.statement for t in state.discussion_log):
        pattern1_fired += 1

print(f"2名占いCOが発生: {two_seer_co}/500")
print(f"パターン1条件成立: {pattern1_condition}/500")
print(f"パターン1実際に発言: {pattern1_fired}/500")

# 条件成立したが発言なしのケースを1件サンプル表示
for _ in range(2000):
    players = [RuleBasedCP(pid) for pid in PLAYER_IDS]
    state   = GameState(player_ids=PLAYER_IDS)
    state.setup(ROLE_LIST)
    recorder = GameRecorder(output_dir="data/")
    runner   = GameRunner(state, players, recorder, total_statements=10)
    runner.run()

    sc = _parse_seer_claims(state)
    claimants = {c for c, _, _ in sc}
    cond = False
    for claimer, target, result in sc:
        if target in claimants and result != "人狼":
            cond = True
            break
    fired = any("偽の占い師" in t.statement for t in state.discussion_log)

    if cond and not fired:
        print("\n--- 条件成立・未発言のサンプル ---")
        print(f"original_role_map: {dict((k, v.value) for k,v in state.original_role_map.items())}")
        print(f"seer_claims: {sc}")
        print(f"claimants: {claimants}")
        for t in state.discussion_log:
            p = next(p for p in players if p.player_id == t.player_id)
            role = p._get_believed_role(state).value
            print(f"  {t.player_id}({role}): {t.statement}")
        break
