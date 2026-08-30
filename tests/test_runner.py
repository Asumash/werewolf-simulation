"""同期ランナーで1ゲームが完走し、妥当な勝敗を返すことのテスト。"""
import io
import contextlib

from tests._helpers import GameState, ROLE_LIST, IDS, run_all
from engine.game_runner import GameRunner
from players.rule_based import RuleBasedCP


class _NullRecorder:
    def save(self, *a, **k):
        pass


def test_cp_game_completes_with_valid_winner():
    for _ in range(10):
        st = GameState(player_ids=IDS)
        st.setup(ROLE_LIST)
        players = [RuleBasedCP(i) for i in IDS]
        runner = GameRunner(st, players, _NullRecorder(), total_statements=12)
        with contextlib.redirect_stdout(io.StringIO()):
            res = runner.run()
        assert res["winner"] in ("village", "werewolf")
        assert isinstance(res.get("executed"), list)
        # 全員が投票している
        assert len(st.votes) == len(IDS)


def test_every_vote_targets_another_player():
    st = GameState(player_ids=IDS)
    st.setup(ROLE_LIST)
    players = [RuleBasedCP(i) for i in IDS]
    runner = GameRunner(st, players, _NullRecorder(), total_statements=12)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    for voter, target in st.votes.items():
        assert target in IDS
        assert target != voter


if __name__ == "__main__":
    run_all(globals())
