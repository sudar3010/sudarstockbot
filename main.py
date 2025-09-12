# app.py
import os
import re
import json
import time
import datetime
import threading
from flask import Flask
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client

# -------------------------
# Load secrets from env
# -------------------------
# Supabase credentials
SUPABASE_URL = "https://xdkcliccyvzbikpxfwds.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhka2NsaWNjeXZ6YmlrcHhmd2RzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU1Mjk2NTQsImV4cCI6MjA3MTEwNTY1NH0.FwCWmTV4BkQ8ZbWoKSHuNXdStddCUY_o2RtcrGj8urw"

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Please set BOT_TOKEN, SUPABASE_URL and SUPABASE_KEY environment variables")

# -------------------------
# Supabase client
# -------------------------
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Flask app (Render requires a web port)
# -------------------------
web_app = Flask(__name__)

# -------------------------
# Helpers (Supabase + Telegram)
# -------------------------
def send_direct_message(chat_id, message):
    try:
        bot = Bot(token=BOT_TOKEN)
        bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"[send_direct_message] Error sending to {chat_id}: {e}")

def save_user(chat_id, username):
    try:
        existing = supabase.table("users").select("chat_id").eq("chat_id", chat_id).execute()
        if not existing.data:
            supabase.table("users").insert({
                "chat_id": chat_id,
                "username": username,
                "watchlist": []
            }).execute()
    except Exception as e:
        print(f"[save_user] supabase error: {e}")

def add_to_watchlist(chat_id, symbol):
    try:
        resp = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
        if resp.data:
            raw_watchlist = resp.data.get("watchlist", [])
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
    except Exception as e:
        print(f"[add_to_watchlist] supabase error: {e}")
    return []

def remove_from_watchlist(chat_id, symbol):
    try:
        resp = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
        if resp.data:
            raw_watchlist = resp.data.get("watchlist", [])
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
    except Exception as e:
        print(f"[remove_from_watchlist] supabase error: {e}")
    return [], False

def get_watchlist(chat_id):
    try:
        resp = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
        if resp.data:
            return resp.data.get("watchlist") or []
    except Exception as e:
        print(f"[get_watchlist] supabase error: {e}")
    return []

# -------------------------
# Telegram handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "unknown"
    first_name = update.effective_user.first_name or "Investor"
    save_user(chat_id, username)
    await update.message.reply_text(
        f"Hi {first_name}! You’re now subscribed to SudarStockBot.\n"
        "Type /add INFY to track a stock or /summary to view your watchlist."
    )
    send_direct_message(chat_id, "📈 You’ll start receiving personalized stock updates soon.")

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

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    raw_watchlist = get_watchlist(chat_id)
    if not raw_watchlist:
        await update.message.reply_text("📭 Your watchlist is empty. Add stocks using /add SYMBOL.")
        return
    try:
        watchlist = json.loads(raw_watchlist) if isinstance(raw_watchlist, str) else raw_watchlist
    except Exception:
        await update.message.reply_text("⚠️ Couldn't parse your watchlist. Please try again.")
        return
    cleaned_watchlist = [s.strip().replace('\n', ' ') for s in watchlist if isinstance(s, str) and s.strip()]
    if not cleaned_watchlist:
        await update.message.reply_text("📭 Your watchlist is empty. Add stocks using /add SYMBOL.")
        return
    summary = "📊 Your current watchlist:\n" + "\n".join(f"• {s}" for s in cleaned_watchlist)
    await update.message.reply_text(summary)

# -------------------------
# Background worker: sends periodic summary to users
# -------------------------
def background_worker(reminder_interval_seconds=3600):
    """
    Periodically sends each user a compact watchlist reminder.
    Default interval: 3600 seconds (1 hour). Change if needed.
    """
    print("[background_worker] started")
    while True:
        try:
            resp = supabase.table("users").select("chat_id, watchlist").execute()
            users = resp.data or []
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for u in users:
                try:
                    chat_id = u.get("chat_id")
                    watchlist_raw = u.get("watchlist") or []
                    # normalize watchlist into list of strings
                    if isinstance(watchlist_raw, str):
                        try:
                            watchlist = json.loads(watchlist_raw)
                        except Exception:
                            cleaned = watchlist_raw.strip("{}[]").split(",")
                            watchlist = [s.strip().strip('"') for s in cleaned if s.strip() and s.strip() != '[]']
                    elif isinstance(watchlist_raw, list):
                        watchlist = [s for s in watchlist_raw if s and s != '[]']
                    else:
                        watchlist = []

                    if not watchlist:
                        # skip users with empty watchlist
                        continue

                    # build a compact reminder message
                    reminder = f"⏰ Watchlist reminder — {now_str}\n" + "\n".join(f"• {s}" for s in watchlist)
                    reminder += "\n\nUse /summary in bot for full details."
                    send_direct_message(chat_id, reminder)
                except Exception as e:
                    print(f"[background_worker] send error for user {u}: {e}")

            # sleep until next run
            time.sleep(reminder_interval_seconds)

        except Exception as e:
            print(f"[background_worker] supabase read error: {e}")
            time.sleep(60)  # short pause on error

# -------------------------
# Flask health endpoints
# -------------------------
@web_app.route('/')
def home():
    return "✅ SudarStockBot is running!"

@web_app.route('/status')
def status():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "✅ SudarStockBot is running", "timestamp": now, "message": "Bot is alive and ready to serve!"}

# -------------------------
# Start bot & worker & Flask
# -------------------------
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_stock))
    app.add_handler(CommandHandler("remove", remove_stock))
    app.add_handler(CommandHandler("summary", show_summary))
    print("[run_bot] starting polling...")
    app.run_polling()  # blocks until stopped

if __name__ == "__main__":
    # start Telegram bot thread
    t_bot = threading.Thread(target=run_bot, daemon=True)
    t_bot.start()

    # start background worker thread (default 1 hour interval)
    t_worker = threading.Thread(target=background_worker, args=(3600,), daemon=True)
    t_worker.start()

    # run Flask (Render requires binding to $PORT)
    port = int(os.environ.get("PORT", 8080))
    print(f"[main] running Flask on port {port}")
    web_app.run(host="0.0.0.0", port=port)
