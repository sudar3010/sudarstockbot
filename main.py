# app.py
import os
import datetime
import threading
import asyncio
from flask import Flask
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client

# ==========================
# 🔹 Config
# ==========================
# Telegram Bot Token
BOT_TOKEN = "8108841318:AAE8aoEPqOU6SrwzRvtAjOQAG9AjD2IT2NI"

# Supabase credentials
SUPABASE_URL = "https://xdkcliccyvzbikpxfwds.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhka2NsaWNjeXZ6YmlrcHhmd2RzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU1Mjk2NTQsImV4cCI6MjA3MTEwNTY1NH0.FwCWmTV4BkQ8ZbWoKSHuNXdStddCUY_o2RtcrGj8urw"

# Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask app (Render expects this to bind on $PORT)
web_app = Flask(__name__)

# ==========================
# 🔹 Telegram Bot Handlers
# ==========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "unknown"
    first_name = update.effective_user.first_name or "Investor"

    existing = supabase.table("users").select("chat_id").eq("chat_id", chat_id).execute()
    if not existing.data:
        supabase.table("users").insert({
            "chat_id": chat_id,
            "username": username,
            "watchlist": []
        }).execute()

    await update.message.reply_text(f"Hi {first_name}! You’re now subscribed to SudarStockBot.")

def start_telegram_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

# ==========================
# 🔹 Background Worker
# ==========================
def send_direct_message(chat_id, message):
    bot = Bot(token=BOT_TOKEN)
    bot.send_message(chat_id=chat_id, text=message)

def background_worker():
    while True:
        try:
            users = supabase.table("users").select("chat_id").execute().data
            for u in users:
                chat_id = u["chat_id"]
                send_direct_message(chat_id, f"⏰ Reminder at {datetime.datetime.now().strftime('%H:%M:%S')}")
            
            time.sleep(3600)  # run every 1 hr
        except Exception as e:
            print("Background worker error:", e)
            time.sleep(60)  # retry in 1 min

# ==========================
# 🔹 Flask Routes
# ==========================
@web_app.route("/")
def home():
    return "✅ SudarStockBot is running!"

@web_app.route("/status")
def status():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "running", "time": now}

# ==========================
# 🔹 Main Entrypoint
# ==========================
if __name__ == "__main__":
    import time
    
    # Start Telegram bot in a separate thread
    threading.Thread(target=start_telegram_bot, daemon=True).start()

    # Start background worker in another thread
    threading.Thread(target=background_worker, daemon=True).start()

    # Run Flask (main service)
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)
