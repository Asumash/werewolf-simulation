# dev/ — 開発・分析用スクリプト

本番アプリ（`server.py`）には不要な、開発中に使ったオフライン検証・データ生成・
分析用のスクリプト置き場です。

## 実行方法
リポジトリのルートから **モジュールとして** 実行してください（インポート解決のため）：

```bash
python -m dev.batch_run --games 200            # 全CPUで200戦（記録＋勝率集計）
python -m dev.batch_run --games 50 --llm 1     # 1席をLLMに（要APIキー）
python -m dev.batch_run --games 30 --llm 2 --models "openai/gpt-4o-mini,openai/gpt-3.5-turbo"  # モデル比較
python -m dev.analyze_games                    # data/ の評価指標を集計（現行schema≥2のみ）
python -m dev.analyze_games --all              # 旧データも含めて集計

# 人間らしさの軸
python -m dev.turing_eval --limit 40           # 発言を人間/AI判定し人間らしさスコア算出（要APIキー）
python -m dev.export_training --types human     # 人間ログを学習用(SFT JSONL/few-shot)に書き出し
python -m dev.batch_run --llm 1 --fewshot data/train/fewshot_human.json  # 人間例を注入して対戦
```

## 主なスクリプト
- `batch_run.py` … 無人バッチ対戦。CPU/LLMの席構成を指定して多数対戦を回し、
  各ゲームを `data/` に記録（種別・モデル・行動タグ付き）＋種別ごとの勝率を集計。
  **研究用データ生成・モデル比較の土台。**
- `analyze_games.py` … `data/` の対戦ログから評価指標を集計（勝率・種別/モデル別の
  強さ・投票精度・情報役職のCO率・intent分布）。**現行 schema≥2 のみを既定で対象。**
- `dataset.py` … 対戦ログを発言単位（文脈つき）で読み出す共通ローダ。
- `turing_eval.py` … LLM審判が発言を人間/AI判定し、ソース別の「人間らしさスコア」を算出。
- `export_training.py` … 対戦ログ（既定 human）を fine-tune 用 JSONL と few-shot 例に書き出し。
  → `batch_run --fewshot <bank.json>` で LLM に人間の口調を注入できる。
- `anonymize.py` … ログを匿名化（名前→P1〜P5、type/model除去）し `ground_truth.jsonl` を出力。
  実名の**完全一致だけでなく、略称・部分名（野比のび太→のび太）・敬称つき（のび太くん）・
  かな読み・表記ゆれ（LLM-3／LLM３）**も置換する。ゲーム用語（怪盗・占い・吊る等）は
  ストップワードで保護。かな読み照合は `pykakasi`（任意）。辞書外の当て字読みや無関係な
  あだ名（乃木吊助→つりすけ、光彦→元太君）は機械的に導けないため、必要なら
  `--aliases dict.json`（`{"つりすけ":"乃木吊助"}`）で一度宣言すれば全ログに適用できる。
- `run_cp_only.py` … 全員ルールベースCPで対戦（簡易）
- `main.py` … 旧CLI版（コンソールで人間＋CPU＋LLM）
- `generate_data.py` / `clean_data.py` … 学習データの生成・整形
- `analyze_*.py` / `check_*.py` / `debug_*.py` / `benchmark_*.py` … 各種検証・分析

> これらは開発補助であり、Webアプリの動作には影響しません。
