"""infer_tags（発言→構造化タグ）のテスト。"""
from tests._helpers import IDS, run_all
from players.rule_based import infer_tags

P = ["CPU-1", "CPU-2", "CPU-3", "CPU-4", "Me"]


def test_seer_result_wolf():
    intent, target, result = infer_tags(
        "占い師です。CPU-2さんを占ったところ人狼でした。", P, "CPU-1")
    assert (intent, target, result) == ("seer_result", "CPU-2", "人狼")


def test_seer_result_clean():
    intent, target, result = infer_tags(
        "占い師です。CPU-3さんを占いました。結果は村人でした。", P, "CPU-1")
    assert (intent, target, result) == ("seer_result", "CPU-3", "村人陣営")


def test_robber_result():
    intent, target, result = infer_tags(
        "怪盗です。CPU-4と交換しました。私は今村人です。", P, "CPU-1")
    assert (intent, target, result) == ("robber_result", "CPU-4", "村人")


def test_suspect_picks_target():
    intent, target, _ = infer_tags("CPU-2さんの発言が矛盾しているように感じます。", P, "CPU-1")
    assert intent == "suspect"
    assert target == "CPU-2"


def test_contradict_extracts_accused():
    intent, target, _ = infer_tags(
        "CPU-3さんが偽の占い師だと思います。CPU-3さんへの投票を強く勧めます。", P, "CPU-1")
    assert intent == "contradict"
    assert target == "CPU-3"


def test_second_seer_statement_is_suspect_not_seer_result():
    # 2回目の占い師発言は結果COではなく suspect 扱い（二重計上防止）
    intent, _, _ = infer_tags(
        "CPU-2さんが人狼という結果でしたし、CPU-3さんの発言も気になります。", P, "CPU-1")
    assert intent == "suspect"


if __name__ == "__main__":
    run_all(globals())
