import os
import sys
from flask import Flask, request, jsonify
import logging
import requests
import json
import re
from datetime import datetime

app = Flask(__name__)

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# requests/urllib3 のDEBUGログを抑制
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- 設定読み込み ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "sekailabo_webhook_secret_2026")

# ヘルパー関数: IDから数字のみを抽出（最強の正規化）
def clean_id(input_id):
    """数字以外の文字を完全に削除して正規化"""
    if not input_id:
        return ""
    return re.sub(r"\D", "", str(input_id))

# 店舗ごとのサーバーURLマッピング（環境変数から読み込み）
# 形式: {"instagram_business_account_id": "https://restaurant-bot-url.railway.app/webhook"}
try:
    RESTAURANT_SERVERS_JSON = os.environ.get('RESTAURANT_SERVERS', '{}')
    logger.info(f"🔍 Raw RESTAURANT_SERVERS JSON: {RESTAURANT_SERVERS_JSON!r}")
    
    # JSONをパース
    raw_servers = json.loads(RESTAURANT_SERVERS_JSON)
    
    # キーを数字のみに正規化
    RESTAURANT_SERVERS = {}
    for key, value in raw_servers.items():
        clean_key = clean_id(key)
        clean_value = value.strip()
        RESTAURANT_SERVERS[clean_key] = clean_value
        logger.info(f"🔍 Normalized: {key!r} -> {clean_key!r} (len: {len(clean_key)})")
        # 各文字のコードを表示（17文字目の正体を暴く）
        logger.info(f"🔍 Key char codes: {[ord(c) for c in clean_key]}")
    
    logger.info(f"✅ Loaded {len(RESTAURANT_SERVERS)} restaurant servers")
    
except json.JSONDecodeError as e:
    logger.error(f"❌ Failed to parse RESTAURANT_SERVERS: {e}")
    RESTAURANT_SERVERS = {}

# 転送タイムアウト（秒）
FORWARD_TIMEOUT = int(os.environ.get('FORWARD_TIMEOUT', '30'))

# リトライ設定
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '3'))

# --- ヘルスチェック ---
@app.route('/health', methods=['GET'])
def health():
    """ヘルスチェックエンドポイント"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'restaurants_count': len(RESTAURANT_SERVERS)
    }), 200


# --- Webhook検証（GET） ---
@app.route('/webhook', methods=['GET'])
def webhook_verify():
    """
    Meta からのWebhook検証リクエストを処理
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    logger.info(f'📥 Webhook verification request: mode={mode}, token={token[:10]}...')
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info('✅ Webhook verified successfully')
        return challenge, 200
    else:
        logger.error('❌ Webhook verification failed')
        return 'Forbidden', 403


# --- Webhookイベント受信（POST） ---
@app.route('/webhook', methods=['POST'])
def webhook_receive():
    """
    Meta からのWebhookイベントを受信し、適切な店舗サーバーに転送
    """
    data = request.json
    
    # イベントタイプを取得
    try:
        entry = data.get('entry', [{}])[0]
        raw_page_id = str(entry.get('id'))
        
        # Page IDを数字のみに正規化（最強の正規化）
        page_id = clean_id(raw_page_id)
        
        changes = entry.get('changes', [])
        
        logger.info(f'📨 Webhook POST received')
        logger.info(f'📦 Raw Page ID: {raw_page_id!r}')
        logger.info(f'📦 Cleaned Page ID: {page_id!r} (len: {len(page_id)})')
        # 各文字のコードを表示（17文字目の正体を暴く）
        logger.info(f'🔍 Webhook ID char codes: {[ord(c) for c in page_id]}')
        logger.info(f'📋 Changes: {len(changes)} item(s)')
        
    except (KeyError, IndexError, AttributeError) as e:
        logger.error(f'❌ Invalid webhook data structure: {e}')
        return jsonify({'status': 'error', 'message': 'Invalid data structure'}), 400
    
    if not page_id:
        logger.error('❌ Page ID not found in webhook data')
        return jsonify({'status': 'error', 'message': 'Page ID missing'}), 400
    
    # 対応する店舗サーバーURLを取得
    logger.info(f'🔍 Looking for Page ID: {page_id!r}')
    logger.info(f'🔍 Available IDs: {list(RESTAURANT_SERVERS.keys())}')
    
    target_url = RESTAURANT_SERVERS.get(page_id)
    
    if target_url:
        logger.info(f'✅ Match found: {page_id} -> {target_url}')
    else:
        logger.warning(f'⚠️ Unknown Page ID: {page_id}')
        logger.warning(f'⚠️ Registered IDs: {list(RESTAURANT_SERVERS.keys())}')
        return jsonify({
            'status': 'ignored',
            'message': 'Unknown page - not registered in RESTAURANT_SERVERS'
        }), 200
    
    # 店舗サーバーに転送（リトライ機能付き）
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f'📤 Forwarding to {target_url} (attempt {attempt}/{MAX_RETRIES})')
            logger.info(f'📦 Forwarding data: {json.dumps(data, ensure_ascii=False)[:500]}...')
            
            response = requests.post(
                target_url,
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'X-Forwarded-By': 'Sekailabo-Webhook-Proxy'
                },
                timeout=FORWARD_TIMEOUT
            )
            
            logger.info(f'✅ Forward successful: {response.status_code} - {target_url}')
            logger.info(f'📥 Response: {response.text[:200]}')
            
            # ログに詳細を記録
            if response.status_code >= 400:
                logger.warning(f'⚠️ Target server returned error: {response.status_code} - {response.text[:200]}')
            
            return jsonify({
                'status': 'forwarded',
                'target': target_url,
                'target_status': response.status_code
            }), 200
        
        except requests.exceptions.Timeout:
            logger.error(f'❌ Timeout forwarding to {target_url} (attempt {attempt}/{MAX_RETRIES})')
            if attempt == MAX_RETRIES:
                return jsonify({
                    'status': 'error',
                    'message': 'Target server timeout after retries'
                }), 500
        
        except requests.exceptions.RequestException as e:
            logger.error(f'❌ Error forwarding to {target_url}: {str(e)} (attempt {attempt}/{MAX_RETRIES})')
            if attempt == MAX_RETRIES:
                return jsonify({
                    'status': 'error',
                    'message': f'Forward failed: {str(e)}'
                }), 500
    
    # ここには到達しないはず
    return jsonify({'status': 'error', 'message': 'Unexpected error'}), 500


# --- 管理用エンドポイント（店舗リスト確認） ---
@app.route('/admin/restaurants', methods=['GET'])
def list_restaurants():
    """
    登録されている店舗のリストを返す（デバッグ用）
    簡易的な認証: クエリパラメータで admin_token を確認
    """
    admin_token = request.args.get('admin_token')
    expected_token = os.environ.get('ADMIN_TOKEN', 'change_me_in_production')
    
    if admin_token != expected_token:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    restaurants = [
        {
            'page_id': page_id,
            'webhook_url': url
        }
        for page_id, url in RESTAURANT_SERVERS.items()
    ]
    
    return jsonify({
        'status': 'success',
        'count': len(restaurants),
        'restaurants': restaurants
    }), 200


# --- ルートエンドポイント ---
@app.route('/', methods=['GET'])
def home():
    """
    ルートページ - プロキシサーバーの情報を表示
    """
    return jsonify({
        'service': 'Sekailabo Webhook Proxy',
        'status': 'running',
        'version': '1.0.0',
        'restaurants_count': len(RESTAURANT_SERVERS),
        'endpoints': {
            'webhook': '/webhook (GET/POST)',
            'health': '/health',
            'admin': '/admin/restaurants?admin_token=xxx'
        }
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f'🚀 Starting Webhook Proxy Server on port {port}')
    logger.info(f'📋 Managing {len(RESTAURANT_SERVERS)} restaurant(s)')
    app.run(host='0.0.0.0', port=port, debug=False)
