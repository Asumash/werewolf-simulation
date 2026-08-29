from engine.game_state import GameState, Role

# ルール要約（全プロンプト共通）
_RULES = """【ゲーム】人狼ゲーム（5人）。役職カードは 人狼×2・占い師・怪盗・村人×3 の7枚、
うち2枚は墓地（誰の手札でもない）。夜→議論→投票の1日で決着する。
- 占い師：夜に他プレイヤー1人の役職を見る／または墓地2枚を見る。
- 怪盗：夜に他プレイヤー1人とカードを交換し、交換後の自分の新役職を知る（相手は知らない）。
- 人狼：夜に仲間の人狼が誰かを知る。
- 議論後、全員で同時に1人に投票。最多得票者を処刑。
- 処刑された中に人狼がいれば村人陣営の勝ち。いなければ人狼陣営の勝ち。
※怪盗は「交換後の役職」の陣営で判定される。"""


def _own_info(player_id: str, state: GameState) -> str:
    """そのプレイヤーが夜に正当に知り得る情報だけを文章化する（公平性のため）。"""
    role = state.original_role_map[player_id]
    kn = state.knowledge.get(player_id, {})
    if role == Role.SEER:
        if "saw_player" in kn:
            tgt, r = list(kn["saw_player"].items())[0]
            return f"あなたは占い師。{tgt} を占った結果は「{r}」だった。"
        if "saw_graveyard" in kn:
            return f"あなたは占い師。墓地の2枚は {kn['saw_graveyard']} だった。"
        return "あなたは占い師。（夜の行動結果は未確定）"
    if role == Role.ROBBER:
        if "swapped_with" in kn:
            return (f"あなたは怪盗。{kn['swapped_with']} とカードを交換し、"
                    f"今のあなたの役職は「{kn.get('new_role','不明')}」。"
                    f"（交換相手はこの交換を知らない）")
        return "あなたは怪盗。（交換結果は未確定）"
    if role == Role.WEREWOLF:
        allies = [p for p in state.player_ids
                  if p != player_id and state.original_role_map[p] == Role.WEREWOLF]
        if allies:
            return f"あなたは人狼。仲間の人狼は {allies}。正体を隠して村人陣営を欺くこと。"
        return "あなたは人狼（一匹狼、仲間なし）。正体を隠すこと。"
    return "あなたは村人。特別な夜の情報はない。発言の矛盾から人狼を推理せよ。"


def _log_text(state: GameState, player_id: str) -> str:
    pub = state.get_public_state(player_id)
    return "\n".join(
        f"  {t['player']}: {t['statement']}" for t in pub["discussion_log"]
    ) or "  （まだ発言なし）"


def build_statement_prompt(player_id: str, state: GameState,
                           hint: str = "", style: str = "") -> str:
    others = [p for p in state.player_ids if p != player_id]
    hint_line = f"\n【状況】{hint}\n" if hint else ""
    style_line = f"- あなたの口調: {style}\n" if style else ""
    return f"""{_RULES}

あなたはプレイヤー「{player_id}」。他プレイヤー: {others}
{_own_info(player_id, state)}

【これまでの議論】
{_log_text(state, player_id)}
{hint_line}
いま議論で発言します。1つだけ短く発言し、その「行動タグ」も付けてください。

【話し方（重要）】オンラインで人狼を遊ぶ普通のプレイヤーになりきってください。
- **短く**（1〜2文、目安15〜50字）。長い説明・丁寧すぎる敬語・毎回理由を述べるのは禁止。
- 崩した口語でOK（「〜だと思う」「〜じゃない?」「うーん」等）。言い切ってもよい。
- AIっぽく完璧に整理しない。時々ラフでよいし、質問攻め・長い矛盾指摘は避ける。
- 情報役職（占い師・怪盗）なら結果は早めに、ただし短くCOする。
{style_line}
行動タグ intent は次から1つ:
- "seer_result"  : 占い結果をCO（target=占った相手, result="人狼"または"村人陣営"）
- "robber_result": 怪盗の交換結果をCO（target=交換相手, result=交換後の役職）
- "suspect"      : 誰かを疑う（target=対象）
- "vote_suggest" : 投票を誘導（target=対象）
- "contradict"   : 誰かの主張が矛盾していると指摘（target=対象, basis=矛盾の根拠にした相手のリスト）
- "vouch"        : 誰かを信頼・擁護（target=対象）
- "ask"          : 誰かに質問（target=対象）
- "none"         : 上記以外の通常発言

JSONのみで返答（他の文字は不要）:
{{
  "statement": "発言（短く・15〜50字目安）",
  "intent": "上記のいずれか",
  "target": "対象のplayer_id（不要なら空文字）",
  "result": "seer_result/robber_result のときのみ（他は空文字）",
  "basis": ["contradictの根拠にしたplayer_id", "..."],
  "reasoning": "なぜその発言をしたか（内部思考）"
}}"""


def build_vote_prompt(player_id: str, state: GameState) -> str:
    others = [p for p in state.player_ids if p != player_id]
    return f"""{_RULES}

あなたはプレイヤー「{player_id}」。
{_own_info(player_id, state)}

【議論ログ】
{_log_text(state, player_id)}

投票フェーズです。あなたの陣営が勝つために、最も投票すべきプレイヤーを1人選んでください。
投票候補: {others}

JSONのみで返答:
{{
  "vote_target": "投票先のplayer_id（候補から1つ）",
  "reasoning": "その理由"
}}"""


def build_night_prompt(player_id: str, state: GameState) -> str:
    role = state.original_role_map[player_id]
    others = [p for p in state.player_ids if p != player_id]

    if role == Role.SEER:
        return f"""{_RULES}

あなたは占い師「{player_id}」。他プレイヤー: {others}
夜の行動：誰か1人を占う、または墓地2枚を見る。

JSONのみで返答:
{{"action": "see_player", "target": "player_id"}}
または
{{"action": "see_graveyard"}}"""

    if role == Role.ROBBER:
        return f"""{_RULES}

あなたは怪盗「{player_id}」。他プレイヤー: {others}
夜の行動：誰か1人とカードを交換する（交換後の自分の役職が分かる）、または交換しない。

JSONのみで返答:
{{"action": "swap", "target": "player_id"}}
または
{{"action": "skip"}}"""

    return '{"action": "none"}'
