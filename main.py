import asyncio
import datetime
import threading
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client
from flask import Flask
import os
import re
import json

# Telegram Bot Token
BOT_TOKEN = "8108841318:AAE8aoEPqOU6SrwzRvtAjOQAG9AjD2IT2NI"

# Supabase credentials
SUPABASE_URL = "https://xdkcliccyvzbikpxfwds.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhka2NsaWNjeXZ6YmlrcHhmd2RzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU1Mjk2NTQsImV4cCI6MjA3MTEwNTY1NH0.FwCWmTV4BkQ8ZbWoKSHuNXdStddCUY_o2RtcrGj8urw"

# ✅ Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ✅ Flask app for health check
web_app = Flask(__name__)

# ✅ Helper: Send direct message
def send_direct_message(chat_id, message):
    bot = Bot(token=BOT_TOKEN)
    bot.send_message(chat_id=chat_id, text=message)

# ✅ Background worker task
def background_worker():
    while True:
        try:
            # Fetch all users
            users = supabase.table("users").select("chat_id").execute().data
            for u in users:
                chat_id = u["chat_id"]
                # Example: send a daily stock reminder
                send_direct_message(chat_id, f"⏰ Reminder at {datetime.datetime.now().strftime('%H:%M:%S')}")
            
            # Sleep before next run (e.g. every 1 hour)
            asyncio.run(asyncio.sleep(3600))

        except Exception as e:
            print("Background worker error:", e)
            asyncio.run(asyncio.sleep(60))  # wait before retry

# ✅ Telegram command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "unknown"
    first_name = update.effective_user.first_name or "Investor"
    # Save user
    existing = supabase.table("users").select("chat_id").eq("chat_id", chat_id).execute()
    if not existing.data:
        supabase.table("users").insert({
            "chat_id": chat_id,
            "username": username,
            "watchlist": []
        }).execute()
    await update.message.reply_text(f"Hi {first_name}! You’re now subscribed to SudarStockBot.")

# === Flask routes ===
@web_app.route('/')
def home():
    return "✅ SudarStockBot is running!"

@web_app.route('/status')
def status():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "running", "time": now}

if __name__ == "__main__":
    # Start Telegram bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    # 🔹 Start background worker in a separate thread
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()

    # 🔹 Run both Flask + Telegram bot
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(app.run_polling())
    web_app.run(host="0.0.0.0", port=8080)
