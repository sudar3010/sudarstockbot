from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client
from flask import Flask
import datetime
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

# ✅ Helper: Send direct message
def send_direct_message(chat_id, message):
    bot = Bot(token=BOT_TOKEN)
    bot.send_message(chat_id=chat_id, text=message)

# ✅ Helper: Save user to Supabase
def save_user(chat_id, username):
    existing = supabase.table("users").select("chat_id").eq("chat_id", chat_id).execute()
    if not existing.data:
        supabase.table("users").insert({
            "chat_id": chat_id,
            "username": username,
            "watchlist": []
        }).execute()

# ✅ Helper: Add stock to watchlist
def add_to_watchlist(chat_id, symbol):
    user = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
    if user.data:
        raw_watchlist = user.data["watchlist"]
        if isinstance(raw_watchlist, str):
            cleaned = raw_watchlist.strip("{}[]").split(",")
            current = [s.strip().strip('"') for s in cleaned if s.strip() and s.strip() != '[]']
        elif isinstance(raw_watchlist, list):
            current = [s for s in raw_watchlist if s != '[]']
        else:
            current = []

        if symbol not in current:
            current.append(symbol)
            supabase.table("users").update({"watchlist": current}).eq("chat_id", chat_id).execute()

        return current
    return []

# ✅ Helper: Remove stock from watchlist
def remove_from_watchlist(chat_id, symbol):
    user = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
    if user.data:
        raw_watchlist = user.data["watchlist"]
        if isinstance(raw_watchlist, str):
            cleaned = raw_watchlist.strip("{}[]").split(",")
            current = [s.strip().strip('"') for s in cleaned if s.strip() and s.strip() != '[]']
        elif isinstance(raw_watchlist, list):
            current = [s for s in raw_watchlist if s != '[]']
        else:
            current = []

        if symbol in current:
            current.remove(symbol)
            supabase.table("users").update({"watchlist": current}).eq("chat_id", chat_id).execute()
            return current, True
        else:
            return current, False
    return [], False

# ✅ Helper: Get watchlist
def get_watchlist(chat_id):
    user = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
    if user.data:
        return user.data["watchlist"] or []
    return []

# ✅ Telegram command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "unknown"
    first_name = update.effective_user.first_name or "Investor"
    save_user(chat_id, username)
    await update.message.reply_text(
        f"Hi {first_name}! You’re now subscribed to SudarStockBot.\n"
        f"Type /add INFY to track a stock or /summary to view your watchlist."
    )
    send_direct_message(chat_id, "📈 You’ll start receiving personalized stock updates soon.")

# ✅ Telegram command: /add
async def add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("❗ Please provide a stock symbol. Example: /add INFY")
        return
    symbol = " ".join(args).upper().strip()
    if not re.match(r"^[A-Z\s]{3,15}$", symbol):
        await update.message.reply_text("❗ Invalid symbol format. Use something like INFY or HDFC BANK.")
        return
    watchlist = add_to_watchlist(chat_id, symbol)
    if symbol in watchlist:
        await update.message.reply_text(f"✅ {symbol} added to your watchlist.")
    else:
        await update.message.reply_text(f"ℹ️ {symbol} is already in your watchlist.")
    await update.message.reply_text(f"📌 Your current watchlist: {', '.join(watchlist)}")

# ✅ Telegram command: /remove
async def remove_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("❗ Please provide a stock symbol to remove. Example: /remove INFY")
        return
    symbol = args[0].upper()
    watchlist, removed = remove_from_watchlist(chat_id, symbol)
    if removed:
        await update.message.reply_text(f"🗑️ {symbol} removed from your watchlist.")
    else:
        await update.message.reply_text(f"⚠️ {symbol} was not found in your watchlist.")
    if watchlist:
        await update.message.reply_text(f"📌 Updated watchlist: {', '.join(watchlist)}")
    else:
        await update.message.reply_text("📭 Your watchlist is now empty.")

# ✅ Telegram command: /summary
async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    raw_watchlist = get_watchlist(chat_id)
    if not raw_watchlist:
        await update.message.reply_text("📭 Your watchlist is empty. Add stocks using /add SYMBOL.")
        return
    try:
        watchlist = json.loads(raw_watchlist) if isinstance(raw_watchlist, str) else raw_watchlist
    except json.JSONDecodeError:
        await update.message.reply_text("⚠️ Couldn't parse your watchlist. Please try again.")
        return
    cleaned_watchlist = [s.strip().replace('\n', ' ') for s in watchlist if isinstance(s, str) and s.strip()]
    if not cleaned_watchlist:
        await update.message.reply_text("📭 Your watchlist is empty. Add stocks using /add SYMBOL.")
        return
    summary = "📊 Your current watchlist:\n" + "\n".join(f"• {s}" for s in cleaned_watchlist)
    await update.message.reply_text(summary)

# ✅ Flask app for Render health check
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "✅ SudarStockBot is running!"

@web_app.route('/status')
def status():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "status": "✅ SudarStockBot is running",
        "timestamp": now,
        "message": "Bot is alive and ready to serve!"
    }

if __name__ == '__main__':
    # Start Telegram bot (polling)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_stock))
    app.add_handler(CommandHandler("summary", show_summary))
    app.add_handler(CommandHandler("remove", remove_stock))

    # Run bot in a separate async task
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(app.run_polling())

    # Run Flask app (Render will keep this alive)
    web_app.run(host='0.0.0.0', port=8080)
