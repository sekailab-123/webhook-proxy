# Sekailabo Webhook Proxy Server

このプロキシサーバーは、Meta（Instagram/Facebook）からのWebhookイベントを受信し、適切な店舗サーバーに転送する役割を担います。

## 🎯 目的

**問題**: Meta アプリのWebhook設定では、**1つのCallback URLしか設定できない**ため、複数店舗の管理が困難。

**解決策**: 中央プロキシサーバーが1つのWebhook URLでイベントを受信し、Page IDに基づいて各店舗サーバーに転送。

## 🏗️ アーキテクチャ

```
Meta (Instagram) 
    │
    │ Webhook Event (Page ID含む)
    ↓
┌─────────────────────────────┐
│  Webhook Proxy Server       │ ← このプロジェクト
│  (常時起動、月$5)           │
└─────────────────────────────┘
    │
    │ Page ID判定
    ├─→ 店舗A Bot (Serverless, 月$0.50)
    ├─→ 店舗B Bot (Serverless, 月$0.50)
    ├─→ 店舗C Bot (Serverless, 月$0.50)
    └─→ ...
```

## 📦 機能

- ✅ Webhook検証（GET）
- ✅ Webhookイベント受信（POST）
- ✅ Page IDによる店舗判定
- ✅ 各店舗サーバーへの転送
- ✅ リトライ機能（最大3回）
- ✅ ヘルスチェックエンドポイント
- ✅ 管理用エンドポイント（店舗リスト）

## 🚀 Railwayデプロイ手順

### 1. 新規プロジェクト作成

```bash
# Railwayにログイン
railway login

# 新規プロジェクト作成
railway init
# プロジェクト名: webhook-proxy

# このディレクトリをデプロイ
cd webhook-proxy
railway link
```

### 2. 環境変数設定

Railway Dashboard → プロジェクト → Variables で以下を設定:

```bash
VERIFY_TOKEN=sekailabo_webhook_secret_2026

# 店舗マッピング（JSON形式）
RESTAURANT_SERVERS={
  "123456789012345": "https://restaurant-a.railway.app/webhook",
  "234567890123456": "https://restaurant-b.railway.app/webhook",
  "345678901234567": "https://restaurant-c.railway.app/webhook"
}

# 管理用トークン（店舗リスト確認用）
ADMIN_TOKEN=your_secure_admin_token_here

# その他（オプション）
FORWARD_TIMEOUT=30
MAX_RETRIES=3
GUNICORN_WORKERS=2
```

**重要**: `RESTAURANT_SERVERS` は**1行のJSON文字列**として入力してください。改行を含めないこと。

### 3. デプロイ

```bash
# デプロイ実行
railway up

# ログ確認
railway logs
```

### 4. Serverless機能は**無効**に設定

⚠️ プロキシサーバーは**常時起動が必要**です:

1. Railway Dashboard → Settings
2. "Enable Serverless" を**オフ**に設定
3. 常時起動コスト: 月$5

### 5. URLを取得

```bash
# デプロイされたURLを確認
railway domain

# 例: https://webhook-proxy-production.up.railway.app
```

## 🔧 Meta Webhooks設定

### 1. Meta App Dashboard → Webhooks

1. **Callback URL**: `https://webhook-proxy-production.up.railway.app/webhook`
2. **Verify Token**: `sekailabo_webhook_secret_2026`
3. **Subscribe to**: `messages`, `messaging_postbacks`

### 2. ページを購読

各飲食店のFacebookページをアプリに接続:

1. Meta App Dashboard → Webhooks
2. "Webhooks Fields" → "messages" にチェック
3. 各ページをSubscribe

## 📝 環境変数の詳細

### RESTAURANT_SERVERS の設定例

```json
{
  "123456789012345": "https://restaurant-sekailabo.railway.app/webhook",
  "234567890123456": "https://restaurant-yakiniku.railway.app/webhook",
  "345678901234567": "https://restaurant-sushi.railway.app/webhook"
}
```

**Page IDの確認方法**:
1. Facebookページを開く
2. ページ設定 → ページ情報
3. "ページID" をコピー

または、Graph API Explorerを使用:
```bash
curl -X GET "https://graph.facebook.com/v21.0/me/accounts?access_token=YOUR_PAGE_TOKEN"
```

## 🔍 動作確認

### ヘルスチェック

```bash
curl https://webhook-proxy-production.up.railway.app/health
```

レスポンス例:
```json
{
  "status": "healthy",
  "timestamp": "2025-02-07T12:34:56.789Z",
  "restaurants_count": 3
}
```

### 店舗リスト確認

```bash
curl "https://webhook-proxy-production.up.railway.app/admin/restaurants?admin_token=your_secure_admin_token_here"
```

レスポンス例:
```json
{
  "status": "success",
  "count": 3,
  "restaurants": [
    {
      "page_id": "123456789012345",
      "webhook_url": "https://restaurant-a.railway.app/webhook"
    },
    ...
  ]
}
```

## 📊 ログ確認

```bash
# Railway ログをリアルタイム表示
railway logs

# 特定のログを検索
railway logs | grep "Page ID"
```

ログ例:
```
2025-02-07 12:34:56 - __main__ - INFO - 📨 Webhook POST received
2025-02-07 12:34:56 - __main__ - INFO - 📦 Page ID: 123456789012345
2025-02-07 12:34:56 - __main__ - INFO - 📤 Forwarding to https://restaurant-a.railway.app/webhook (attempt 1/3)
2025-02-07 12:34:57 - __main__ - INFO - ✅ Forward successful: 200 - https://restaurant-a.railway.app/webhook
```

## 🛠️ トラブルシューティング

### 問題1: Webhook検証が失敗する

**症状**: Meta App Dashboardで "Verify Token Mismatch" エラー

**解決**:
```bash
# 環境変数を確認
railway variables

# VERIFY_TOKEN が正しいか確認
# Meta Dashboard の Verify Token と一致させる
```

### 問題2: イベントが転送されない

**症状**: Webhook POSTを受信するが、店舗サーバーに転送されない

**解決**:
```bash
# ログを確認
railway logs | grep "Unknown Page ID"

# Page ID が RESTAURANT_SERVERS に登録されているか確認
railway variables | grep RESTAURANT_SERVERS
```

### 問題3: タイムアウトエラー

**症状**: `❌ Timeout forwarding to...` エラー

**解決**:
```bash
# FORWARD_TIMEOUT を延長
railway variables set FORWARD_TIMEOUT=60

# 店舗サーバーのログを確認（応答が遅い可能性）
```

## 📈 スケーリング

### 100店舗展開時の設定

```bash
# ワーカー数を増やす
railway variables set GUNICORN_WORKERS=4

# タイムアウトを調整
railway variables set FORWARD_TIMEOUT=45

# リトライ回数を調整
railway variables set MAX_RETRIES=2
```

**コスト**:
- プロキシサーバー（常時起動）: 月$5
- 100店舗 × $0.50 (Serverless): 月$50
- **合計**: 月$55
### 📊 送信制限について

#### API制限は「店舗ごと」に独立

重要なポイント: Instagram Messaging APIの制限は**アプリ単位ではなく、各店舗（Instagramアカウント）ごと**に計算されます。

- **1店舗あたり**: 200件/時（推奨値: 150-180件/時）
- **店舗間の独立**: 店舗Aが制限に達しても店舗B・Cには影響なし
- **100店舗の合計**: 理論上20,000件/時まで対応可能

#### ⚠️ 複数アプリ作成は禁止

**重要**: スケールアップのために「同じ機能の別アプリを作成する」ことは、Metaのポリシー違反（制限回避）に該当します。

- ❌ 制限回避目的の類似アプリ作成は禁止
- ❌ 違反時は全アプリ停止・ビジネスアカウント凍結のリスク
- ✅ 1つのアプリで複数店舗を管理する構成が正しい方法
- ✅ 現在のプロキシサーバー構成で100店舗以上に対応可能
## 🔐 セキュリティ

### 推奨設定

1. **VERIFY_TOKEN**: ランダムな64文字の文字列を使用
   ```bash
   # 例: openssl rand -base64 48
   ```

2. **ADMIN_TOKEN**: 管理用エンドポイントの保護
   ```bash
   # 強力なトークンを設定
   railway variables set ADMIN_TOKEN=$(openssl rand -base64 48)
   ```

3. **HTTPSのみ**: Railwayは自動でHTTPSを提供

4. **Rate Limiting**: 必要に応じてCloudflareなどを導入

## 📚 参考資料

- [Meta Webhooks Documentation](https://developers.facebook.com/docs/graph-api/webhooks)
- [Railway Documentation](https://docs.railway.app)
- [Flask Documentation](https://flask.palletsprojects.com)

## 🎯 次のステップ

1. ✅ プロキシサーバーのデプロイ
2. ✅ Meta Webhooks設定変更
3. ⬜ 既存の店舗サーバーに環境変数追加（必要に応じて）
4. ⬜ 新規店舗追加時の手順を標準化
5. ⬜ モニタリング・アラート設定（オプション）

---

**作成日**: 2025年2月7日  
**バージョン**: 1.0.0  
**作成者**: Sekailabo Team
