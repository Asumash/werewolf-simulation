from __future__ import annotations
import random
from players.base import PlayerInterface
from engine.game_state import GameState, Role

# ──────────────────────────────────────────────
# 発言解析ユーティリティ
# ──────────────────────────────────────────────

def infer_tags(
    statement: str, players: list[str], speaker: str = ""
) -> tuple[str, str, str]:
    """発言テキストから (intent, target, result) を推定する。

    CPU の定型発言・人間の自由発言どちらも、対象プレイヤー付きで
    構造化タグに変換する。人間/CPU/LLM 共通の行動言語として使う。
    """
    s = statement
    others = [p for p in players if p != speaker]

    def name_with(marker: str) -> str:
        """`{pid}さん{marker}` または `{pid}{marker}` に一致する pid を返す。"""
        for p in others:
            if f"{p}さん{marker}" in s or f"{p}{marker}" in s:
                return p
        return ""

    def last_name() -> str:
        """文中で最後に登場するプレイヤー名を返す（疑い対象の推定）。"""
        best, best_idx = "", -1
        for p in others:
            idx = s.rfind(p)
            if idx > best_idx:
                best_idx, best = idx, p
        return best

    # 1. 矛盾指摘（偽COの告発）
    if "偽の占い師" in s or "偽の怪盗" in s or "投票を強く勧め" in s:
        tgt = name_with("への投票を強く勧め") or name_with("が偽") or last_name()
        return ("contradict", tgt, "")

    # 2. 占い結果CO
    if "占い師です" in s or "私は占い師" in s or "占い師CO" in s:
        if "墓地" in s:
            return ("seer_result", "", "")  # 墓地確認（対象プレイヤーなし）
        tgt = name_with("を占")
        if tgt:
            after = s.split("を占", 1)[-1]
            result = "人狼" if "人狼" in after else "村人陣営"
            return ("seer_result", tgt, result)

    # 3. 怪盗結果CO
    if ("怪盗です" in s or "私は怪盗" in s or "怪盗CO" in s) and "交換" in s:
        tgt = name_with("と交換")
        new_role = ""
        for r in ["人狼", "占い師", "怪盗", "村人"]:
            if f"今{r}" in s or f"は{r}でした" in s:
                new_role = r
                break
        return ("robber_result", tgt, new_role)

    # 4. 投票誘導
    if "投票" in s or "処刑" in s:
        return ("vote_suggest", last_name(), "")

    # 5. 疑い
    if any(k in s for k in
           ["怪しい", "疑", "矛盾", "気になります", "違和感", "詳しく", "発言が", "説明"]):
        return ("suspect", last_name(), "")

    # 6. 質問
    if "ですか" in s or "情報をお持ち" in s or "役職でした" in s:
        return ("ask", last_name(), "")

    return ("none", "", "")


def _parse_seer_claims(state: GameState) -> list[tuple[str, str, str]]:
    """(claimer, target, result) のリストを返す。

    intent タグ（seer_result + target + result）があれば最優先で使い、
    無ければ発言テキストを解析する（旧データ・タグ無しへのフォールバック）。
    """
    claims = []
    for turn in state.discussion_log:
        stmt = turn.statement
        pid = turn.player_id

        # ── タグ優先 ──
        if getattr(turn, "intent", "") == "seer_result":
            tgt = getattr(turn, "target", "") or ""
            if tgt:
                res = getattr(turn, "result", "") or ""
                role_name = "人狼" if res == "人狼" else "村人"
                claims.append((pid, tgt, role_name))
            continue  # タグ付き発言はテキスト解析しない（二重計上防止）

        # ── テキスト解析（フォールバック） ──
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
    """(claimer, swap_target, new_role_or_None) のリストを返す。

    intent タグ（robber_result + target + result）を最優先で使う。
    """
    claims = []
    for turn in state.discussion_log:
        stmt = turn.statement
        pid = turn.player_id

        # ── タグ優先 ──
        if getattr(turn, "intent", "") == "robber_result":
            tgt = getattr(turn, "target", "") or ""
            if tgt:
                new_role = getattr(turn, "result", "") or None
                claims.append((pid, tgt, new_role))
            continue  # タグ付き発言はテキスト解析しない（二重計上防止）

        # ── テキスト解析（フォールバック） ──
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
        # タグで対象が明示されていれば最優先
        if getattr(turn, "intent", "") in ("suspect", "vote_suggest", "contradict"):
            if getattr(turn, "target", "") == target_pid:
                accusers.append(turn.player_id)
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
#
# BeliefState は「各プレイヤーの人狼確率」を導く単一の情報源。
# 発言（Turn）が届くたびに observe() で生の証拠を増分的に蓄積し、
# probabilities() が蓄積済みの証拠から一括で確率を算出する。
# 「いつ／何を話すか」「誰に投票するか」の全判断がここを経由する。
# LLM や学習方策に差し替える際の継ぎ目でもある。
# ──────────────────────────────────────────────

# 疑いの重み（intent 別）
_ACCUSE_WEIGHT = {"contradict": 0.20, "suspect": 0.15, "vote_suggest": 0.15}


def _seer_claims_from_turn(turn, players: list[str]) -> list[tuple[str, str, str]]:
    """1つの Turn から占いCO (claimer, target, result) を抽出（複数可）。"""
    pid = turn.player_id
    stmt = turn.statement
    if getattr(turn, "intent", "") == "seer_result":
        tgt = getattr(turn, "target", "") or ""
        if tgt:
            res = getattr(turn, "result", "") or ""
            return [(pid, tgt, "人狼" if res == "人狼" else "村人")]
        return []
    out = []
    if "占い師" not in stmt:
        return out
    for other in players:
        if other == pid:
            continue
        if f"{other}を占" in stmt or f"{other}さんを占" in stmt:
            for role_name in ["人狼", "村人", "占い師", "怪盗"]:
                if (f"結果は{role_name}" in stmt
                        or f"{role_name}でした" in stmt
                        or f"ところ{role_name}" in stmt):
                    out.append((pid, other, role_name))
    return out


def _robber_claims_from_turn(turn, players: list[str]) -> list[tuple[str, str, str | None]]:
    """1つの Turn から怪盗CO (claimer, swap_target, new_role) を抽出。"""
    pid = turn.player_id
    stmt = turn.statement
    if getattr(turn, "intent", "") == "robber_result":
        tgt = getattr(turn, "target", "") or ""
        if tgt:
            return [(pid, tgt, getattr(turn, "result", "") or None)]
        return []
    out = []
    if "怪盗" not in stmt:
        return out
    for other in players:
        if f"{other}と交換" in stmt or f"{other}さんと交換" in stmt:
            new_role = None
            for role_name in ["人狼", "村人", "占い師", "怪盗"]:
                if f"今{role_name}" in stmt or f"私は今{role_name}" in stmt:
                    new_role = role_name
                    break
            out.append((pid, other, new_role))
    return out


class BeliefState:
    """人狼確率の単一情報源。Turn ごとに証拠を増分蓄積する。"""

    def __init__(self, self_id: str, players: list[str], wolf_count: int):
        self.self_id = self_id
        self.players = list(players)
        self.prior = wolf_count / len(players)
        self._seen = 0  # 処理済みの discussion_log 件数

        # 蓄積される生の証拠
        self.seer_claims: list[tuple[str, str, str]] = []
        self.robber_claims: list[tuple[str, str, str | None]] = []
        # (accuser, weight, [targets], [basis], kind) を発言順に保持
        self.accuse_events: list[tuple[str, float, list[str], list[str], str]] = []
        # (voucher, target) 擁護（疑いを下げる正の証拠）
        self.vouch_events: list[tuple[str, str]] = []
        # (target, boost) 投票時のみ適用する強い誘導
        self.vote_recs: list[tuple[str, float]] = []
        self.statement_counts: dict[str, int] = {p: 0 for p in players}

    # ---------- 証拠の増分蓄積 ----------

    def observe(self, state: GameState) -> "BeliefState":
        """discussion_log の未処理 Turn を取り込む。"""
        log = state.discussion_log
        for turn in log[self._seen:]:
            self._ingest(turn)
        self._seen = len(log)
        return self

    def _ingest(self, turn) -> None:
        pid = turn.player_id
        stmt = turn.statement
        if pid in self.statement_counts:
            self.statement_counts[pid] += 1

        self.seer_claims.extend(_seer_claims_from_turn(turn, self.players))
        self.robber_claims.extend(_robber_claims_from_turn(turn, self.players))

        # 疑い/投票誘導/矛盾指摘/擁護の対象を発言順に記録
        intent = getattr(turn, "intent", "") or ""
        tag_target = getattr(turn, "target", "") or ""
        tag_basis = [b for b in (getattr(turn, "basis", []) or [])
                     if b in self.statement_counts]
        if intent == "vouch":
            # 擁護：対象の疑いを下げる正の証拠（人間/LLM が供給）
            if tag_target and tag_target in self.statement_counts and tag_target != pid:
                self.vouch_events.append((pid, tag_target))
        elif intent in _ACCUSE_WEIGHT:
            if tag_target and tag_target in self.statement_counts:
                targets = [tag_target]
            else:
                targets = [
                    p for p in self.players
                    if p != pid and (
                        p in stmt
                        or f"{p}さんの発言が" in stmt
                        or f"{p}が怪しい" in stmt
                        or f"{p}は人狼" in stmt
                    )
                ]
            targets = [t for t in targets if t != pid]
            self.accuse_events.append(
                (pid, _ACCUSE_WEIGHT[intent], targets, tag_basis, intent)
            )
        elif intent in ("seer_result", "robber_result"):
            pass  # 結果は claims 側で処理（疑い加算はしない）
        else:
            targets = [
                p for p in self.players
                if p != pid and (
                    f"{p}さんの発言が" in stmt
                    or f"{p}が怪しい" in stmt
                    or f"{p}は人狼" in stmt
                )
            ]
            self.accuse_events.append((pid, 0.10, targets, [], "text"))

        # 投票時のみ効く強い誘導シグナル
        EXPOSE_SIGNALS = ("投票を勧めます", "投票を検討", "どちらかが偽装", "嘘をついていると思います")
        if any(sig in stmt for sig in EXPOSE_SIGNALS):
            for p in self.players:
                if f"{p}さんへの投票を勧めます" in stmt:
                    self.vote_recs.append((p, 0.7))
                elif (f"{p}さんのどちらかに投票" in stmt
                      or f"{p}さんへ投票を検討" in stmt
                      or f"{p}さんへの投票を検討" in stmt):
                    self.vote_recs.append((p, 0.5))

    # ---------- 確率の算出 ----------

    def probabilities(
        self, known_wolves=(), is_voting: bool = False
    ) -> dict[str, float]:
        """蓄積済みの証拠から各プレイヤーの人狼確率を算出する。"""
        wolf_prob = {pid: self.prior for pid in self.players}
        wolf_prob[self.self_id] = 0.0
        for pid in known_wolves:
            if pid in wolf_prob:
                wolf_prob[pid] = 1.0

        # 占い結果
        for _, target, result in self.seer_claims:
            if result == "人狼":
                wolf_prob[target] = min(1.0, wolf_prob[target] + 0.25)
            else:
                wolf_prob[target] = max(0.0, wolf_prob[target] - 0.25)

        # 占いCO複数
        seer_claimants = list({c for c, _, _ in self.seer_claims})
        if len(seer_claimants) > 1:
            for c in seer_claimants:
                wolf_prob[c] = min(1.0, wolf_prob[c] + 0.15)

        # 占い結果の矛盾
        target_results: dict[str, list[tuple[str, str]]] = {}
        for claimer, target, result in self.seer_claims:
            target_results.setdefault(target, []).append((claimer, result))
        for target, entries in target_results.items():
            if len({r for _, r in entries}) > 1:
                for claimer, _ in entries:
                    wolf_prob[claimer] = min(1.0, wolf_prob[claimer] + 0.5)

        # 怪盗CO整合性
        for claimer, swap_target, new_role in self.robber_claims:
            if new_role == "人狼":
                wolf_prob[claimer] = min(1.0, wolf_prob[claimer] + 0.4)
            else:
                wolf_prob[claimer] = max(0.0, wolf_prob[claimer] - 0.1)
                if swap_target in wolf_prob:
                    wolf_prob[swap_target] = max(0.0, wolf_prob[swap_target] - 0.2)

        # 怪盗CO複数
        robber_claimants = list({c for c, _, _ in self.robber_claims})
        if len(robber_claimants) > 1:
            for c in robber_claimants:
                wolf_prob[c] = min(1.0, wolf_prob[c] + 0.15)

        # 疑いの重み付け（発言順・信頼度の高い発言者ほど影響大）
        for accuser, weight, targets, basis, kind in self.accuse_events:
            cred = 1.0 - wolf_prob.get(accuser, self.prior)
            # 矛盾指摘に論拠（basis）が付いていれば、その矛盾が実在するか検証
            if kind == "contradict" and basis:
                if self._conflict_exists(basis):
                    eff = weight  # 実在 → 通常どおり採用
                else:
                    eff = 0.0     # ハッタリ → 無効化し、扇動した本人を疑う
                    wolf_prob[accuser] = min(1.0, wolf_prob[accuser] + 0.10)
            else:
                eff = weight
            for pid in targets:
                if pid == accuser:
                    continue
                wolf_prob[pid] = min(1.0, wolf_prob[pid] + eff * cred)

        # 擁護（正の証拠）：信頼できる発言者の擁護ほど疑いを下げる
        for voucher, target in self.vouch_events:
            cred = 1.0 - wolf_prob.get(voucher, self.prior)
            wolf_prob[target] = max(0.0, wolf_prob[target] - 0.15 * cred)

        # 発言数ペナルティ
        for pid in self.players:
            if pid == self.self_id:
                continue
            cnt = self.statement_counts.get(pid, 0)
            if is_voting and cnt == 0:
                wolf_prob[pid] = min(1.0, wolf_prob[pid] + 0.35)
            elif is_voting and cnt == 1:
                wolf_prob[pid] = min(1.0, wolf_prob[pid] + 0.20)
            if cnt >= 1:
                wolf_prob[pid] = min(1.0, wolf_prob[pid] + 0.005 * cnt * (cnt + 1) / 2)

        clipped = {pid: max(0.0, min(1.0, p)) for pid, p in wolf_prob.items()}

        # 投票時のみ：強い誘導シグナルを上乗せ
        if is_voting:
            for target, boost in self.vote_recs:
                if target in clipped:
                    clipped[target] = min(1.0, clipped[target] + boost)
        return clipped

    # ---------- 判断ヘルパー ----------

    def most_suspicious(
        self, candidates: list[str], known_wolves=(), is_voting: bool = False
    ) -> str:
        """候補のうち最も人狼確率が高いプレイヤーを返す。"""
        probs = self.probabilities(known_wolves, is_voting)
        return max(candidates, key=lambda p: probs.get(p, 0.0))

    def _conflict_exists(self, basis: list[str]) -> bool:
        """basis に挙げられたプレイヤー間に、実在する主張の食い違いがあるか。

        - 2人以上が占いCO / 2人以上が怪盗CO（役職は1人のはず）
        - basis内の1人がもう1人を占っている（占い結果の突き合わせが可能）
        """
        bs = set(basis)
        if len({c for c, _, _ in self.seer_claims if c in bs}) >= 2:
            return True
        if len({c for c, _, _ in self.robber_claims if c in bs}) >= 2:
            return True
        for c, t, _ in self.seer_claims:
            if c in bs and t in bs:
                return True
        for c, t, _ in self.robber_claims:
            if c in bs and t in bs:
                return True
        return False

    @classmethod
    def from_state(
        cls, self_id: str, state: GameState
    ) -> "BeliefState":
        """state 全体から一括構築する（増分を使わない簡易利用向け）。"""
        wolf_count = sum(1 for r in state.role_map.values() if r == Role.WEREWOLF)
        return cls(self_id, state.player_ids, wolf_count).observe(state)


def _calculate_wolf_probabilities(
    self_id: str,
    state: GameState,
    my_known_wolves: list[str],
    is_voting: bool = False,
) -> dict[str, float]:
    """後方互換ラッパー。BeliefState を都度構築して確率を返す。"""
    return BeliefState.from_state(self_id, state).probabilities(
        my_known_wolves, is_voting
    )


# ──────────────────────────────────────────────
# RuleBasedCP
# ──────────────────────────────────────────────

class RuleBasedCP(PlayerInterface):

    # ---------- 初期化・ペルソナ ----------

    def __init__(self, player_id: str):
        super().__init__(player_id)
        # 発話個性（役職とは無関係。タイミングの役職バレを防ぐ）
        self.speed = random.choice([0.7, 0.85, 1.0, 1.0, 1.3])   # 反応の速さ倍率（小さいほど速い）
        self.talkativeness = random.uniform(0.8, 1.25)           # 発言頻度倍率
        self._recent_statements: list[str] = []                  # 直近の自分の発言（反復回避用）
        self._belief: BeliefState | None = None                  # 信念状態（Turnごとに増分更新）

    def _get_belief(self, state: GameState) -> BeliefState:
        """自分の信念状態を返す。新しいゲームなら作り直し、未処理Turnを取り込む。"""
        b = self._belief
        # 別ゲーム・ログ巻き戻し・メンバー変更を検知して作り直す
        if (b is None
                or b.self_id != self.player_id
                or b.players != state.player_ids
                or b._seen > len(state.discussion_log)):
            b = BeliefState.from_state(self.player_id, state)
            self._belief = b
        else:
            b.observe(state)
        return b

    def remember_statement(self, text: str) -> None:
        """直近発言を記録（反復回避のため）。"""
        self._recent_statements.append(text)
        if len(self._recent_statements) > 5:
            self._recent_statements.pop(0)

    def _pick_fresh(self, pool: list[str]) -> str:
        """直近に使っていない候補を優先して選ぶ。"""
        fresh = [s for s in pool if s not in self._recent_statements]
        return random.choice(fresh) if fresh else random.choice(pool)

    # ---------- リアルタイム反応 ----------

    def _my_statement_count(self, state: GameState) -> int:
        return sum(1 for t in state.discussion_log if t.player_id == self.player_id)

    def reactive_context(self, state: GameState) -> dict:
        """自分の最後の発言より後に起きた「反応すべき事象」を抽出する。"""
        log = state.discussion_log
        me = self.player_id
        my_idxs = [i for i, t in enumerate(log) if t.player_id == me]
        last_my = my_idxs[-1] if my_idxs else -1
        recent = log[last_my + 1:]  # 自分の最終発言以降の他者発言

        accused_by = None
        asked_by = None
        for t in recent:
            if t.player_id == me:
                continue
            intent = getattr(t, "intent", "") or ""
            target = getattr(t, "target", "") or ""
            stmt = t.statement
            # 名指しで疑われた / 投票誘導・矛盾指摘された
            if (intent in ("suspect", "vote_suggest", "contradict") and target == me) or (
                f"{me}さん" in stmt
                and any(k in stmt for k in ["怪しい", "人狼", "投票", "処刑", "矛盾"])
            ):
                accused_by = t.player_id
            # 質問された
            if intent == "ask" and target == me:
                asked_by = t.player_id

        return {
            "accused_by": accused_by,
            "asked_by": asked_by,
            "conflict_by": self._find_knowledge_conflict(state, recent),
            "expose": self._try_expose_statement(state),
            "has_unshared_info": self._has_unshared_info(state),
        }

    def _find_knowledge_conflict(self, state: GameState, recent: list) -> str | None:
        """自分の夜知識と食い違うCOをした相手を返す。"""
        role = self._get_believed_role(state)
        me = self.player_id
        if role == Role.SEER:
            for t in recent:
                if t.player_id != me and getattr(t, "intent", "") == "seer_result":
                    return t.player_id  # 対抗占い師
        if role == Role.ROBBER:
            for t in recent:
                if t.player_id != me and getattr(t, "intent", "") == "robber_result":
                    return t.player_id  # 対抗怪盗
        return None

    def _has_unshared_info(self, state: GameState) -> bool:
        """情報役職（占い師・怪盗）で、まだCOしていない状態か。"""
        role = self._get_believed_role(state)
        if role not in (Role.SEER, Role.ROBBER):
            return False
        return self._my_statement_count(state) == 0

    def speak_urge(
        self, state: GameState, since_my_last: float, since_any_msg: float
    ) -> tuple[float, str]:
        """今どれだけ話したいか（urge）と、その理由（trigger）を返す。"""
        ctx = self.reactive_context(state)
        if ctx["expose"] is not None:
            return 5.0, "expose"
        # 対抗COが自分を名指ししている → 反論(カウンターCO)を最優先
        if ctx["conflict_by"] and ctx["conflict_by"] == ctx["accused_by"]:
            return 4.2, "rebut"
        if ctx["accused_by"]:
            return 4.0, "defend"
        if ctx["conflict_by"]:
            return 3.5, "rebut"
        if ctx["asked_by"]:
            return 3.0, "answer"

        my_count = self._my_statement_count(state)
        if my_count == 0 and ctx["has_unshared_info"]:
            return 2.5, "co"
        if since_any_msg > 8.0:
            return 1.5, "fill"
        if my_count == 0:
            return 1.2, "open"
        # 発言済み：回数が増えるほど控えめに
        return max(0.3, 1.0 * (0.6 ** my_count)) * self.talkativeness, "base"

    def make_reactive_statement(
        self, state: GameState, trigger: str
    ) -> tuple[str, str]:
        """trigger に応じた文脈依存の発言を返す。基本ケースは make_statement に委譲。"""
        role = self._get_believed_role(state)
        ctx = self.reactive_context(state)

        if trigger == "expose" and ctx["expose"] is not None:
            return ctx["expose"], "確定情報を指摘"
        if trigger == "defend" and ctx["accused_by"]:
            return self._say_defense(state, ctx["accused_by"], role)
        if trigger == "answer" and ctx["asked_by"]:
            return self._say_answer(ctx["asked_by"], role)
        if trigger == "rebut" and ctx["conflict_by"]:
            return self._say_rebut(ctx["conflict_by"], role)
        # co / open / fill / base → 通常生成
        return self.make_statement(state)

    def _say_defense(
        self, state: GameState, accuser: str, role: Role
    ) -> tuple[str, str]:
        """疑いへの反論。役職に応じて言い方を変える。"""
        if role == Role.WEREWOLF:
            # 人狼：正体を隠しつつ疑いを他へ逸らす
            others = [p for p in state.player_ids if p not in (self.player_id, accuser)]
            wp = self._get_belief(state).probabilities([])
            cand = max(others, key=lambda p: wp.get(p, 0)) if others else accuser
            pool = [
                f"{accuser}さん、私を疑うより{cand}さんの方が怪しいと思いますよ。",
                f"私は村人です。{accuser}さんこそ人狼から目を逸らしていませんか？",
                f"{accuser}さんに疑われる理由が分かりません。{cand}さんの方が不自然です。",
            ]
        elif role == Role.SEER:
            pool = [
                f"{accuser}さん、私は本物の占い師です。疑うのは筋違いです。",
                f"占い結果も話しています。{accuser}さんの指摘は的外れだと思います。",
            ]
        elif role == Role.ROBBER:
            pool = [
                f"{accuser}さん、私は怪盗で交換結果も共有しました。疑うなら根拠を示してください。",
                f"私は怪盗です。{accuser}さんの疑いには納得できません。",
            ]
        else:
            pool = [
                f"{accuser}さん、私を疑う根拠が薄いと思います。私は村人です。",
                f"待ってください、{accuser}さんの方こそ動きが不自然に見えます。",
                f"私は人狼ではありません。{accuser}さん、なぜそう思うのですか？",
            ]
        return self._pick_fresh(pool), f"{accuser}の疑いに反論"

    def _say_answer(self, asker: str, role: Role) -> tuple[str, str]:
        """質問への回答。"""
        if role == Role.SEER:
            pool = [f"{asker}さん、私は占い師です。", f"{asker}さんへ。私は占い師で情報を持っています。"]
        elif role == Role.ROBBER:
            pool = [f"{asker}さん、私は怪盗です。", f"{asker}さんへ。私は怪盗で交換を行いました。"]
        else:
            pool = [
                f"{asker}さん、私は村人で特別な情報はありません。",
                f"{asker}さんへ。私は村人です。役職はありません。",
            ]
        return self._pick_fresh(pool), f"{asker}の質問に回答"

    def _say_rebut(self, claimer: str, role: Role) -> tuple[str, str]:
        """自分の知識と矛盾するCOへの反論。"""
        if role == Role.SEER:
            pool = [
                f"{claimer}さんが占い師を名乗っていますが、本物の占い師は私です。",
                f"{claimer}さんの占い結果は信じられません。私が本物の占い師です。",
            ]
        elif role == Role.ROBBER:
            pool = [
                f"{claimer}さんが怪盗と言っていますが、怪盗は私です。おかしいですね。",
                f"{claimer}さんの怪盗COには矛盾があります。本物は私です。",
            ]
        else:
            pool = [
                f"{claimer}さんの発言、少し整合性が取れていない気がします。",
                f"{claimer}さんの話には引っかかる点があります。",
            ]
        return self._pick_fresh(pool), f"{claimer}のCOに反論"

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
        wolf_probs = self._get_belief(state).probabilities([])
        target = (
            max(non_allies, key=lambda p: wolf_probs.get(p, 0))
            if non_allies else random.choice(others)
        )

        if strategy == "seer":
            templates = [
                f"{target}さんの発言が気になります。もう少し説明してもらえますか？",
                f"議論を見ていると{target}さんが怪しいと思います。",
                f"{target}さん、占い師が他にいるとしたら矛盾しますよね。",
                f"占い師の立場から見ても{target}さんの動きは不自然です。",
                f"{target}さんへの疑いが晴れませんね。",
            ]
        elif strategy == "robber":
            templates = [
                f"交換した結果を踏まえると、{target}さんが一番疑わしいです。",
                f"{target}さんの話に違和感があります。",
                f"怪盗として動いた立場から見ると{target}さんが怪しいです。",
                f"{target}さん、交換の話と合わせて考えると引っかかります。",
                f"私の交換結果からすると{target}さんが残ります。",
            ]
        else:  # villager
            templates = [
                f"{target}さんの発言が矛盾しているように感じます。",
                f"{target}さん、もう少し詳しく話してもらえますか？",
                f"私は{target}さんが一番怪しいと思います。",
                f"{target}さんの立ち回りが気になります。",
                f"どうも{target}さんが引っかかります。",
            ]

        statement = self._pick_fresh(templates)
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
                wolf_probs = self._get_belief(state).probabilities(known_wolves)
                candidates = [p for p in others if p != target]
                if result == "人狼" and candidates:
                    # 人狼確認済みのうえで他の疑惑を補強
                    most_suspicious = max(
                        candidates, key=lambda p: wolf_probs.get(p, 0)
                    )
                    statement = self._pick_fresh([
                        f"{target}さんが人狼という結果でしたし、{most_suspicious}さんの発言も気になります。",
                        f"改めて言いますが{target}さんは人狼です。加えて{most_suspicious}さんも怪しい。",
                        f"{target}さんは確定人狼です。次点で{most_suspicious}さんを警戒しています。",
                    ])
                    reasoning = "占い結果を踏まえた追加疑惑。"
                elif candidates:
                    most_suspicious = max(
                        candidates, key=lambda p: wolf_probs.get(p, 0)
                    )
                    statement = self._pick_fresh([
                        f"議論を踏まえると{most_suspicious}さんも怪しいと思います。",
                        f"占い師として見ると、次は{most_suspicious}さんが気になります。",
                        f"{most_suspicious}さんの立ち回りが引っかかります。",
                    ])
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
                wolf_probs = self._get_belief(state).probabilities([])
                suspicious = max(others, key=lambda p: wolf_probs.get(p, 0))
                statement = self._pick_fresh([
                    f"墓地情報からも{suspicious}さんが最も怪しいです。",
                    f"墓地を見た限り、{suspicious}さんが残ると思います。",
                    f"墓地の役職を踏まえると{suspicious}さんが疑わしいですね。",
                ])
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
                wolf_probs = self._get_belief(state).probabilities([])
                candidates = [p for p in others if p != swap_target]
                suspicious = (
                    max(candidates, key=lambda p: wolf_probs.get(p, 0))
                    if candidates else random.choice(others)
                )
                statement = self._pick_fresh([
                    f"{swap_target}と交換した結果を踏まえると、{suspicious}さんが最も怪しいです。",
                    f"私は{swap_target}と交換した怪盗です。その上で{suspicious}さんを疑っています。",
                    f"交換相手の{swap_target}以外だと、{suspicious}さんが一番怪しいですね。",
                ])
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
        wolf_probs = self._get_belief(state).probabilities([])
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
                f"{suspicious}さんの立ち回りがどうも気になります。",
                f"今のところ{suspicious}さんが一番あやしいと感じています。",
                f"{suspicious}さんの話、少し引っかかる点がありますね。",
            ]
            statement = self._pick_fresh(templates)
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

        # 確定人狼がいればそこへ即決
        for pid in known_wolves:
            if pid in others:
                return pid

        # 信念状態から投票モードの確率を算出（沈黙ペナルティ・投票誘導シグナルを含む）
        wolf_probs = self._get_belief(state).probabilities(known_wolves, is_voting=True)
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

        # 村人陣営（＝仲間以外）から最も疑われている候補へ便乗投票する。
        # ※ここは意図的にテキストパターンのみで集計する（タグ対応にすると
        #   人狼が過度に有利になりバランスが崩れるため）。
        accusation_counts = {p: 0 for p in candidates}
        for turn in state.discussion_log:
            stmt = turn.statement
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
        return max(candidates, key=lambda p: accusation_counts[p])
