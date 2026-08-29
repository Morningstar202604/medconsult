<div align="center">

# 🏥 MedConsult · 汇診

**ローカル完結型の医療マルチエージェント診療プラットフォーム**
多専門 AI チーム · ドキュメント根拠 RAG · 医療計算ツール · 診療メモリ · プロンプトプール

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

`MIT License` `Python 3.10+` `データは手元から出ない`

</div>

---

## ⚠️ 免責事項

> MedConsult は**研究・デモ用プラットフォーム**です。医療機器ではなく、出力は**医学的助言ではありません**。実際の使用は現地の医療法規に従い、必ず担当医に相談してください。

## ✨ 主な機能

- 🤖 **本物のマルチエージェント構成**：患者・医師・検査・モデレーター・専門科エージェントが構造化プロトコルで協働し、根拠付きの結論に収束
- 👥 **診療ワークベンチ**：症状や匿名化カルテを提出 → 事前問診の確認 → 各専門科の独立意見とクロスディスカッション → 構造化レポート
- 📁 **ローカル文書ライブラリ**：カルテ・検査報告・ガイドライン（txt/md/pdf/docx）をローカル保存し、診療でリアルタイム引用
- 🔎 **RAG 検索ツール**：取り込み時にチャンク索引を自動生成し、関連断片を自動検索
- 🧮 **医療計算ツール**：MAP / BMI / Cockcroft-Gault クレアチニンクリアランスを自動計算しレポートに反映
- 🧠 **セッションメモリ**：自動アーカイブ・再生・削除
- 📝 **プロンプトプール**：各エージェントのシステムプロンプトを編集・保存・切替
- 🧰 **設定可能なサンドボックス**：ツールホワイトリスト・タイムアウト・ローカルデータ境界
- 🔌 **OpenAI 互換 LLM**：OpenAI / DeepSeek / GLM / Qwen / Ollama に対応、役割ごとにモデルを指定可能

## 🚀 クイックスタート

```bash
git clone https://github.com/Morningstar202604/medconsult.git
cd medconsult
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

**http://127.0.0.1:8765** を開くだけ。`config.json`（`config.json.example` 参照）またはアプリ内設定で LLM を 30 秒で接続できます。キーがなくても**スクリプトデモモード**で動作します。

## 📜 ライセンス

[MIT](LICENSE) © 2026 MedConsult Contributors · [AgentClinic](https://github.com/samuelschmidgall/AgentClinic)（MIT）ベース。詳細は [NOTICE](NOTICE)。

役に立ったら **Star ⭐** をお願いします！
