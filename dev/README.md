# dev/ — 開発・分析用スクリプト

本番アプリ（`server.py`）には不要な、開発中に使ったオフライン検証・データ生成・
分析用のスクリプト置き場です。

## 実行方法
リポジトリのルートから **モジュールとして** 実行してください（インポート解決のため）：

```bash
python -m dev.run_cp_only 5      # 全CPUで5ゲーム対戦（動作確認）
python -m dev.generate_data 100  # 学習用データ生成
python -m dev.analyze_data       # 生成データの分析
```

## 主なスクリプト
- `run_cp_only.py` … 全員ルールベースCPで対戦
- `main.py` … 旧CLI版（コンソールで人間＋CPU＋LLM）
- `generate_data.py` / `clean_data.py` … 学習データの生成・整形
- `analyze_*.py` / `check_*.py` / `debug_*.py` / `benchmark_*.py` … 各種検証・分析

> これらは開発補助であり、Webアプリの動作には影響しません。
