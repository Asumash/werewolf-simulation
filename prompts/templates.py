from engine.game_state import GameState, Role

def build_statement_prompt(player_id: str, state: GameState) -> str:
    pub = state.get_public_state(player_id)
    role = pub["my_role"]

    strategy = {
        "人狼":  "正体を隠し、疑惑を他者に向けてください。偽COも有効です。",
        "占い師": "得た情報を活かし、人狼を論理的に追い詰めてください。",
        "怪盗":  "交換結果を踏まえ、自分の現在の役職として発言してください。",
        "村人":  "発言の矛盾を見つけ、人狼を推理してください。",
    }.get(role, "")

    log_text = "\n".join(
        f"  {t['player']}: {t['statement']}"
        for t in pub["discussion_log"]
    ) or "  （まだ発言なし）"

    return f"""あなたはワンナイト人狼のプレイヤー「{player_id}」です。

【あなたの役職】{role}
【戦略指針】{strategy}
【夜に得た情報】{pub['my_knowledge'] or 'なし'}
【これまでの議論】
{log_text}

以下のJSON形式のみで返答してください（他の文字は不要）:
{{
  "statement": "議論での発言（自然な日本語、50〜100文字）",
  "reasoning": "なぜその発言をしたか（内部思考、学習データ用）"
}}"""


def build_vote_prompt(player_id: str, state: GameState) -> str:
    pub = state.get_public_state(player_id)
    others = [p for p in state.player_ids if p != player_id]
    log_text = "\n".join(
        f"  {t['player']}: {t['statement']}"
        for t in pub["discussion_log"]
    )
    return f"""あなたは「{player_id}」（役職: {pub['my_role']}）です。
投票フェーズです。以下の議論を踏まえて、最も人狼らしいプレイヤーに投票してください。

【議論ログ】
{log_text}

【投票候補】{others}

JSON形式のみで返答:
{{
  "vote_target": "投票先のplayer_id",
  "reasoning": "その理由"
}}"""


def build_night_prompt(player_id: str, state: GameState) -> str:
    role = state.role_map[player_id]
    others = [p for p in state.player_ids if p != player_id]

    if role == Role.SEER:
        return f"""あなたは占い師「{player_id}」です。
誰かを占うか、墓地を見るか選んでください。
【他のプレイヤー】{others}

JSON形式のみで返答:
{{"action": "see_player", "target": "player_id"}}
または
{{"action": "see_graveyard"}}"""

    elif role == Role.ROBBER:
        return f"""あなたは怪盗「{player_id}」です。
誰かと役職を交換するか、スキップするか選んでください。
【他のプレイヤー】{others}

JSON形式のみで返答:
{{"action": "swap", "target": "player_id"}}
または
{{"action": "skip"}}"""

    return '{"action": "none"}'
