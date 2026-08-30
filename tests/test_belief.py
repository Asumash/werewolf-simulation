"""BeliefState（人狼確率の推論コア）のテスト。"""
from tests._helpers import Role, Turn, IDS, make_state, run_all
from players.rule_based import BeliefState


def _two_wolf_state():
    # prior が 0 にならないよう人狼を2体含める
    return make_state({"P1": Role.VILLAGER, "P2": Role.VILLAGER, "P3": Role.VILLAGER,
                       "P4": Role.WEREWOLF, "P5": Role.WEREWOLF})


def _prob(state, self_id="P1", **kw):
    return BeliefState.from_state(self_id, state).probabilities([], **kw)


def test_seer_wolf_result_raises_target():
    st = _two_wolf_state()
    base = _prob(st)["P3"]
    st.add_statement(Turn("P2", "占い師です。P3さんを占ったところ人狼でした。",
                          intent="seer_result", target="P3", result="人狼"))
    assert _prob(st)["P3"] > base


def test_seer_clear_result_lowers_target():
    st = _two_wolf_state()
    base = _prob(st)["P3"]
    st.add_statement(Turn("P2", "占い師です。P3さんを占いました。結果は村人でした。",
                          intent="seer_result", target="P3", result="村人陣営"))
    assert _prob(st)["P3"] < base


def test_vouch_lowers_target():
    st = _two_wolf_state()
    base = _prob(st)["P3"]
    st.add_statement(Turn("P2", "P3さんを信頼します", intent="vouch", target="P3"))
    assert _prob(st)["P3"] < base


def test_contradict_with_valid_basis_is_adopted():
    st = _two_wolf_state()
    # P2, P4 が両方占いCO＝矛盾が実在
    st.add_statement(Turn("P2", "占い師です。P5さんを占いました。結果は村人でした。",
                          intent="seer_result", target="P5", result="村人陣営"))
    st.add_statement(Turn("P4", "占い師です。P3さんを占ったところ人狼でした。",
                          intent="seer_result", target="P3", result="人狼"))
    before = _prob(st)["P2"]
    st.add_statement(Turn("P1", "P2は偽占い", intent="contradict",
                          target="P2", basis=["P2", "P4"]))
    assert _prob(st)["P2"] > before


def test_contradict_with_bluff_basis_penalizes_accuser():
    st = _two_wolf_state()
    # 占いCOは1件のみ → basis[P2,P4] に矛盾は存在しない
    st.add_statement(Turn("P2", "占い師です。P5さんを占いました。結果は村人でした。",
                          intent="seer_result", target="P5", result="村人陣営"))
    p1_before = BeliefState.from_state("P3", st).probabilities([])["P1"]
    p2_before = BeliefState.from_state("P3", st).probabilities([])["P2"]
    st.add_statement(Turn("P1", "P2は偽占い", intent="contradict",
                          target="P2", basis=["P2", "P4"]))
    probs = BeliefState.from_state("P3", st).probabilities([])
    assert abs(probs["P2"] - p2_before) < 1e-9   # 対象への加算は無効化
    assert probs["P1"] > p1_before               # 扇動した本人が疑われる


def test_incremental_equals_full_recompute():
    st = _two_wolf_state()
    inc = BeliefState.from_state("P1", st)
    turns = [
        Turn("P2", "占い師です。P3さんを占ったところ人狼でした。",
             intent="seer_result", target="P3", result="人狼"),
        Turn("P4", "P2さんが怪しい", intent="suspect", target="P2"),
        Turn("P5", "P3さんを信頼します", intent="vouch", target="P3"),
        Turn("P3", "私は村人です", intent="none"),
    ]
    for t in turns:
        st.add_statement(t)
        inc.observe(st)
        full = BeliefState.from_state("P1", st)
        for vote in (False, True):
            a = inc.probabilities([], is_voting=vote)
            b = full.probabilities([], is_voting=vote)
            for pid in IDS:
                assert abs(a[pid] - b[pid]) < 1e-9


if __name__ == "__main__":
    run_all(globals())
