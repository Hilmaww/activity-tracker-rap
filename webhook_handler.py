"""
Webhook handler for Telegram bot (Alternative to polling)
Use this for production environments with high traffic
"""

from flask import Flask, request, Response
import json
import logging
from telegram import Update
from telegram_bot import application

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

webhook_app = Flask(__name__)

@webhook_app.route('/telegram/webhook', methods=['POST'])
async def webhook():
    """Handle incoming Telegram updates via webhook"""
    try:
        # Get the update from Telegram
        update_data = request.get_json()
        
        if update_data:
            update = Update.de_json(update_data, application.bot)
            await application.process_update(update)
            
        return Response(status=200)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return Response(status=500)

@webhook_app.route('/telegram/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "telegram-bot-webhook"}

if __name__ == '__main__':
    webhook_app.run(host='0.0.0.0', port=5001, debug=False)
