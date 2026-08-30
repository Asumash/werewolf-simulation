"""テスト共通ヘルパー。pytest でもプレーン実行でも動くよう import パスを補正。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.game_state import GameState, Role, Turn  # noqa: E402

ROLE_LIST = [
    Role.WEREWOLF, Role.WEREWOLF,
    Role.SEER, Role.ROBBER, Role.VILLAGER,
    Role.VILLAGER, Role.VILLAGER,
]
IDS = ["P1", "P2", "P3", "P4", "P5"]


def make_state(roles: dict) -> GameState:
    """役職を明示して GameState を作る（テスト用・夜行動なし）。"""
    st = GameState(player_ids=list(roles.keys()))
    st.role_map = dict(roles)
    st.original_role_map = dict(roles)
    st.knowledge = {p: {} for p in roles}
    return st


def run_all(module_globals):
    """`python tests/test_x.py` で全 test_* を実行するフォールバックランナー。"""
    fns = [v for k, v in sorted(module_globals.items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("  ok:", fn.__name__)
    print(f"{len(fns)} passed")
