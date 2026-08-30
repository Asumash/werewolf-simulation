"""GameState の配札・夜行動・勝敗判定のテスト。"""
from tests._helpers import GameState, Role, ROLE_LIST, IDS, make_state, run_all


def test_setup_deals_all_players_and_graveyard():
    st = GameState(player_ids=IDS)
    st.setup(ROLE_LIST)
    assert len(st.role_map) == 5
    assert len(st.graveyard) == len(ROLE_LIST) - 5  # 墓地2枚
    # 配布された役職＋墓地 = 元のカード集合
    dealt = list(st.role_map.values()) + st.graveyard
    assert sorted(r.value for r in dealt) == sorted(r.value for r in ROLE_LIST)
    # original_role_map は配布直後のスナップショット
    assert st.original_role_map == st.role_map


def test_seer_sees_player():
    st = make_state({"P1": Role.SEER, "P2": Role.WEREWOLF, "P3": Role.VILLAGER,
                     "P4": Role.VILLAGER, "P5": Role.ROBBER})
    st.apply_seer_action("P1", "P2")
    assert st.knowledge["P1"]["saw_player"] == {"P2": "人狼"}


def test_seer_sees_graveyard():
    st = make_state({p: Role.VILLAGER for p in IDS})
    st.graveyard = [Role.WEREWOLF, Role.WEREWOLF]
    st.apply_seer_action("P1", None)
    assert st.knowledge["P1"]["saw_graveyard"] == ["人狼", "人狼"]


def test_robber_swaps_and_learns_new_role():
    st = make_state({"P1": Role.ROBBER, "P2": Role.WEREWOLF, "P3": Role.VILLAGER,
                     "P4": Role.VILLAGER, "P5": Role.SEER})
    st.apply_robber_action("P1", "P2")
    # 交換後 P1 は人狼、P2 は怪盗
    assert st.role_map["P1"] == Role.WEREWOLF
    assert st.role_map["P2"] == Role.ROBBER
    assert st.knowledge["P1"]["swapped_with"] == "P2"
    assert st.knowledge["P1"]["new_role"] == "人狼"


def test_judge_village_wins_when_wolf_executed():
    st = make_state({"P1": Role.WEREWOLF, "P2": Role.VILLAGER, "P3": Role.VILLAGER,
                     "P4": Role.SEER, "P5": Role.ROBBER})
    st.votes = {"P2": "P1", "P3": "P1", "P4": "P1", "P5": "P1", "P1": "P2"}
    res = st.judge_result()
    assert res["executed"] == ["P1"]
    assert res["winner"] == "village"


def test_judge_werewolf_wins_when_villager_executed():
    st = make_state({"P1": Role.WEREWOLF, "P2": Role.VILLAGER, "P3": Role.VILLAGER,
                     "P4": Role.SEER, "P5": Role.ROBBER})
    st.votes = {"P1": "P2", "P3": "P2", "P4": "P2", "P5": "P2", "P2": "P1"}
    res = st.judge_result()
    assert res["executed"] == ["P2"]
    assert res["winner"] == "werewolf"


if __name__ == "__main__":
    run_all(globals())
