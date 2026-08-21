# One Night Werewolf Simulation — Complete Specification

Last updated: 2026-06-08

---

## Table of Contents

1. [Game Overview](#1-game-overview)
2. [Role List](#2-role-list)
3. [Game Flow](#3-game-flow)
4. [Night Phase Details](#4-night-phase-details)
5. [Discussion Phase Details](#5-discussion-phase-details)
6. [Voting Phase Details](#6-voting-phase-details)
7. [Win Condition](#7-win-condition)
8. [Role Perception System (_get_believed_role)](#8-role-perception-system)
9. [Statement Urgency Score System](#9-statement-urgency-score-system)
10. [CP Statement Content by Role](#10-cp-statement-content-by-role)
11. [Werewolf Strategy System](#11-werewolf-strategy-system)
12. [Contradiction Detection System](#12-contradiction-detection-system)
13. [Wolf Probability (wolf_prob) Calculation System](#13-wolf-probability-wolf_prob-calculation-system)
14. [Voting Logic Details](#14-voting-logic-details)
15. [Lie Detection System](#15-lie-detection-system)
16. [Statement Parse System](#16-statement-parse-system)
17. [Training Data Structure](#17-training-data-structure)
18. [Statistics](#18-statistics)
19. [Rule Change History](#19-rule-change-history)

---

## 1. Game Overview

- **Players**: 5 (Alice, Bob, Carol, Dave, Eve)
- **Role Composition**: Werewolf×2, Seer×1, Robber×1, Villager×1 + Graveyard×2
- **Total Statements**: 15 (`total_statements = 15`)
- **Win Conditions**:
  - Village team (Seer, Robber, Villager): Execute at least 1 werewolf
  - Werewolf team: Avoid having any werewolf executed

### Two-Layer Role Management

The program manages roles using two separate variables.

| Variable | Content | Usage |
|----------|---------|-------|
| `original_role_map` | Role snapshot at the start of the night phase (before any swaps) | Identifying original werewolves and their allies |
| `role_map` | Current role after robber swap | Win condition judgment, seer confirmation results |

---

## 2. Role List

| Role | Team | Night Action | Notes |
|------|------|-------------|-------|
| Werewolf (WEREWOLF) | Werewolf | None | 2 exist. Each knows the other via `original_role_map` |
| Seer (SEER) | Village | Check 1 player or graveyard | Learns the role of the target (before any swap) |
| Robber (ROBBER) | Village | Swap roles with 1 player | Always performs the swap. Learns their new role afterward |
| Villager (VILLAGER) | Village | None | No special ability |

---

## 3. Game Flow

```
Setup
  └ Shuffle roles and distribute to 5 players. Last 2 cards go to the graveyard.
  └ original_role_map = snapshot of role_map before any swaps
    ↓
Night Phase (processed in NIGHT_ORDER)
  └ Order: Seer → Werewolf (no action) → Robber
    ↓
Discussion Phase (15 turns)
  └ Each turn: calculate urgency_score for all → weighted random pick → generate statement
    ↓
Voting Phase
  └ All players simultaneously calculate wolf_prob and decide their vote target
    ↓
Win Condition Check
  └ Judged by the executed player's role_map (post-swap)
```

---

## 4. Night Phase Details

### Processing Order (`NIGHT_ORDER`)
`Seer → Werewolf → Robber`

The seer always acts before the robber, so the seer always observes pre-swap roles.

### Seer Night Action

```python
if random.random() < 0.7:
    return {"action": "see_player", "target": random.choice(others)}  # check 1 other player
return {"action": "see_graveyard"}  # 30% chance to check graveyard
```

- Checked a player: stored as `knowledge["saw_player"] = {target: role}`
- Checked graveyard: stored as `knowledge["saw_graveyard"] = [role1, role2]`

### Robber Night Action

```python
return {"action": "swap", "target": random.choice(others)}  # always swaps
```

- Swaps `role_map[robber]` and `role_map[target]`
- `knowledge["swapped_with"] = target`
- `knowledge["new_role"] = new role after swap`
- **The swapped target is NOT notified**

### Werewolf Night Action

- Does nothing (`{"action": "none"}`)
- Each werewolf already knows its ally via `original_role_map`

### Asymmetric Information Summary

| Situation | Who knows | Who doesn't know |
|-----------|-----------|-----------------|
| Robber swaps with Werewolf | Robber (knows they became a werewolf) | Original werewolf (doesn't know they were swapped) |
| Robber swaps with Villager | Robber (knows they became a villager) | Original villager (doesn't know they were swapped) |
| Robber swaps with Seer | Robber (knows they became a seer) | Original seer (doesn't know they were swapped) |

---

## 5. Discussion Phase Details

### Speaker Selection Mechanism

Each turn proceeds as follows:

1. Calculate `get_urgency_score()` for all players
2. Select 1 speaker via weighted random draw (`_weighted_choice`)
3. Selected speaker generates a statement via `make_statement()`
4. Statement is appended to `discussion_log`
5. Repeat 15 times

### Statement Urgency Score (`urgency_score`)

#### Highest Priority: Contradiction Can Be Exposed

```
Contradiction exposable (non-werewolf) → 5.0 (always top priority)
```

#### If Not Yet Spoken

| Role | Condition | Score |
|------|-----------|-------|
| Seer | — | **3.0** |
| Robber | — | **2.5** |
| Werewolf | Total statements so far = 0 | **1.0** |
| Werewolf | Total statements so far ≥ 1 | **2.0** |
| Villager | Total statements so far = 0 | **0.0** (stays silent) |
| Villager | Total statements so far = N | **min(0.8, 0.08×N)** |

#### If Already Spoken (M times)

```
decay = 1.2 × 0.55^M
For villager: decay × 0.8
Floor: max(0.15, decay)
```

| Times spoken (M) | All roles | Villager only |
|-----------------|-----------|--------------|
| 1 | 0.66 | 0.53 |
| 2 | 0.36 | 0.29 |
| 3 | 0.20 | 0.16 |
| 4 | 0.15 (floor) | 0.15 (floor) |

---

## 6. Voting Phase Details

All players simultaneously choose 1 person to vote for.

### Village Team Voting

1. If the seer has confirmed a werewolf (`known_wolves`), vote for them immediately
2. Calculate `wolf_prob` with `is_voting=True` (includes silence penalty)
3. Adjust wolf_prob based on contradiction-pointing statements in the log
4. Vote for the player with the highest wolf_prob

### Werewolf Voting

1. Exclude werewolf allies (identified via `original_role_map`) from candidates
2. Tally suspicion scores from village team's statements in the discussion log
   - Ignore statements by allies and self (to avoid bias)
   - Suspicion keywords: `"X's statement is suspicious"`, `"X is suspicious"`, `"X is a werewolf"`, `"execute X"`, `"vote for X"`
3. Bandwagon-vote for the most-accused player

---

## 7. Win Condition

```python
# If all players receive the same number of votes (all tied)
if len(executed) == len(players):
    winner = "village" if not wolves else "werewolf"

# Normal case
wolf_executed = any(role_map[p] == WEREWOLF for p in executed)
winner = "village" if wolf_executed else "werewolf"
```

- Judgment uses **`role_map` (current post-swap role)** of the executed player
- If a robber who swapped with a werewolf gets executed, village wins (that player is now a werewolf)

---

## 8. Role Perception System

`_get_believed_role()` returns the role that each player "believes" they are.

```
① If knowledge contains "new_role" (player acted as robber)
    new_role == Werewolf → behave as WEREWOLF (hide the swap)
    new_role == other    → behave as ROBBER (claim the swap)

② If knowledge does NOT contain "new_role" (player was swapped into)
    original_role_map == Werewolf:
        If discussion log contains "swapped with me" → switch to true role (ROBBER)
        Otherwise → continue behaving as WEREWOLF
    Otherwise → use the role from original_role_map as-is
```

### Behavior per Situation

| Situation | believed_role | Actual behavior |
|-----------|-------------|----------------|
| Former Robber swapped with Werewolf | WEREWOLF | Speaks and votes as werewolf |
| Former Robber swapped with Villager | ROBBER | Claims robber role, says swapped with villager |
| Former Werewolf was swapped by Robber | WEREWOLF | Doesn't know, continues acting as werewolf |
| Former Villager was swapped by Robber | VILLAGER | Doesn't know, acts as villager (actually robber) |

---

## 9. Statement Urgency Score System

See Section 5 for full details. Scores are computed by `get_urgency_score()`.

`_try_expose_statement()` runs for all players every turn, so once a contradiction arises,
the top-priority score of 5.0 is assigned immediately.

---

## 10. CP Statement Content by Role

### Seer Statements

**First statement:**
- Checked a player (result: werewolf):
  > "I am the seer. I checked [X] and they were a werewolf. Please trust me."
- Checked a player (result: non-werewolf):
  > "I am the seer. I checked [X]. The result was [role]."
- Checked the graveyard:
  > "I am the seer. I checked the graveyard. The cards were ['role A', 'role B']."
- No action taken:
  > "I am the seer, but I couldn't obtain useful information."

**Second statement onward:**
- If confirmed werewolf: mention confirmed werewolf while also casting suspicion on the top wolf_prob player
- If confirmed non-werewolf: cast suspicion on the top wolf_prob player
- If graveyard: cast suspicion on the top wolf_prob player

---

### Robber Statements

**First statement (when swapped with non-werewolf):**
> "I am the robber. I swapped with [X]. I am now [role]."

**Second statement onward:**
> "Taking into account my swap with [X], I think [Y] is the most suspicious."

**Exception:** If `knowledge["swapped_with"]` is absent (original werewolf became robber via swap),
they don't realize they're the robber and speak as a villager.

---

### Villager Statements

**First statement (if discussion log is empty):**
> "What role did you have, [X]?"

**Standard statements (3 patterns rotated):**
- "I feel like [X]'s statements are contradictory."
- "[X], could you explain in more detail?"
- "I think [X] is the most suspicious."

Target is the player with the highest wolf_prob. If already accused, target the next-highest.

---

### Werewolf Statements

Statements vary by strategy (seer / robber / villager). See Section 11 for full details.

**First statement (seer disguise):**
> "I am the seer. I checked [X] and they were [role]."
- Claimed result: random from `["villager", "villager", "werewolf"]`

**First statement (robber disguise):**
> "I am the robber. I swapped with [X]. I am now [role]."
- Claimed new role: random from `["villager", "villager", "seer"]`

**First statement (villager camouflage):**
> "What information do you have, [X]?"

**Second statement onward (all strategies):**
Cast suspicion on the non-ally player with the highest wolf_prob, cycling through 3 patterns.

---

## 11. Werewolf Strategy System

### Strategy Decision Flow

```
If past statements contain "I am the seer" → maintain "seer"
If past statements contain "I am the robber" + "I swapped" → maintain "robber"
Otherwise → call _choose_wolf_strategy() to select a new strategy
```

### Strategy Selection Weights (`_choose_wolf_strategy`)

**Default weights:**

| Strategy | Weight |
|----------|--------|
| Seer disguise (seer) | 0.70 (70%) |
| Robber disguise (robber) | 0.30 (30%) |
| Villager camouflage (villager) | 0.00 (0%) |

**Situational weight adjustments (applied in order):**

| Situation | seer | robber | villager |
|-----------|------|--------|---------|
| Ally has already claimed seer | 0.05 | 0.40 | 0.55 |
| Ally has already claimed robber | 0.40 | 0.05 | 0.55 |
| 2+ seer claims in play | ×0.20 | — | — |
| 1+ robber claim in play | — | ×0.25 | — |

Multiple conditions stack in order. Final weights are normalized to sum = 1.

---

## 12. Contradiction Detection System

### Prerequisites

- **Werewolves never expose contradictions** (skipped when `believed_role == WEREWOLF`)
- If the same accusation text (first 30 chars) already exists in the log, it is skipped (dedup)
- When a contradiction is detected, urgency_score = **5.0** (top priority)

### Pattern 1: Fake Seer (Confirmed)

**Detection condition:**
- 2+ players have claimed seer
- One of them (claimer) has stated that another seer (target) is "non-werewolf"

**Logic:**
A real seer cannot see another seer as a villager/seer/robber (there is only 1 seer)
→ The claimer must be a fake seer (werewolf)

**Statement example (when speaker is the real seer):**
> "I checked [target] as a villager, but [target] is also claiming to be the seer. A real seer cannot see another seer as a villager. I believe [target] is the fake seer. I strongly recommend voting for [target]."

**Statement example (when a third party points it out):**
> "[claimer] checked [target] as a villager, but [target] is also claiming seer. Since a real seer cannot see another seer as a villager, there is a high probability that [claimer] is the fake seer. I strongly recommend voting for [claimer]."

---

### Pattern 2: Fake Robber (Confirmed)

**Detection condition:**
- 2+ players have claimed robber
- One of them (claimer) claims to have "swapped with [swap_target] and became non-werewolf"

**Logic:**
There is only 1 robber. If swap_target is the real robber, the swap with claimer never happened
→ The claimer must be a fake robber (werewolf)

**Statement example:**
> "[claimer] says they swapped with [swap_target] and became a villager, but [swap_target] is also claiming to be the robber. If [swap_target] is the real robber, the swap with [claimer] never happened. There is a high probability that [claimer] is the fake robber. I strongly recommend voting for [claimer]."

---

## 13. Wolf Probability (wolf_prob) Calculation System

`_calculate_wolf_probabilities(self_id, state, my_known_wolves, is_voting=False)`

### Initial Values

| Target | Initial value |
|--------|--------------|
| All players | 2 ÷ 5 = **0.4** (prior probability) |
| Self (self_id) | **0.0** (always excluded) |
| known_wolves list | **1.0** (confirmed) |

### Change Conditions

#### Seer Claim Related

| Condition | Target | Change |
|-----------|--------|--------|
| Seer claim: target judged as "werewolf" | Target | **+0.25** |
| Seer claim: target judged as "non-werewolf" | Target | **-0.25** |
| 2+ seer claims exist | All seer claimers | **+0.15** |
| Contradictory seer results on same target (2 players give different results) | Both claimers | **+0.5** |

#### Robber Claim Related

| Condition | Target | Change |
|-----------|--------|--------|
| Robber claim: "I am now a werewolf" | Claimer | **+0.4** |
| 2+ robber claims exist | All robber claimers | **+0.15** |
| Robber claim's swap target | Swap target | **-0.2** |

#### Suspicion Statements

| Condition | Target | Change |
|-----------|--------|--------|
| "X's statement is suspicious", "X is suspicious", "X is a werewolf" | Named player | **+0.1 × (1 − speaker's wolf_prob)** |

The higher the speaker's own wolf_prob, the less impact their accusation has.

#### Statement Count Related

| Condition | When applied | Target | Change |
|-----------|-------------|--------|--------|
| 0 statements | **Voting phase only** | That player | **+0.35** |
| 1 statement | **Voting phase only** | That player | **+0.20** |
| N statements (N≥1) | **Ongoing (during discussion too)** | That player | **+0.005 × N×(N+1)/2** |

Cumulative increase per statement count:

| Statements (N) | Total increase |
|---------------|---------------|
| 1 | +0.005 |
| 2 | +0.015 |
| 3 | +0.030 |
| 4 | +0.050 |
| 5 | +0.075 |
| 6 | +0.105 |

#### Additional Adjustments During Voting (applied inside `_vote_as_village`)

| Keyword | Target | Change |
|---------|--------|--------|
| "I recommend voting for [X]" | Named player | **+0.7** |
| "considering voting for [X]" / "either [X]" | Target | **+0.5** |

All final values are clipped to **0.0–1.0**.

---

## 14. Voting Logic Details

### Village Team (`_vote_as_village`)

```
1. If known_wolves is non-empty, vote for them immediately
2. Calculate wolf_probs = _calculate_wolf_probabilities(is_voting=True)
3. Adjust wolf_probs based on contradiction-pointing keywords in discussion log
4. Vote for the player with the highest wolf_prob
```

### Werewolf (`_vote_as_werewolf`)

```
1. Exclude allies (original_role_map == WEREWOLF) from candidates
2. Tally accusation_counts from village team's discussion statements
   (ignore statements by allies and self)
3. Bandwagon-vote for the most-accused player
```

---

## 15. Lie Detection System

`_detect_lie(pid, statement)` sets the `is_lie` flag for each statement.

```python
believed = _believed_role(pid, state)  # function in recorder.py

# "I am [role]" format
if f"I am {role_name}" in statement and role_name != believed:
    return True

# Seer claim
if "I am the seer" in statement and "seer" != believed:
    return True

# Robber claim
if "I am the robber" in statement and "I swapped" in statement and "robber" != believed:
    return True
```

Logic of `_believed_role` (recorder.py):
- `knowledge["new_role"]` is werewolf → return "werewolf"
- `knowledge["new_role"]` is other → return "robber"
- Otherwise → return the role from `original_role_map`

---

## 16. Statement Parse System

### `_parse_seer_claims(state)`

Parses seer claim statements from the discussion log and returns a list of `(claimer, target, result)`.

**Match conditions:**
- Statement contains "seer"
- Contains "I checked [other]" or "I saw [other]"
- Contains one of: "result was [role]", "they were [role]", "turned out [role]"

### `_parse_robber_claims(state)`

Parses robber claim statements and returns a list of `(claimer, swap_target, new_role)`.

**Match conditions:**
- Statement contains "robber"
- Contains "swapped with [other]"
- New role extracted from "I am now [role]" (or None if absent)

---

## 17. Training Data Structure

### Files

| File | Content |
|------|---------|
| `data/game_XXXX.jsonl` | Individual game log (1 file per game) |
| `data/finetune_dataset.jsonl` | Merged fine-tuning dataset across all games |

The `data/` folder is excluded via `.gitignore` (files are too large to commit).

### Record Types

#### statement

```json
{
  "type": "statement",
  "player_id": "Alice",
  "role": "seer",           // believed_role (role the speaker thinks they are)
  "true_role": "seer",      // actual current role (post-swap role_map)
  "original_role": "seer",  // originally distributed role (original_role_map)
  "statement": "I am the seer. ...",
  "is_lie": false,
  "reasoning": "Claiming seer result. ..."
}
```

#### vote

```json
{
  "type": "vote",
  "voter": "Alice",
  "voter_role": "seer",       // voter's believed_role
  "voter_true_role": "seer",  // voter's current actual role
  "target": "Bob"
}
```

#### meta

```json
{
  "type": "meta",
  "game_id": "xxxxxxxx",
  "timestamp": "20260608_xxxxxx",
  "players": ["Alice", "Bob", "Carol", "Dave", "Eve"],
  "role_map": {"Alice": "seer", ...},
  "original_role_map": {"Alice": "seer", ...},
  "graveyard": ["villager", "werewolf"],
  "result": {
    "executed": ["Bob"],
    "winner": "village"
  }
}
```

### Role Field Usage

| Field | Meaning | Use case |
|-------|---------|---------|
| `role` | believed_role (role driving the statement) | Learning intent and strategy behind statements |
| `true_role` | Current role after swap | Objective correctness judgment |
| `original_role` | Originally distributed role | Understanding initial game state |

---

## 18. Statistics

Data from 3,000 games / 15 statements per game.

### Win Rate

| Team | Win Rate |
|------|---------|
| Village team | **50.6%** |
| Werewolf team | **49.4%** |

### Voting Accuracy (rate of voting for a werewolf)

| Role | Accuracy |
|------|---------|
| Robber | 67.2% |
| Seer | 63.8% |
| Werewolf | 53.5% |
| Villager | 7.9% |

### Werewolf Win Rate by Strategy

| Strategy | Werewolf win rate | Notes |
|----------|-----------------|-------|
| Seer disguise | 45.1% | Exposed by contradiction detection |
| Robber disguise | 70.1% | Hard to verify, very effective |
| Villager camouflage | 61.2% | Weakened by silence penalty |
| Mixed strategy | 48.2% | Balanced overall |

### Seer Hit Rate and Win Rate

| Situation | Occurrence | Village win rate |
|-----------|-----------|-----------------|
| Seer hit a werewolf | 14.3% | **72.0%** |
| Seer did not hit a werewolf | 57.4% | 41.3% |
| Seer did not claim | 28.3% | 51.6% |

### Contradiction Detection Rate

| Pattern | Occurrence rate |
|---------|---------------|
| Overall | 12.6% |
| Pattern 1 (fake seer confirmed) | 9.3% |
| Pattern 2 (fake robber confirmed) | 3.3% |

### First Statement Timing

| Role | Average | Median | Main distribution |
|------|---------|--------|------------------|
| Robber | 1.8th turn | 1st | 1st: 55%, 2nd: 24% |
| Seer | 2.1th turn | 2nd | 1st: 46%, 2nd: 26% |
| Werewolf | 2.7th turn | 2nd | 1st: 23%, 2nd: 32% |
| Villager | 7.3th turn | 7th | Concentrated in 5th–9th |

### Training Data Scale

| Item | Value |
|------|-------|
| Number of games | 3,000 |
| Training samples | 45,000 |

---

## 19. Rule Change History

| Date | Change |
|------|--------|
| 2026-06-08 | Full rewrite of specification to complete version |
| 2026-06-08 | Separated silence penalty into voting-only (0 statements: +0.35 / 1 statement: +0.20) and ongoing verbosity penalty (N statements: +0.005×N×(N+1)/2) |
| 2026-06-08 | Changed wolf_prob increase for seer-confirmed werewolf target from +0.5 to +0.25 |
| 2026-06-08 | Added voting-phase silence penalties: 0 statements +0.35 / 1 statement +0.20 |
| 2026-06-08 | Added ongoing micro wolf_prob increase per statement count |
| 2026-06-08 | Set werewolf urgency score: 0 statements = 1.0 / 1+ statements = 2.0 |
| 2026-06-08 | Set villager first-statement score to 0.0 when total statements = 0 |
| 2026-06-08 | Set default werewolf strategy weights: seer 70% / robber 30% / villager 0% |
| 2026-06-08 | Set weights when ally has claimed seer: seer 5% / robber 40% / villager 55% |
| 2026-06-08 | Set weights when ally has claimed robber: seer 40% / robber 5% / villager 55% |
| 2026-06-08 | Robber must always perform a swap (no skipping) |
| 2026-06-08 | Contradiction detection set to 2 patterns: Pattern 1 (fake seer confirmed) and Pattern 2 (fake robber confirmed) |
| 2026-06-08 | Set total_statements to 15 |
