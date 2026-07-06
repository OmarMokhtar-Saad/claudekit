<p align="center">
  <img src="https://img.shields.io/badge/ClaudeKit-v2.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
</p>

<h1 align="center">ClaudeKit</h1>

<p align="center">
  <strong><a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a> 向けの本番グレードのマルチエージェントオーケストレーションシステム。</strong><br>
  構造化された計画。レビューゲート。安全な実行。品質検証。あらゆる言語に対応。
</p>

<p align="center">
  <a href="#クイックスタート">クイックスタート</a> &middot;
  <a href="#仕組み">仕組み</a> &middot;
  <a href="#コマンド">コマンド</a> &middot;
  <a href="#エージェント">エージェント</a> &middot;
  <a href="#コントリビュート">コントリビュート</a>
</p>

---

### 言語を選択 | Select Language

[English](../README.md) | [العربية](README.ar.md) | [中文](README.zh.md) | [Espanol](README.es.md) | [Francais](README.fr.md) | **日本語** | [한국어](README.ko.md)

---

## なぜ ClaudeKit なのか？

Claude Code は単体でも強力です。ClaudeKit はそれを**構造化され、安全で、監査可能**にします。

ClaudeKit なしでは、AIアシスタントは直接変更を行います -- 計画なし、レビューなし、ロールバックなし。ClaudeKit があれば、すべての変更がパイプラインに従います：計画し、レビューし、安全に実行し、結果を検証します。

### コアコンポーネント

| コンポーネント | 数量 | 説明 |
|------------|------|------|
| エージェント | 13 | 各タスク専門のエージェント |
| コマンド | 20+ | すぐに使えるコマンド |
| スキル | 55+ | 再利用可能なスキル |
| モード | 7 | 異なる動作モード |
| セーフティガード | 29 | すべての設定を検証するガード |
| 言語テンプレート | 11 | Python、TypeScript、Java、Go など対応 |
| MCP サーバー | 5 | モデルコンテキストプロトコル統合 |

---

## クイックスタート

### インストール

```bash
git clone https://github.com/OmarMokhtar-Saad/claudekit.git
./claudekit/install.sh /path/to/your-project --full
```

インストーラーはプロジェクトの言語を自動検出し、`.claude/` ディレクトリをプロジェクトにコピーし、`CLAUDE.md` と `CONSTITUTION.md` を生成し、ビルド/テスト/リントコマンドでフックを設定します。

### インストールオプション

```bash
# フルインストール（エージェント + コマンド + スキル + フック + オペレーション）
./install.sh ./my-project --full

# 最小インストール（エージェント + コマンド + オペレーションのみ）
./install.sh ./my-project --minimal

# 言語を事前設定
./install.sh ./my-project --full --language typescript

# 既存のインストールを上書き
./install.sh ./my-project --full --force
```

### 使い方

Claude Code でプロジェクトを開き、実行します：

```
/plan JWT トークンを使ったユーザー認証を追加
```

ClaudeKit が引き継ぎます -- プランナーがコードベースを探索し、ops.json 設定付きの計画を作成し、レビュアーが検証し、インプリメンターが自動バックアップ付きで実行し、ベリファイアーが結果を確認します。

---

## コマンド

| コマンド | 説明 | 例 |
|---------|------|-----|
| `/plan` | ops.json 付きの実装計画を作成 | `/plan API にレート制限を追加` |
| `/review` | 計画を検証（閾値 90/100） | `/review` |
| `/implement` | 承認済み計画を実行 | `/implement` |
| `/verify` | 品質チェックを実行（閾値 80/100） | `/verify` |
| `/debug` | バグを診断（読み取り専用） | `/debug なぜログインが 500 を返すのか？` |
| `/docs` | ドキュメントを生成 | `/docs 認証モジュールの API リファレンス` |
| `/git` | Git 操作 | `/git commit "feat: 認証追加"` |
| `/coordinator` | マルチエージェントオーケストレーション | `/coordinator データベーススキーマの移行` |
| `/explore` | コードベースのアーキテクチャを探索 | `/explore 認証モジュールはどう動作するか？` |
| `/security` | セキュリティ分析 | `/security 認証モジュールの脆弱性をスキャン` |
| `/test` | テストの生成と実行 | `/test src/services/auth.ts --generate` |
| `/deploy` | リリース準備とデプロイ | `/deploy release` |

---

## エージェント

| エージェント | 責任 | モデル |
|------------|------|--------|
| **コーディネーター** | タスク分類、ワークフロー調整、エージェント引き継ぎ管理 | Sonnet |
| **プランナー** | コードベース探索、実装計画 + ops.json 設定の作成 | Sonnet |
| **レビュアー** | 多次元計画検証 -- 計画品質(40%)、アーキテクチャ(30%)、セキュリティ(30%) | Opus |
| **インプリメンター** | 自動バックアップ付きでオペレーションスクリプト経由で承認済み計画を実行 | Sonnet |
| **ベリファイアー** | 品質検証 -- 静的解析(30%)、テスト(40%)、カバレッジ(30%) | Haiku |
| **デバッガー** | 4フェーズの体系的デバッグによる読み取り専用の根本原因分析 | Opus |
| **ドキュメンター** | 技術ドキュメントの作成と保守 | Haiku |
| **GitOps** | ブランチ、コミット、PR作成、リリース管理 | Haiku |
| **エクスプローラー** | 高速なコードベース探索、パターン発見、アーキテクチャマッピング | Sonnet |
| **テスター** | 専門テスト作成 -- ユニット、統合、E2E、カバレッジギャップ分析 | Sonnet |
| **セキュリティスキャナー** | OWASP Top 10 スキャン、シークレット検出、依存関係 CVE 分析 | Opus |
| **DevOps** | CI/CD パイプライン、コンテナ化、デプロイ、Infrastructure as Code | Sonnet |
| **データベースアーキテクト** | スキーマ設計、マイグレーション、クエリ最適化、データモデリング | Sonnet |

---

## 動作モード

| モード | 説明 |
|--------|------|
| **デフォルト** | 完全な説明と出力フォーマットによる通常運用 |
| **ブレインストーム** | 実装制約なしの自由なアイデア生成 |
| **トークン効率** | 40-70% のトークン節約を目標とした圧縮出力 |

---

## 仕様駆動ワークフロー

1. `specs/` に仕様を記述
2. `/plan` を実行して仕様から計画
3. レビュアーが仕様に対して検証
4. ベリファイアーが仕様への準拠を確認

---

## コントリビュート

コントリビュートを歓迎します！詳細は[コントリビューションガイド](../CONTRIBUTING.md)をご覧ください。

---

## ライセンス

MIT -- 詳細は [LICENSE](../LICENSE) をご覧ください。
