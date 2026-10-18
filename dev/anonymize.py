"""ゲームログを匿名化する。

プレイヤー名を P1〜P5 に置換し、players_meta の type/model 情報を除去する。
匿名化ログを output_dir に保存し、正解ラベルを ground_truth.jsonl に書き出す。

名前の置換は実名そのものだけでなく、**略称・部分名・敬称つき・かな読み**も対象にする
（例: 「野比のび太」→「のび太」「のび太くん」、「円谷光彦」→「光彦」、
      漢字名のかな読みで呼ばれたケースなど）。
辞書にない当て字読み（例: 乃木吊助→つりすけ）など、機械的に導けない呼称は
`--aliases` で補助辞書を渡すことで一度の宣言で全ログに適用できる。

使い方:
    python -m dev.anonymize                            # data/ → data/anon/
    python -m dev.anonymize --input data/ --output data/anon/
    python -m dev.anonymize --games 20261013           # 日付フィルタ
    python -m dev.anonymize --aliases aliases.json     # 補助別名辞書 {"つりすけ":"乃木吊助", ...}
"""
from __future__ import annotations
import argparse
import json
import random
import re
import unicodedata
from pathlib import Path

# ─ かな読み（任意依存）。無くてもルール置換は動く ─
try:
    import pykakasi  # type: ignore
    _KKS = pykakasi.kakasi()
except Exception:  # pragma: no cover
    _KKS = None

# エイリアスにしてはいけない一般語・ゲーム用語（部分名由来の誤置換を防ぐ）
# ※ プレイヤーがゲーム用語を含む名前を付けた場合でも、フルネームは無条件に
#    置換対象になる（下記は「部分名」としての採用だけを抑止する）。
_STOPWORDS = {
    "怪盗", "占い", "占い師", "人狼", "村人", "市民", "狼", "墓地", "役職",
    "投票", "処刑", "仲間", "陣営", "結果", "カード", "交換", "議論", "夜",
    "墓", "占", "村", "狼陣営", "村人陣営",
    # 処刑まわりの動詞・頻出語（「吊る」等を名前に含む人対策）
    "吊る", "吊り", "吊って", "吊", "つる", "べき", "ベキ", "吊るべき",
    "白", "黒", "しろ", "くろ", "グレー", "ぐれー",
}

# 敬称（名前の直後にあれば一緒に消費して P◯ に畳む）
_HONORIFICS = ["先生", "さま", "ちゃま", "さん", "くん", "ちゃん", "君", "氏", "様"]
_HON_GROUP = "(?:" + "|".join(_HONORIFICS) + ")?"


# 区切り文字（名前内のハイフン・アンダースコア・空白・中黒）
_SEP_CHARS = "-_‐-―ー・/\\.　 "
_STRIP_SEP = {ord(c): None for c in "-_‐‑‒–—―/\\.・　 "}
_TO_FULL = str.maketrans("0123456789", "０１２３４５６７８９")
_TO_HALF = str.maketrans("０１２３４５６７８９", "0123456789")


def _variants(s: str) -> set[str]:
    """表記ゆれ（全角↔半角数字・区切り文字の有無・NFKC）を吸収した別表記を返す。
    例: 'LLM-3' → {'LLM-3','LLM3','LLM３', ...}"""
    base = {s, unicodedata.normalize("NFKC", s)}
    out: set[str] = set()
    for b in base:
        if not b:
            continue
        out.add(b)
        out.add(b.translate(_STRIP_SEP))   # 区切り文字を除去した形
    more: set[str] = set()
    for b in out:
        more.add(b.translate(_TO_FULL))    # 数字を全角に
        more.add(b.translate(_TO_HALF))    # 数字を半角に
    out |= more
    return {x for x in out if x}


def _is_kana_only(s: str) -> bool:
    for ch in s:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF or ch in "ー・　 ":
            continue
        return False
    return bool(s)


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _reading_hira(name: str) -> str:
    if _KKS is None:
        return ""
    try:
        return "".join(x["hira"] for x in _KKS.convert(name))
    except Exception:
        return ""


def _kakasi_parts(name: str) -> list[str]:
    if _KKS is None:
        return []
    try:
        return [x["orig"] for x in _KKS.convert(name)]
    except Exception:
        return []


def _acceptable(alias: str) -> bool:
    """部分名候補をエイリアスとして採用してよいか。"""
    a = alias.strip()
    if not a or a in _STOPWORDS:
        return False
    if a.isdigit():
        return False
    # ASCII断片は2文字以下を除外（"Ja" 等の誤爆防止。"KID" は可）
    if _is_ascii(a):
        return len(a) >= 3
    # かなのみの断片は2文字だと一般語に当たりやすいので3文字以上
    if _is_kana_only(a):
        return len(a) >= 3
    # 漢字を含む断片は2文字以上でよい（光彦 / 野比 / 壮太 …）
    return len(a) >= 2


def _derive_aliases(name: str) -> set[str]:
    """実名から、本文中で使われうる略称候補を機械生成する。
    full name 自体は含めない（呼び出し側で別途最優先に登録する）。"""
    cands: set[str] = set()
    n = len(name)

    # 接頭・接尾の部分文字列（略称は多くが名前の頭か末尾）
    for k in range(2, n):            # prefixes s[:k]  (len 2..n-1)
        cands.add(name[:k])
    for k in range(1, n - 1):        # suffixes s[k:]  (len 2..n-1)
        cands.add(name[k:])

    # kakasi 形態素（光彦 / 野比 / 藤井 / 壮太 …）
    for p in _kakasi_parts(name):
        cands.add(p)

    # かな読み（漢字名をかなで呼ぶケース）とその接尾
    hira = _reading_hira(name)
    if hira and hira != name:
        cands.add(hira)
        for k in range(1, len(hira) - 1):
            cands.add(hira[k:])

    return {c for c in cands if _acceptable(c)}


def _build_replacer(name_to_p: dict[str, str],
                    extra_aliases: dict[str, str] | None = None):
    """実名・略称 → P◯ を一括置換する関数を返す。
    - full name は最優先・無条件に登録
    - 派生エイリアスは、複数の実名に曖昧一致するものは安全のため破棄
    - 直後の敬称（さん/くん/君 等）も消費して P◯ に畳む
    """
    alias_to_p: dict[str, str] = {}          # 小文字キー → P◯
    ambiguous: set[str] = set()
    # 派生エイリアスがどの実名に紐づくか（曖昧検出用）
    derived_owner: dict[str, str] = {}

    # 1) 派生エイリアス（＋表記ゆれバリアント）を収集（曖昧なら破棄）
    for real, p in name_to_p.items():
        for a in _derive_aliases(real):
            for v in _variants(a):
                key = v.lower()
                if key in alias_to_p and alias_to_p[key] != p:
                    ambiguous.add(key)
                else:
                    alias_to_p[key] = p
                    derived_owner[key] = real
    for key in ambiguous:
        alias_to_p.pop(key, None)

    # 2) 補助辞書（手動宣言した略称。派生より優先）
    if extra_aliases:
        for alias, real in extra_aliases.items():
            if real in name_to_p and alias.strip():
                for v in _variants(alias.strip()):
                    alias_to_p[v.lower()] = name_to_p[real]

    # 3) full name（＋表記ゆれ）は最後に上書き登録（最優先・曖昧除外の対象外）
    for real, p in name_to_p.items():
        for v in _variants(real):
            alias_to_p[v.lower()] = p

    if not alias_to_p:
        return lambda text: text

    # 長い別名から順にマッチ（短い名が長い名の一部を食わないように）
    ordered = sorted(alias_to_p, key=len, reverse=True)
    pattern = re.compile(
        "(" + "|".join(re.escape(a) for a in ordered) + ")" + _HON_GROUP,
        flags=re.IGNORECASE,
    )

    def repl(m: re.Match) -> str:
        return alias_to_p.get(m.group(1).lower(), m.group(0))

    def sub(text):
        if not isinstance(text, str):
            return text
        return pattern.sub(repl, text)

    return sub


def anonymize_game(records: list[dict],
                   extra_aliases: dict[str, str] | None = None) -> tuple[list[dict], dict] | None:
    """1ゲームを匿名化して (anonymized_records, ground_truth) を返す。
    meta レコードがなければ None を返す。
    """
    meta = next((r for r in records if r.get("type") == "meta"), None)
    if not meta or "players_meta" not in meta:
        return None

    players: list[str] = meta["players"]
    pmeta: dict = meta["players_meta"]

    # ─ シャッフルして P1〜P5 に割り当て ─
    shuffled = players[:]
    random.shuffle(shuffled)
    name_to_p: dict[str, str] = {name: f"P{i+1}" for i, name in enumerate(shuffled)}
    p_to_name: dict[str, str] = {v: k for k, v in name_to_p.items()}

    # 正解ラベル
    truth = {
        "game_id": meta["game_id"],
        "map": {
            p_label: {
                "real_name": real_name,
                "type": pmeta.get(real_name, {}).get("type", "unknown"),
            }
            for p_label, real_name in p_to_name.items()
        },
    }

    # 実名・略称・かな読み・敬称つき を一括置換する関数
    sub = _build_replacer(name_to_p, extra_aliases)

    def sub_list(lst) -> list:
        return [sub(x) if isinstance(x, str) else x for x in (lst or [])]

    # ─ 各レコードを匿名化 ─
    anon_records: list[dict] = []
    for rec in records:
        t = rec.get("type")

        if t == "meta":
            anon = {
                "type": "meta",
                "schema_version": rec.get("schema_version"),
                "game_id": rec["game_id"],
                "timestamp": rec.get("timestamp"),
                "players": [name_to_p[p] for p in players],
                # type/model を除去したメタ（人数情報のみ残す）
                "players_meta": {
                    name_to_p[p]: {"index": i}
                    for i, p in enumerate(shuffled)
                },
                # 役職は判定の参考のため含める（開示情報として扱う）
                "role_map": {name_to_p[p]: v for p, v in rec.get("role_map", {}).items()},
                "original_role_map": {
                    name_to_p[p]: v for p, v in rec.get("original_role_map", {}).items()
                },
                "graveyard": rec.get("graveyard", []),
                "result": {
                    "winner": rec["result"]["winner"],
                    "executed": [name_to_p.get(p, p) for p in rec["result"].get("executed", [])],
                },
            }

        elif t == "statement":
            pid = rec.get("player_id", "")
            anon = {
                "type": "statement",
                "game_id": rec["game_id"],
                "order": rec.get("order"),
                "player_id": name_to_p.get(pid, pid),
                # player_type / model は除去
                "statement": sub(rec.get("statement", "")),
                "intent": rec.get("intent", ""),
                "target": sub(rec.get("target", "")),
                "result": rec.get("result", ""),
                "basis": sub_list(rec.get("basis", [])),
                # reasoning / knowledge / is_lie は推定の手がかりになるため除去
            }

        elif t == "vote":
            voter = rec.get("voter", "")
            target = rec.get("target", "")
            anon = {
                "type": "vote",
                "game_id": rec["game_id"],
                "voter": name_to_p.get(voter, voter),
                "target": name_to_p.get(target, target),
                # voter_type / voter_role は除去
            }

        else:
            anon = rec  # その他はそのまま

        anon_records.append(anon)

    return anon_records, truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/")
    ap.add_argument("--output", default="data/anon/")
    ap.add_argument("--games", default=None,
                    help="ファイル名に含まれる文字列でフィルタ（例: 20261013）")
    ap.add_argument("--aliases", default=None,
                    help='補助別名辞書 JSON（{"略称":"実名", ...}）。辞書にない読み等を補う')
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)

    extra_aliases = None
    if args.aliases:
        extra_aliases = json.loads(Path(args.aliases).read_text(encoding="utf-8"))

    if _KKS is None:
        print("[warn] pykakasi 未インストール: かな読みの照合はスキップします "
              "(pip install pykakasi で有効化)")

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob("game_*.jsonl"))
    if args.games:
        files = [f for f in files if args.games in f.name]

    truth_path = out_dir / "ground_truth.jsonl"
    truth_path.unlink(missing_ok=True)

    ok = skip = 0
    for fp in files:
        records = [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
        result = anonymize_game(records, extra_aliases)
        if result is None:
            print(f"[skip] {fp.name} (meta なし)")
            skip += 1
            continue

        anon_records, truth = result
        out_path = out_dir / fp.name
        with open(out_path, "w", encoding="utf-8") as f:
            for r in anon_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(truth_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(truth, ensure_ascii=False) + "\n")

        types = [truth["map"][p]["type"] for p in sorted(truth["map"])]
        print(f"[ok] {fp.name} → {out_path.name}  types={types}")
        ok += 1

    print(f"\n完了: {ok} ゲーム匿名化 / {skip} スキップ")
    print(f"正解ラベル: {truth_path}")


if __name__ == "__main__":
    main()
