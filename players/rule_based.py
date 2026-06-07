from __future__ import annotations
import random
from players.base import PlayerInterface
from engine.game_state import GameState, Role

# ──────────────────────────────────────────────
# 発言解析ユーティリティ
# ──────────────────────────────────────────────

def _parse_seer_claims(state: GameState) -> list[tuple[str, str, str]]:
    """(claimer, target, result) のリストを返す。"""
    claims = []
    for turn in state.discussion_log:
        stmt = turn.statement
        pid = turn.player_id
        if "占い師" not in stmt:
            continue
        for other in state.player_ids:
            if other == pid:
                continue
            # 「を占いました」「を占ったところ」どちらにも対応するため「を占」で検索
            if (f"{other}を占" in stmt or f"{other}さんを占" in stmt):
                for role_name in ["人狼", "村人", "占い師", "怪盗"]:
                    if (f"結果は{role_name}" in stmt
                            or f"{role_name}でした" in stmt
                            or f"ところ{role_name}" in stmt):
                        claims.append((pid, other, role_name))
    return claims


def _parse_robber_claims(state: GameState) -> list[tuple[str, str, str | None]]:
    """(claimer, swap_target, new_role_or_None) のリストを返す。"""
    claims = []
    for turn in state.discussion_log:
        stmt = turn.statement
        pid = turn.player_id
        if "怪盗" not in stmt:
            continue
        for other in state.player_ids:
            # 「〇〇と交換」「〇〇さんと交換」の両方に対応
            if f"{other}と交換" in stmt or f"{other}さんと交換" in stmt:
                new_role = None
                for role_name in ["人狼", "村人", "占い師", "怪盗"]:
                    if f"今{role_name}" in stmt or f"私は今{role_name}" in stmt:
                        new_role = role_name
                        break
                claims.append((pid, other, new_role))
    return claims


def _parse_accusations(state: GameState, target_pid: str) -> list[str]:
    """target_pid を疑っている発言者リストを返す。"""
    accusers = []
    for turn in state.discussion_log:
        stmt = turn.statement
        if turn.player_id == target_pid:
            continue
        if (
            f"{target_pid}さんの発言が" in stmt
            or f"{target_pid}が怪しい" in stmt
            or f"{target_pid}は人狼" in stmt
            or f"{target_pid}を処刑" in stmt
            or f"{target_pid}に投票" in stmt
        ):
            accusers.append(turn.player_id)
    return accusers


# ──────────────────────────────────────────────
# 信念モデル（village 視点）
# ──────────────────────────────────────────────

def _calculate_wolf_probabilities(
    self_id: str,
    state: GameState,
    my_known_wolves: list[str],
) -> dict[str, float]:
    """
    各プレイヤーの「人狼である確率」を返す。
    my_known_wolves: 自分が確実に人狼と知っているプレイヤーのリスト。
    """
    players = state.player_ids
    n = len(players)
    wolf_count = sum(1 for r in state.role_map.values() if r == Role.WEREWOLF)
    prior = wolf_count / n

    # 事前確率
    wolf_prob: dict[str, float] = {pid: prior for pid in players}
    wolf_prob[self_id] = 0.0  # 自分は除外

    # 確実な情報を適用
    for pid in my_known_wolves:
        wolf_prob[pid] = 1.0

    seer_claims = _parse_seer_claims(state)
    robber_claims = _parse_robber_claims(state)

    # 占い結果の適用
    for claimer, target, result in seer_claims:
        if result == "人狼":
            wolf_prob[target] = min(1.0, wolf_prob[target] + 0.5)
            wolf_prob[claimer] = max(0.0, wolf_prob[claimer] - 0.1)
        else:
            wolf_prob[target] = max(0.0, wolf_prob[target] - 0.25)

    # 占い師を複数人が名乗っている場合は全員やや怪しい
    seer_claimants = list({c for c, _, _ in seer_claims})
    if len(seer_claimants) > 1:
        for c in seer_claimants:
            wolf_prob[c] = min(1.0, wolf_prob[c] + 0.15)

    # 占い結果の矛盾を検出（同一ターゲットに対して異なる結果）
    target_results: dict[str, list[tuple[str, str]]] = {}
    for claimer, target, result in seer_claims:
        target_results.setdefault(target, []).append((claimer, result))
    for target, entries in target_results.items():
        results_set = {r for _, r in entries}
        if len(results_set) > 1:
            # 矛盾あり → 片方が嘘つき（効果を強くする）
            for claimer, _ in entries:
                wolf_prob[claimer] = min(1.0, wolf_prob[claimer] + 0.5)

    # 怪盗COの整合性確認
    for claimer, swap_target, new_role in robber_claims:
        if new_role == "人狼":
            # 怪盗が人狼と交換したと主張 → その怪盗は今人狼
            # ただし本当の怪盗(人狼になった)はこれを言わないはずなので疑わしい
            wolf_prob[claimer] = min(1.0, wolf_prob[claimer] + 0.4)
        else:
            # 怪盗COは村人陣営の証拠になりやすい
            wolf_prob[claimer] = max(0.0, wolf_prob[claimer] - 0.1)
            # 交換先の元の役職は人狼以外だったことが示唆される → 疑いを下げる
            if swap_target in wolf_prob:
                wolf_prob[swap_target] = max(0.0, wolf_prob[swap_target] - 0.2)

    # 怪盗COが2人以上いる場合は全員やや怪しい（怪盗は1人しかいないため）
    robber_claimants = list({c for c, _, _ in robber_claims})
    if len(robber_claimants) > 1:
        for c in robber_claimants:
            wolf_prob[c] = min(1.0, wolf_prob[c] + 0.15)

    # 疑惑の重み付け集計（信頼度の高い発言者ほど影響大）
    # 1周目: 暫定信頼度 = 1 - wolf_prob
    for turn in state.discussion_log:
        accuser = turn.player_id
        stmt = turn.statement
        accuser_credibility = 1.0 - wolf_prob.get(accuser, prior)
        for pid in players:
            if pid == accuser:
                continue
            if (
                f"{pid}さんの発言が" in stmt
                or f"{pid}が怪しい" in stmt
                or f"{pid}は人狼" in stmt
            ):
                wolf_prob[pid] = min(1.0, wolf_prob[pid] + 0.1 * accuser_credibility)

    # 0〜1 にクリップ
    return {pid: max(0.0, min(1.0, p)) for pid, p in wolf_prob.items()}


# ──────────────────────────────────────────────
# RuleBasedCP
# ──────────────────────────────────────────────

class RuleBasedCP(PlayerInterface):

    # ---------- 役職認識 ----------

    def _get_believed_role(self, state: GameState) -> Role:
        """
        自分が「信じている自分の役職」を返す。

        - 怪盗として交換を実行し、人狼を得た場合 → WEREWOLF（スワップを隠して人狼行動）
        - 怪盗として交換を実行し、それ以外を得た場合 → ROBBER のまま
            怪盗であることは変わらず、議論ではスワップを告知して行動する
        - 交換された側（元人狼など）   → 通知なしのため original_role_map を使う
        - 議論中に交換されたと推測できた場合のみ真の役職に切り替える
        """
        knowledge = state.knowledge[self.player_id]

        # 自分が怪盗として動いた場合
        if "new_role" in knowledge:
            new_role = Role(knowledge["new_role"])
            if new_role == Role.WEREWOLF:
                # 人狼を得た → スワップを隠して人狼として行動
                return Role.WEREWOLF
            # それ以外（村人・占い師・怪盗）を得た → 怪盗として行動（スワップをCO）
            return Role.ROBBER

        # 交換された側: 元の役職のまま（交換の通知なし）
        original = state.original_role_map[self.player_id]
        if original == Role.WEREWOLF:
            # 議論から「自分が怪盗に交換された」と分かれば村人陣営として動く
            if self._can_deduce_was_swapped(state):
                return state.role_map[self.player_id]  # 真の役職（ROBBER）
            return Role.WEREWOLF  # 知らないので引き続き人狼として振る舞う

        return original

    def _can_deduce_was_swapped(self, state: GameState) -> bool:
        """
        議論ログに「自分と交換した」という発言があれば交換を推測できる。
        怪盗→人狼スワップ時は怪盗側がそれを隠すため、実際にはほぼ発動しない。
        """
        for turn in state.discussion_log:
            if (
                f"{self.player_id}と交換" in turn.statement
                and "怪盗" in turn.statement
            ):
                return True
        return False

    # ---------- 夜行動 ----------

    def night_action(self, state: GameState) -> dict:
        role = state.original_role_map[self.player_id]
        others = [p for p in state.player_ids if p != self.player_id]

        if role == Role.SEER:
            if random.random() < 0.7:
                return {"action": "see_player", "target": random.choice(others)}
            return {"action": "see_graveyard"}

        elif role == Role.ROBBER:
            return {"action": "swap", "target": random.choice(others)}

        return {"action": "none"}

    # ---------- 発言重要度 ----------

    def get_urgency_score(self, state: GameState) -> float:
        """
        発言の重要度スコア（高いほど選ばれやすい）。

        設計方針：
          占い師・怪盗  情報を持つため序盤に高スコア
          人狼         偽COを早めに打ちたいが占い師より遅い
          村人         他者の発言が出てから初めて反応する
        """
        role = self._get_believed_role(state)
        log = state.discussion_log
        my_statements = sum(1 for t in log if t.player_id == self.player_id)
        total_statements = len(log)

        # 確定情報（指摘文）があれば常に最優先
        if self._try_expose_statement(state) is not None:
            return 5.0

        # ── 未発言の場合 ──
        if my_statements == 0:
            if role == Role.SEER:
                # 占い師は情報源なので最序盤に積極的に話す
                return 3.0
            elif role == Role.ROBBER:
                # 怪盗も交換結果を早めに開示
                return 2.5
            elif role == Role.WEREWOLF:
                # 人狼は占い師の直後あたりに偽COを打ちたい
                # 他に誰も話していない状況ではやや控える
                if total_statements == 0:
                    return 1.0
                return 2.0
            else:
                # 村人：情報役職が話すまで完全に待つ
                # 誰も発言していない → 話さない（0）
                # 発言が増えるにつれて徐々に参加
                if total_statements == 0:
                    return 0.0
                return min(0.8, 0.08 * total_statements)

        # ── 発言済みの場合：回数に応じて指数的に減衰 ──
        decay = 1.2 * (0.55 ** my_statements)

        # 村人は発言済みでも積極的に話しすぎない
        if role == Role.VILLAGER:
            decay *= 0.8

        return max(0.15, decay)

    # ---------- 発言生成 ----------

    def make_statement(self, state: GameState) -> tuple[str, str]:
        # 確定情報があれば最優先で指摘
        expose = self._try_expose_statement(state)
        if expose is not None:
            return expose, f"確定情報を指摘: {expose}"

        role = self._get_believed_role(state)
        knowledge = state.knowledge[self.player_id]
        others = [p for p in state.player_ids if p != self.player_id]

        # ── 人狼（元人狼・怪盗→人狼スワップどちらも含む） ──
        if role == Role.WEREWOLF:
            return self._statement_as_werewolf(state, knowledge, others)

        # ── 占い師 ──
        elif role == Role.SEER:
            return self._statement_as_seer(state, knowledge, others)

        # ── 怪盗（人狼でなかった場合） ──
        elif role == Role.ROBBER:
            return self._statement_as_robber(state, knowledge, others)

        # ── 村人 ──
        else:
            return self._statement_as_villager(state, others)

    # ── 人狼戦略ヘルパー ──────────────────────────────

    def _get_wolf_strategy(self, state: GameState) -> str:
        """
        現在の人狼の立ち回り戦略を返す（"seer" / "robber" / "villager"）。
        過去発言がある場合はその内容から判断して一貫させる。
        初回は状況を分析して決定する。
        """
        for t in state.discussion_log:
            if t.player_id != self.player_id:
                continue
            if "占い師です" in t.statement or "私は占い師" in t.statement:
                return "seer"
            if "怪盗です" in t.statement and "交換しました" in t.statement:
                return "robber"
        # まだCOしていない → 状況に応じて決定
        return self._choose_wolf_strategy(state)

    def _choose_wolf_strategy(self, state: GameState) -> str:
        """
        初回COの戦略を状況に応じて決定する。

        考慮する要因:
          - 仲間が占いCOしていれば自分はしない
          - 場に占いCOが多ければ怪盗・村人を選ぶ
          - 怪盗COが出ていれば怪盗を避ける
        """
        others = [p for p in state.player_ids if p != self.player_id]
        allies = [p for p in others if state.original_role_map[p] == Role.WEREWOLF]

        # 仲間がすでに選んでいる戦略
        ally_strats: set[str] = set()
        for ally in allies:
            for t in state.discussion_log:
                if t.player_id != ally:
                    continue
                if "占い師です" in t.statement or "私は占い師" in t.statement:
                    ally_strats.add("seer")
                elif "怪盗です" in t.statement and "交換しました" in t.statement:
                    ally_strats.add("robber")

        seer_co_count  = len({c for c, _, _ in _parse_seer_claims(state)})
        robber_co_count = len({c for c, _, _ in _parse_robber_claims(state)})

        # ベース重み（デフォルト: 占い師70%・怪盗30%・村人0%）
        w = {"seer": 0.70, "robber": 0.30, "villager": 0.00}

        # 仲間が占いCOしていれば占いCOを避け、村人率を大きく引き上げる
        if "seer" in ally_strats:
            w["seer"] = 0.05
            w["robber"] = 0.40
            w["villager"] = 0.55

        # 仲間が怪盗COしていれば怪盗を避け、村人潜伏を大きく引き上げる
        if "robber" in ally_strats:
            w["seer"] = 0.40
            w["robber"] = 0.05
            w["villager"] = 0.55

        # 場に占いCOが多い（本物含め2人以上）場合も占いを避ける
        if seer_co_count >= 2:
            w["seer"] *= 0.20

        # 怪盗COがすでに出ていれば怪盗を避ける
        if robber_co_count >= 1:
            w["robber"] *= 0.25

        total = sum(w.values())
        keys = list(w.keys())
        probs = [w[k] / total for k in keys]
        return random.choices(keys, weights=probs)[0]

    # ── 発言生成（人狼） ──────────────────────────────

    def _statement_as_werewolf(
        self, state: GameState, knowledge: dict, others: list[str]
    ) -> tuple[str, str]:
        """人狼として振る舞う発言（元人狼・怪盗→人狼スワップ両方）。"""
        my_statements = sum(
            1 for t in state.discussion_log if t.player_id == self.player_id
        )
        strategy = self._get_wolf_strategy(state)
        allies = [p for p in others if state.original_role_map[p] == Role.WEREWOLF]
        non_allies = [p for p in others if p not in allies]

        # ── 初発言 ──
        if my_statements == 0:
            if strategy == "seer":
                fake_target = random.choice(others)
                fake_result = random.choice(["村人", "村人", "人狼"])
                statement = (
                    f"私は占い師です。{fake_target}さんを占ったところ"
                    f"{fake_result}でした。"
                )
                reasoning = f"偽占いCO。{fake_target}を{fake_result}と申告。"

            elif strategy == "robber":
                # 偽怪盗CO: 村人・占い師・怪盗どれかを新役職として偽装
                # （人狼と交換したとは言わない）
                fake_target = random.choice(others)
                fake_new_role = random.choice(["村人", "村人", "占い師"])
                statement = (
                    f"怪盗です。{fake_target}さんと交換しました。"
                    f"私は今{fake_new_role}です。"
                )
                reasoning = f"偽怪盗CO。{fake_target}と交換・{fake_new_role}と偽申告。"

            else:  # villager
                # 役職を名乗らず自然に発言
                target = random.choice(non_allies) if non_allies else random.choice(others)
                statement = f"{target}さんはどんな情報をお持ちですか？"
                reasoning = "村人を装い様子見。役職を主張しない。"

            return statement, reasoning

        # ── 2回目以降 ──
        wolf_probs = _calculate_wolf_probabilities(self.player_id, state, [])
        target = (
            max(non_allies, key=lambda p: wolf_probs.get(p, 0))
            if non_allies else random.choice(others)
        )

        if strategy == "seer":
            templates = [
                f"{target}さんの発言が気になります。もう少し説明してもらえますか？",
                f"議論を見ていると{target}さんが怪しいと思います。",
                f"{target}さん、占い師が他にいるとしたら矛盾しますよね。",
            ]
        elif strategy == "robber":
            templates = [
                f"交換した結果を踏まえると、{target}さんが一番疑わしいです。",
                f"{target}さんの話に違和感があります。",
                f"怪盗として動いた立場から見ると{target}さんが怪しいです。",
            ]
        else:  # villager
            templates = [
                f"{target}さんの発言が矛盾しているように感じます。",
                f"{target}さん、もう少し詳しく話してもらえますか？",
                f"私は{target}さんが一番怪しいと思います。",
            ]

        my_prev_count = my_statements
        statement = templates[my_prev_count % len(templates)]
        reasoning = f"戦略={strategy}として{target}に疑惑を向ける。"
        return statement, reasoning

    def _statement_as_seer(
        self, state: GameState, knowledge: dict, others: list[str]
    ) -> tuple[str, str]:
        my_statements = sum(
            1 for t in state.discussion_log if t.player_id == self.player_id
        )
        if "saw_player" in knowledge:
            target, result = list(knowledge["saw_player"].items())[0]
            if my_statements == 0:
                if result == "人狼":
                    statement = (
                        f"占い師です。{target}さんを占ったところ人狼でした。"
                        f"信じてもらえると助かります。"
                    )
                else:
                    statement = f"占い師です。{target}さんを占いました。結果は{result}でした。"
                reasoning = f"占い結果をCO。{target}={result}。"
            else:
                # 議論を踏まえた追加推理
                known_wolves = [target] if result == "人狼" else []
                wolf_probs = _calculate_wolf_probabilities(
                    self.player_id, state, known_wolves
                )
                candidates = [p for p in others if p != target]
                if result == "人狼" and candidates:
                    # 人狼確認済みのうえで他の疑惑を補強
                    most_suspicious = max(
                        candidates, key=lambda p: wolf_probs.get(p, 0)
                    )
                    statement = (
                        f"{target}さんが人狼という結果でしたし、"
                        f"{most_suspicious}さんの発言も気になります。"
                    )
                    reasoning = "占い結果を踏まえた追加疑惑。"
                elif candidates:
                    most_suspicious = max(
                        candidates, key=lambda p: wolf_probs.get(p, 0)
                    )
                    statement = (
                        f"議論を踏まえると{most_suspicious}さんも怪しいと思います。"
                    )
                    reasoning = "占い結果を踏まえた追加疑惑。"
                else:
                    statement = f"{target}さんは{result}だったので、他の方をよく見ています。"
                    reasoning = "占い結果の補足。"
        elif "saw_graveyard" in knowledge:
            roles = knowledge["saw_graveyard"]
            if my_statements == 0:
                statement = f"占い師です。墓地を見ました。{roles}でした。"
                reasoning = "墓地情報をCO。"
            else:
                # 2回目以降は議論に参加
                wolf_probs = _calculate_wolf_probabilities(self.player_id, state, [])
                suspicious = max(others, key=lambda p: wolf_probs.get(p, 0))
                statement = f"墓地情報からも{suspicious}さんが最も怪しいです。"
                reasoning = "墓地情報を踏まえた推理。"
        else:
            statement = "占い師ですが、有益な情報が得られませんでした。"
            reasoning = "占い結果なし。"
        return statement, reasoning

    def _statement_as_robber(
        self, state: GameState, knowledge: dict, others: list[str]
    ) -> tuple[str, str]:
        my_statements = sum(
            1 for t in state.discussion_log if t.player_id == self.player_id
        )
        if "swapped_with" in knowledge:
            swap_target = knowledge["swapped_with"]
            new_role = knowledge.get("new_role", "不明")
            # new_role が人狼の場合は werewolf として処理済み（ここには来ない）
            if my_statements == 0:
                statement = (
                    f"怪盗です。{swap_target}と交換しました。"
                    f"私は今{new_role}です。"
                )
                reasoning = f"交換結果をCO。new_role={new_role}。"
            else:
                wolf_probs = _calculate_wolf_probabilities(self.player_id, state, [])
                candidates = [p for p in others if p != swap_target]
                suspicious = (
                    max(candidates, key=lambda p: wolf_probs.get(p, 0))
                    if candidates else random.choice(others)
                )
                statement = (
                    f"{swap_target}と交換した結果を踏まえると、"
                    f"{suspicious}さんが最も怪しいです。"
                )
                reasoning = "怪盗情報を踏まえた追加推理。"
        else:
            # 怪盗は必ず交換するため、knowledge["swapped_with"]が存在しないケースは
            # 元人狼が強奪されてROBBERになった場合（knowledgeが空）
            # → 自分が怪盗だとは気づかず村人として発言
            return self._statement_as_villager(state, others)
        return statement, reasoning

    def _statement_as_villager(
        self, state: GameState, others: list[str]
    ) -> tuple[str, str]:
        wolf_probs = _calculate_wolf_probabilities(self.player_id, state, [])
        log = state.discussion_log
        my_statements = sum(
            1 for t in log if t.player_id == self.player_id
        )
        my_prev = [t.statement for t in log if t.player_id == self.player_id]

        if not log:
            # 議論ログが完全に空（自分が最初の発言者）→ 役職宣言なしで様子見コメント
            suspicious = random.choice(others)
            statement = f"{suspicious}さんはどんな役職でしたか？"
            reasoning = "初手で情報なし。相手に話を振る。"
        else:
            # 最も疑わしいプレイヤーを指摘（すでに指摘済みなら次点へ）
            ranked = sorted(others, key=lambda p: wolf_probs.get(p, 0), reverse=True)
            suspicious = ranked[0]
            for candidate in ranked:
                already = any(candidate in s for s in my_prev)
                if not already:
                    suspicious = candidate
                    break

            templates = [
                f"{suspicious}さんの発言が矛盾しているように感じます。",
                f"{suspicious}さん、もう少し詳しく説明してもらえますか？",
                f"私は{suspicious}さんが一番怪しいと思います。",
            ]
            statement = templates[my_statements % len(templates)]
            reasoning = f"wolf_prob={wolf_probs.get(suspicious, 0):.2f}で{suspicious}を指摘。"
        return statement, reasoning

    # ---------- 矛盾検出・指摘 ----------

    def _try_expose_statement(self, state: GameState) -> str | None:
        """
        公開情報から論理的に導ける矛盾を検出し、指摘文を返す。
        人狼は指摘しない。同じキーがすでにログに存在すれば重複を避ける。
        """
        if self._get_believed_role(state) == Role.WEREWOLF:
            return None

        result = self._find_contradiction(state)
        if result is None:
            return None

        statement, key = result
        # 誰かがすでに同じ指摘文（先頭30文字で照合）をしていれば省略
        prefix = statement[:30]
        if any(prefix in t.statement for t in state.discussion_log):
            return None
        return statement

    def _find_contradiction(
        self, state: GameState
    ) -> tuple[str, str] | None:
        """
        矛盾を検出して (指摘文, 重複チェック用キー) を返す。
        見つからなければ None。

        検出パターン（優先順）:
          1. 2名が占いCOしており、片方がもう一方を非人狼と判定している
             → 判定を出した側が偽占い師（人狼）
          2. 2名が怪盗COしており、片方がもう一方と交換して非人狼になったと主張
             → その主張をした側が偽怪盗（人狼）
        """
        seer_claims   = _parse_seer_claims(state)
        robber_claims = _parse_robber_claims(state)

        # ── パターン1: 2名占いCO + 片方がもう一方を非人狼と判定 ──
        # 占いCOした発言者の集合
        seer_claimants = {c for c, _, _ in seer_claims}
        if len(seer_claimants) >= 2:
            for claimer, target, result in seer_claims:
                # target も占いCOしており、かつ claimer が target を非人狼と報告
                if target not in seer_claimants or result == "人狼":
                    continue
                key = f"[矛盾]占いCO2名:{claimer}が{target}を{result}と占った"
                if claimer == self.player_id:
                    # 自分が占い師（本物）→ target が嘘をついている
                    stmt = (
                        f"私が{target}さんを{result}と占いましたが、"
                        f"{target}さんも占い師とCOしています。"
                        f"本物の占い師が別の占い師を{result}と見ることはありません。"
                        f"{target}さんが偽の占い師だと思います。"
                        f"{target}さんへの投票を強く勧めます。"
                    )
                else:
                    stmt = (
                        f"{claimer}さんは{target}さんを{result}と占いましたが、"
                        f"{target}さんも占い師とCOしています。"
                        f"本物の占い師が別の占い師を{result}と見ることはないため、"
                        f"{claimer}さんが偽の占い師である可能性が非常に高いです。"
                        f"{claimer}さんへの投票を強く勧めます。"
                    )
                return stmt, key

        # ── パターン2: 2名怪盗CO + 片方がもう一方と交換して非人狼になったと主張 ──
        # 怪盗COした発言者の集合
        robber_claimants = {c for c, _, _ in robber_claims}
        if len(robber_claimants) >= 2:
            for claimer, swap_target, new_role in robber_claims:
                # swap_target も怪盗COしており、かつ非人狼の役職を得たと主張
                if swap_target not in robber_claimants:
                    continue
                if not new_role or new_role == "人狼":
                    continue
                key = f"[矛盾]怪盗CO2名:{claimer}が{swap_target}と交換して{new_role}"
                stmt = (
                    f"{claimer}さんは{swap_target}さんと交換して{new_role}になったと言っていますが、"
                    f"{swap_target}さん自身も怪盗とCOしています。"
                    f"{swap_target}さんが本物の怪盗なら{claimer}さんとの交換は起きていないため、"
                    f"{claimer}さんが偽の怪盗である可能性が非常に高いです。"
                    f"{claimer}さんへの投票を強く勧めます。"
                )
                return stmt, key

        return None

    # ---------- 投票 ----------

    def vote(self, state: GameState) -> str:
        role = self._get_believed_role(state)
        knowledge = state.knowledge[self.player_id]
        others = [p for p in state.player_ids if p != self.player_id]

        if role == Role.WEREWOLF:
            return self._vote_as_werewolf(state, others, knowledge)
        else:
            return self._vote_as_village(state, others, knowledge)

    def _vote_as_village(
        self, state: GameState, others: list[str], knowledge: dict
    ) -> str:
        """村人陣営の投票：wolf_probability が最大のプレイヤーへ。"""
        # 自分が知っている確定人狼
        known_wolves: list[str] = []
        if "saw_player" in knowledge:
            target, result = list(knowledge["saw_player"].items())[0]
            if result == Role.WEREWOLF.value:
                known_wolves.append(target)

        wolf_probs = _calculate_wolf_probabilities(
            self.player_id, state, known_wolves
        )
        # 確定人狼がいればそこへ即決
        for pid in known_wolves:
            if pid in others:
                return pid

        # 矛盾指摘の発言から具体的な疑惑対象を抽出して wolf_prob に加算
        EXPOSE_SIGNALS = ("投票を勧めます", "投票を検討", "どちらかが偽装", "嘘をついていると思います")
        for turn in state.discussion_log:
            stmt = turn.statement
            if not any(sig in stmt for sig in EXPOSE_SIGNALS):
                continue
            for pid in others:
                if f"{pid}さんへの投票を勧めます" in stmt:
                    wolf_probs[pid] = min(1.0, wolf_probs.get(pid, 0) + 0.7)
                elif f"{pid}さんのどちらかに投票" in stmt or f"{pid}さんへ投票を検討" in stmt:
                    wolf_probs[pid] = min(1.0, wolf_probs.get(pid, 0) + 0.5)

        return max(others, key=lambda p: wolf_probs.get(p, 0))

    def _vote_as_werewolf(
        self, state: GameState, others: list[str], knowledge: dict
    ) -> str:
        """
        人狼の投票：
        - 村人陣営が票を集めそうな人物へ便乗投票する。
        - 仲間（現在の人狼）には投票しない。
        """
        # 仲間は original_role_map で判定（自分が知っている元の仲間）
        allies = [
            p for p in others
            if state.original_role_map[p] == Role.WEREWOLF
        ]
        candidates = [p for p in others if p not in allies]
        if not candidates:
            return random.choice(others)

        # 村人陣営から疑われている度合いをスコア化
        accusation_counts = {p: 0 for p in candidates}
        for turn in state.discussion_log:
            stmt = turn.statement
            # 発言者が人狼仲間なら無視（偏りを避ける）
            if turn.player_id in allies or turn.player_id == self.player_id:
                continue
            for pid in candidates:
                if (
                    f"{pid}さんの発言が" in stmt
                    or f"{pid}が怪しい" in stmt
                    or f"{pid}は人狼" in stmt
                    or f"{pid}を処刑" in stmt
                    or f"{pid}に投票" in stmt
                ):
                    accusation_counts[pid] += 1

        # 最も疑われているプレイヤーへ便乗
        return max(candidates, key=lambda p: accusation_counts[p])
