from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
import random
from collections import Counter

# ============================================================
# モデル
# ============================================================

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}  # 3=弱い, 2=強い

RANK_NAMES = {1: '大富豪', 2: '富豪', 3: '平民', 4: '大貧民'}

CARD_W = 62
CARD_H = 92
CARD_GAP = 6
RED_SUITS = {'♥', '♦'}


class Card:
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
        self.value = RANK_VALUES[rank]

    def __repr__(self):
        return f"{self.suit}{self.rank}"

    def __eq__(self, other):
        return self.suit == other.suit and self.rank == other.rank

    def __hash__(self):
        return hash((self.suit, self.rank))

    def __lt__(self, other):
        if self.value != other.value:
            return self.value < other.value
        return SUITS.index(self.suit) < SUITS.index(other.suit)


class Player:
    def __init__(self, name, is_human=False):
        self.name = name
        self.hand: list[Card] = []
        self.is_human = is_human
        self.passed = False
        self.finished = False
        self.final_rank: int | None = None

    def sort_hand(self):
        self.hand.sort(key=lambda c: (c.value, SUITS.index(c.suit)))


class Game:
    def __init__(self):
        self.players = [
            Player('あなた', is_human=True),
            Player('CPU 左'),
            Player('CPU 上'),
            Player('CPU 右'),
        ]
        self.table_cards: list[Card] = []   # 場に出ている最後の手
        self.table_count: int = 0           # 場の枚数
        self.last_played_idx: int | None = None
        self.finish_order: list[Player] = []
        self._deal()

    # ----- セットアップ -----

    def _deal(self):
        deck = [Card(s, r) for s in SUITS for r in RANKS]
        random.shuffle(deck)
        for i, p in enumerate(self.players):
            p.hand = deck[i * 13:(i + 1) * 13]
            p.sort_hand()
            p.passed = False
            p.finished = False
            p.final_rank = None

        self.table_cards = []
        self.table_count = 0
        self.last_played_idx = None
        self.finish_order = []

        # ♣3 を持つプレイヤーが先手
        self.current_idx = 0
        for i, p in enumerate(self.players):
            if any(c.suit == '♣' and c.rank == '3' for c in p.hand):
                self.current_idx = i
                break

    # ----- クエリ -----

    def active_players(self) -> list[Player]:
        return [p for p in self.players if not p.finished]

    def is_game_over(self) -> bool:
        return len(self.active_players()) <= 1

    def can_play(self, cards: list[Card]) -> bool:
        if not cards:
            return False
        # すべて同じランク
        if len({c.rank for c in cards}) != 1:
            return False
        # 場が空 → 最初のプレイ
        if not self.table_cards:
            # ♣3 を持っているなら ♣3 を含まなければならない
            player = self.players[self.current_idx]
            has_club3 = any(c.suit == '♣' and c.rank == '3' for c in player.hand)
            if has_club3:
                return any(c.suit == '♣' and c.rank == '3' for c in cards)
            return True
        # 枚数一致 & 強い
        if len(cards) != self.table_count:
            return False
        return cards[0].value > self.table_cards[0].value

    def can_pass(self) -> bool:
        return bool(self.table_cards)  # 場が空のときはパス不可

    def _all_others_passed(self) -> bool:
        """last_played_idx 以外のアクティブプレイヤー全員がパスしたか"""
        if self.last_played_idx is None:
            return False
        for i, p in enumerate(self.players):
            if i == self.last_played_idx:
                continue
            if not p.finished and not p.passed:
                return False
        return True

    # ----- アクション -----

    def play_cards(self, cards: list[Card]) -> bool:
        if not self.can_play(cards):
            return False
        player = self.players[self.current_idx]
        for c in cards:
            player.hand.remove(c)
        player.sort_hand()
        self.table_cards = cards[:]
        self.table_count = len(cards)
        self.last_played_idx = self.current_idx
        # パスリセット
        for p in self.players:
            p.passed = False
        # 上がり判定
        if not player.hand:
            player.finished = True
            player.final_rank = len(self.finish_order) + 1
            self.finish_order.append(player)
        return True

    def pass_turn(self):
        self.players[self.current_idx].passed = True
        if self._all_others_passed():
            self._clear_table()

    def _clear_table(self):
        self.table_cards = []
        self.table_count = 0
        for p in self.players:
            p.passed = False
        # 最後に出した人からスタート（そちらへ戻す）
        self.current_idx = self.last_played_idx  # type: ignore
        self.last_played_idx = None

    def advance_turn(self):
        n = len(self.players)
        for _ in range(n):
            self.current_idx = (self.current_idx + 1) % n
            p = self.players[self.current_idx]
            if not p.finished and not p.passed:
                return

    def finalize(self):
        """ゲーム終了時、残り1人（最下位）を確定させる"""
        remaining = self.active_players()
        for p in remaining:
            if not p.finished:
                p.final_rank = len(self.finish_order) + 1
                p.finished = True
                self.finish_order.append(p)

    # ----- CPU AI -----

    def ai_choose(self) -> list[Card] | None:
        player = self.players[self.current_idx]
        hand = player.hand
        count = self.table_count if self.table_cards else 1
        min_val = self.table_cards[0].value if self.table_cards else -1

        by_rank: dict[str, list[Card]] = {}
        for c in hand:
            by_rank.setdefault(c.rank, []).append(c)

        candidates: list[list[Card]] = []
        for rank, cards in by_rank.items():
            if len(cards) >= count and RANK_VALUES[rank] > min_val:
                candidates.append(sorted(cards)[:count])

        if not candidates:
            return None  # パス
        # 最弱の組み合わせを選ぶ（控えめな AI）
        return min(candidates, key=lambda cs: cs[0].value)


# ============================================================
# GUI
# ============================================================

BG = '#076324'
CARD_BG = '#FFFFFF'
CARD_SEL = '#FFFACD'
CPU_BACK = '#1A237E'
OUTLINE_NORMAL = '#555555'
OUTLINE_SEL = '#FF0000'


class DaifugouApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('大富豪')
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.game = Game()
        self.selected: list[Card] = []
        self._card_rects: list[tuple[int, int, int, int, Card]] = []  # x1,y1,x2,y2,card
        self._cpu_pending = False

        self._build_ui()
        self._refresh()
        self._maybe_schedule_cpu()

    # ============================================================
    # UI 構築
    # ============================================================

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # ---- 上段: CPU 情報 ----
        top = tk.Frame(self.root, bg=BG)
        top.grid(row=0, column=0, sticky='ew', padx=8, pady=4)
        top.columnconfigure((0, 1, 2), weight=1)

        self.cpu_labels: list[tk.Label] = []
        for col in range(3):
            lbl = tk.Label(top, text='', bg=BG, fg='white',
                           font=('Arial', 12, 'bold'))
            lbl.grid(row=0, column=col, padx=4)
            self.cpu_labels.append(lbl)

        # ---- 中段: 場 ----
        mid = tk.Frame(self.root, bg=BG)
        mid.grid(row=1, column=0, sticky='nsew', padx=8, pady=2)
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)

        self.table_canvas = tk.Canvas(mid, bg=BG, highlightthickness=0)
        self.table_canvas.grid(row=0, column=0, sticky='nsew')

        # ---- ステータス行 ----
        self.status_lbl = tk.Label(self.root, text='', bg=BG, fg='#FFD700',
                                   font=('Arial', 13, 'bold'))
        self.status_lbl.grid(row=2, column=0, pady=2)

        # ---- 下段: 手札 ----
        hand_frame = tk.Frame(self.root, bg=BG)
        hand_frame.grid(row=3, column=0, sticky='ew', padx=8, pady=2)
        hand_frame.columnconfigure(0, weight=1)

        self.hand_canvas = tk.Canvas(hand_frame, bg=BG, height=CARD_H + 24,
                                     highlightthickness=0)
        self.hand_canvas.grid(row=0, column=0, sticky='ew')
        self.hand_canvas.bind('<Button-1>', self._on_hand_click)
        self.hand_canvas.bind('<Configure>', lambda e: self._draw_hand())

        # ---- ボタン ----
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.grid(row=4, column=0, pady=6)

        self.play_btn = tk.Button(
            btn_frame, text='カードを出す', command=self._play,
            font=('Arial', 12, 'bold'), width=14, bg='#FFD700', fg='#222',
            relief='raised', cursor='hand2',
        )
        self.play_btn.pack(side='left', padx=10)

        self.pass_btn = tk.Button(
            btn_frame, text='パス', command=self._pass,
            font=('Arial', 12, 'bold'), width=8, bg='#FF6B6B', fg='white',
            relief='raised', cursor='hand2',
        )
        self.pass_btn.pack(side='left', padx=10)

    # ============================================================
    # カード描画ユーティリティ
    # ============================================================

    def _draw_card(self, canvas: tk.Canvas, x: int, y: int, card: Card,
                   selected=False, face_up=True):
        fill = CARD_SEL if selected else CARD_BG
        outline = OUTLINE_SEL if selected else OUTLINE_NORMAL
        lw = 3 if selected else 1
        canvas.create_rectangle(x, y, x + CARD_W, y + CARD_H,
                                 fill=fill, outline=outline, width=lw,
                                 tags='card')
        if face_up:
            color = '#CC0000' if card.suit in RED_SUITS else '#111111'
            canvas.create_text(x + CARD_W // 2, y + CARD_H // 2,
                                text=f'{card.suit}\n{card.rank}',
                                fill=color, font=('Arial', 14, 'bold'),
                                tags='card')
        else:
            canvas.create_rectangle(x + 5, y + 5, x + CARD_W - 5, y + CARD_H - 5,
                                     fill=CPU_BACK, outline='#3F51B5',
                                     tags='card')

    def _draw_cpu_card_back(self, canvas, cx, cy, count):
        """裏向きのカードを重ねて描画"""
        canvas.delete('all')
        fan_offset = min(14, (CARD_W * 2) // max(count, 1))
        total_w = CARD_W + fan_offset * (count - 1)
        sx = cx - total_w // 2
        for i in range(count):
            self._draw_card(canvas, sx + i * fan_offset, 5, Card('♠', '3'),
                            face_up=False)

    # ============================================================
    # 全体リフレッシュ
    # ============================================================

    def _refresh(self):
        g = self.game
        cur = g.players[g.current_idx]

        # ---- CPU ラベル更新 ----
        for i, lbl in enumerate(self.cpu_labels):
            p = g.players[i + 1]
            arrow = ' ◀' if g.current_idx == i + 1 else ''
            if p.finished:
                rank_name = RANK_NAMES.get(p.final_rank, f'{p.final_rank}位')
                info = f'[{rank_name}]'
            else:
                info = f'({len(p.hand)}枚)'
            lbl.config(text=f'{p.name} {info}{arrow}')

        # ---- 場 ----
        self._draw_table()

        # ---- ステータス ----
        if cur.is_human and not cur.finished:
            self.status_lbl.config(text='あなたのターンです')
        elif cur.finished:
            self.status_lbl.config(text='')
        else:
            self.status_lbl.config(text=f'{cur.name} が考えています...')

        # ---- 手札 ----
        self._draw_hand()

        # ---- ボタン有効/無効 ----
        my_turn = (g.current_idx == 0 and not g.players[0].finished
                   and not g.is_game_over())
        self.play_btn.config(state='normal' if my_turn else 'disabled')
        self.pass_btn.config(
            state='normal' if my_turn and g.can_pass() else 'disabled')

    def _draw_table(self):
        canvas = self.table_canvas
        canvas.delete('all')
        cards = self.game.table_cards
        if not cards:
            canvas.create_text(
                canvas.winfo_width() // 2 or 300,
                canvas.winfo_height() // 2 or 75,
                text='場は空です', fill='#88BB88', font=('Arial', 14))
            return
        total_w = len(cards) * (CARD_W + CARD_GAP) - CARD_GAP
        cx = canvas.winfo_width() // 2 or 300
        cy = canvas.winfo_height() // 2 or 75
        sx = cx - total_w // 2
        sy = cy - CARD_H // 2
        for i, card in enumerate(cards):
            self._draw_card(canvas, sx + i * (CARD_W + CARD_GAP), sy, card)

    def _draw_hand(self):
        canvas = self.hand_canvas
        canvas.delete('all')
        hand = self.game.players[0].hand
        self._card_rects = []
        if not hand:
            return
        cw = canvas.winfo_width() or 700
        total_w = len(hand) * (CARD_W + CARD_GAP) - CARD_GAP
        sx = max(4, (cw - total_w) // 2)
        y_base = 14

        for i, card in enumerate(hand):
            x = sx + i * (CARD_W + CARD_GAP)
            sel = card in self.selected
            y = y_base - 12 if sel else y_base
            self._draw_card(canvas, x, y, card, selected=sel)
            self._card_rects.append((x, y_base, x + CARD_W, y_base + CARD_H, card))

    # ============================================================
    # イベント
    # ============================================================

    def _on_hand_click(self, event):
        if self.game.current_idx != 0:
            return
        x, y = event.x, event.y
        # 上から順に確認（後ろのカードが優先されないよう逆順）
        for x1, y1, x2, y2, card in reversed(self._card_rects):
            # 選択済みは 12px 上にあるので両方チェック
            if x1 <= x <= x2 and (y1 - 14 <= y <= y2):
                if card in self.selected:
                    self.selected.remove(card)
                else:
                    self.selected.append(card)
                self._draw_hand()
                return

    def _play(self):
        if not self.selected:
            messagebox.showwarning('選択なし', 'カードを選択してください')
            return
        g = self.game
        cards = self.selected[:]
        if not g.can_play(cards):
            messagebox.showwarning('無効な手', 'そのカードは出せません\n（枚数が違う・強さが足りない・♣3 を含める必要があります）')
            return
        g.play_cards(cards)
        self.selected = []
        self._after_action()

    def _pass(self):
        self.game.pass_turn()
        self.selected = []
        self._after_action()

    def _after_action(self):
        g = self.game
        if g.is_game_over():
            g.finalize()
            self._refresh()
            self._show_result()
            return
        g.advance_turn()
        self._refresh()
        self._maybe_schedule_cpu()

    def _maybe_schedule_cpu(self):
        g = self.game
        p = g.players[g.current_idx]
        if not p.is_human and not p.finished and not g.is_game_over():
            self.root.after(700, self._cpu_step)

    def _cpu_step(self):
        g = self.game
        p = g.players[g.current_idx]
        if p.is_human or p.finished:
            return

        cards = g.ai_choose()
        if cards:
            g.play_cards(cards)
        else:
            g.pass_turn()

        if g.is_game_over():
            g.finalize()
            self._refresh()
            self._show_result()
            return

        g.advance_turn()
        self._refresh()
        self._maybe_schedule_cpu()

    # ============================================================
    # 結果表示
    # ============================================================

    def _show_result(self):
        lines = ['ゲーム終了!\n']
        for p in self.game.finish_order:
            rank_name = RANK_NAMES.get(p.final_rank, f'{p.final_rank}位')
            lines.append(f'{rank_name}: {p.name}')
        msg = '\n'.join(lines)
        if messagebox.askyesno('結果', msg + '\n\nもう一度プレイしますか？'):
            self.game = Game()
            self.selected = []
            self._refresh()
            self._maybe_schedule_cpu()


# ============================================================
# エントリポイント
# ============================================================

if __name__ == '__main__':
    root = tk.Tk()
    root.geometry('820x620')
    root.minsize(600, 480)
    DaifugouApp(root)
    root.mainloop()
