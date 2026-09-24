# dev/ — 開発・分析用スクリプト

本番アプリ（`server.py`）には不要な、開発中に使ったオフライン検証・データ生成・
分析用のスクリプト置き場です。

## 実行方法
リポジトリのルートから **モジュールとして** 実行してください（インポート解決のため）：

```bash
python -m dev.batch_run --games 200            # 全CPUで200戦（記録＋勝率集計）
python -m dev.batch_run --games 50 --llm 1     # 1席をLLMに（要APIキー）
python -m dev.run_cp_only 5                     # 全CPUで5ゲーム対戦（簡易確認）
python -m dev.analyze_data                      # 生成データの分析
```

## 主なスクリプト
- `batch_run.py` … 無人バッチ対戦。CPU/LLMの席構成を指定して多数対戦を回し、
  各ゲームを `data/` に記録（種別・モデル・行動タグ付き）＋種別ごとの勝率を集計。
  **研究用データ生成・モデル比較の土台。**
- `run_cp_only.py` … 全員ルールベースCPで対戦（簡易）
- `main.py` … 旧CLI版（コンソールで人間＋CPU＋LLM）
- `generate_data.py` / `clean_data.py` … 学習データの生成・整形
- `analyze_*.py` / `check_*.py` / `debug_*.py` / `benchmark_*.py` … 各種検証・分析

> これらは開発補助であり、Webアプリの動作には影響しません。
