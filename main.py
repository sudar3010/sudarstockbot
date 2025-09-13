# app.py
import os
import re
import json
import time
import datetime
import threading
import asyncio
import ast
from flask import Flask
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client

# -------------------------
# Load secrets from env
# -------------------------
# Telegram Bot Token
BOT_TOKEN = "8108841318:AAE8aoEPqOU6SrwzRvtAjOQAG9AjD2IT2NI"

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
# Flask app
# -------------------------
web_app = Flask(__name__)

# -------------------------
# Helpers
# -------------------------
async def async_send_direct_message(chat_id, message):
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"[async_send_direct_message] Error sending to {chat_id}: {e}")

def send_direct_message(chat_id, message):
    """Safe wrapper for use in sync functions"""
    asyncio.run(async_send_direct_message(chat_id, message))

def normalize_watchlist(wl):
    """
    Ensure watchlist is always returned as a clean list of strings.
    Handles cases where Supabase returns:
      - a real list: ['TCS']
      - a json string: '["TCS"]'
      - a weird multiline string: '["\nT\nC\nS\n"]'
      - a plain string: "TCS"
    """
    if wl is None:
        return []

    # already a list
    if isinstance(wl, list):
        cleaned = []
        for item in wl:
            if item is None:
                continue
            s = str(item)
            s = s.replace("\n", "").strip().strip('"').strip()
            if s:
                cleaned.append(s)
        return cleaned

    # if it's a bytes object
    if isinstance(wl, (bytes, bytearray)):
        try:
            wl = wl.decode()
        except Exception:
            wl = str(wl)

    # wl is a string (most common problem)
    if isinstance(wl, str):
        text = wl.strip()
        # Try json.loads first
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(x).replace("\n", "").strip().strip('"').strip() for x in parsed if x is not None]
            # if parsed is string inside quotes etc.
            if isinstance(parsed, str):
                s = parsed.replace("\n", "").strip().strip('"').strip()
                return [s] if s else []
        except Exception:
            pass

        # Try python literal eval (handles "['TCS']" or weird quotes)
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(x).replace("\n", "").strip().strip('"').strip() for x in parsed if x is not None]
            if isinstance(parsed, str):
                s = parsed.replace("\n", "").strip().strip('"').strip()
                return [s] if s else []
        except Exception:
            pass

        # Fallback: remove newlines and surrounding brackets/quotes, then split by comma
        cleaned = text.replace("\n", " ").strip()
        # remove surrounding [] if present
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1]
        # split
        parts = [p.strip().strip('"').strip("'") for p in cleaned.split(",") if p.strip()]
        if parts:
            return parts

        # final fallback: single value
        single = text.replace("\n", "").strip().strip('"').strip("'")
        return [single] if single else []

    # any other type -> convert to string
    return [str(wl).replace("\n", "").strip()]

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
            wl_raw = resp.data.get("watchlist", [])
            wl = normalize_watchlist(wl_raw)
            if symbol not in wl:
                wl.append(symbol)
                # update with clean list
                supabase.table("users").update({"watchlist": wl}).eq("chat_id", chat_id).execute()
            return wl
        else:
            # user row missing — create it with this symbol
            supabase.table("users").insert({
                "chat_id": chat_id,
                "username": None,
                "watchlist": [symbol]
            }).execute()
            return [symbol]
    except Exception as e:
        print(f"[add_to_watchlist] supabase error: {e}")
    return []

def remove_from_watchlist(chat_id, symbol):
    try:
        resp = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
        if resp.data:
            wl_raw = resp.data.get("watchlist", [])
            wl = normalize_watchlist(wl_raw)
            if symbol in wl:
                wl.remove(symbol)
                supabase.table("users").update({"watchlist": wl}).eq("chat_id", chat_id).execute()
                return wl, True
            return wl, False
    except Exception as e:
        print(f"[remove_from_watchlist] supabase error: {e}")
    return [], False

def get_watchlist(chat_id):
    try:
        resp = supabase.table("users").select("watchlist").eq("chat_id", chat_id).single().execute()
        if resp.data:
            return normalize_watchlist(resp.data.get("watchlist") or [])
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
        f"Hi {first_name}! You’re now subscribed.\n"
        "Type /add INFY to track a stock or /summary to view your watchlist."
    )
    await async_send_direct_message(chat_id, "📈 You’ll start receiving updates soon.")

async def add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("❗ Usage: /add SYMBOL (e.g., /add INFY)")
        return
    symbol = " ".join(args).upper().strip()
    watchlist = add_to_watchlist(chat_id, symbol)
    await update.message.reply_text(f"✅ {symbol} added.\n📌 Watchlist: {', '.join(watchlist)}")

async def remove_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("❗ Usage: /remove SYMBOL")
        return
    symbol = args[0].upper()
    wl, removed = remove_from_watchlist(chat_id, symbol)
    msg = f"🗑️ {symbol} removed." if removed else f"⚠️ {symbol} not found."
    await update.message.reply_text(msg + f"\n📌 Watchlist: {', '.join(wl)}")

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    wl = get_watchlist(chat_id)
    # normalize here as extra safety (get_watchlist already normalizes)
    wl = normalize_watchlist(wl)

    if not wl:
        await update.message.reply_text("📭 Your watchlist is empty.")
    else:
        summary = "📊 Watchlist:\n" + "\n".join(f"• {s}" for s in wl)
        await update.message.reply_text(summary)

# -------------------------
# Background worker
# -------------------------
def background_worker():
    print("[background_worker] started")
    while True:
        try:
           # resp = supabase.table("users").select("chat_id, watchlist").execute()
           # for u in (resp.data or []):
           #     chat_id = u.get("chat_id")
            #    wl = u.get("watchlist") or []
            #    if wl:
            #        now = datetime.datetime.now().strftime("%H:%M:%S")
             #       msg = f"⏰ Reminder {now}\n" + "\n".join(f"• {s}" for s in wl)
              #      send_direct_message(chat_id, msg)
            time.sleep(3600)  # hourly
        except Exception as e:
            print(f"[background_worker] error: {e}")
            time.sleep(60)

# -------------------------
# Flask routes
# -------------------------
@web_app.route('/')
def home():
    return "✅ Bot is running!"
@web_app.route('/status')
def status():
    return {"status": "ok", "message": "Bot and background worker are running ✅"}

# -------------------------
# Main entry
# -------------------------
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Start background worker
    threading.Thread(target=background_worker, daemon=True).start()
    # Start Flask
    threading.Thread(target=run_flask, daemon=True).start()

    # Run Telegram bot (must be in main thread)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_stock))
    app.add_handler(CommandHandler("remove", remove_stock))
    app.add_handler(CommandHandler("summary", show_summary))
    print("[main] starting Telegram bot...")
    app.run_polling()
