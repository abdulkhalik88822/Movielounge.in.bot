from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from tmdbv3api import TMDb, Movie, TV
from flask import Flask
from threading import Thread
from pymongo import MongoClient
import logging
import requests
import time
import socket
import sys
import threading
import os

# Logging configuration
logging.basicConfig(level=logging.INFO)

# MongoDB Setup
mongo = MongoClient("mongodb+srv://kailash:pass@cluster0.sqtztxm.mongodb.net/?retryWrites=true&w=majority")
db = mongo["movie_bot"]
searches = db["searches"]

# Admin Telegram ID
ADMIN_ID = 6133440326  # Replace with your Telegram user ID

# Bot Configuration
BOT_TOKEN = "7851649379:AAEYbY9Hf_28LNfcbJ4cMSx8ivGYh-BxQ5Y"  # Replace with your bot token
API_ID = 24503270  # Replace with your API ID
API_HASH = "53b04d58c085c3136ceda8036ee9a1da"  # Replace with your API hash
BOT_NAME = "Movielunge.in"  # Replace with your bot's name

# Laravel API Configuration
LARAVEL_API_TOKEN = "002_TM_854_FYTDCS"  # Replace with your Laravel API token
LARAVEL_API_URL = "https://api.cinema4u.xyz/api"
search_results = {}

# Pyrogram Client
app = Client(
    "movie_bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# Flask server for health check
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return 'OK BOT IS WORKING MODE', 200

# TMDB setup
tmdb = TMDb()
tmdb.api_key = "c64a889556107e0f7e0d2c00966fffa1"
tmdb.language = "en"
movie = Movie()
tv = TV()

site_connected = False
timeout_duration = 20  # seconds
max_retries = 3
retry_delay = 5  # seconds

def show_timer():
    for i in range(timeout_duration):
        if site_connected:
            break
        sys.stdout.write(f"\r⏳ [Admin ID: {ADMIN_ID}] Waiting for site response... {i + 1}/{timeout_duration} sec")
        sys.stdout.flush()
        time.sleep(1)
    if not site_connected:
        sys.stdout.write("\n")

def check_site_connection():
    global site_connected

    bot_name = socket.gethostname()
    headers = {
        "X-API-TOKEN": LARAVEL_API_TOKEN,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    for attempt in range(1, max_retries + 1):
        site_connected = False
        print(f"\n🔄 [Admin ID: {ADMIN_ID}] Attempt {attempt} to connect to Laravel site...")

        timer_thread = threading.Thread(target=show_timer)
        timer_thread.start()

        try:
            response = requests.post(
                LARAVEL_API_URL,
                json={"bot_name": bot_name, "status": "online"},
                headers=headers,
                timeout=timeout_duration
            )

            site_connected = True
            timer_thread.join()

            if response.status_code == 200:
                print(f"\n✅ [Admin ID: {ADMIN_ID}] Successfully connected to Laravel site.")
                return
            else:
                try:
                    error_detail = response.json()
                except ValueError:
                    error_detail = response.text
                print(f"\n❌ [Admin ID: {ADMIN_ID}] Status: {response.status_code}, Response: {error_detail}")

        except requests.exceptions.RequestException as e:
            site_connected = False
            timer_thread.join()
            print(f"\n❌ [Admin ID: {ADMIN_ID}] Error: {str(e)}")

        if attempt < max_retries:
            wait_time = retry_delay * attempt
            print(f"🔁 [Admin ID: {ADMIN_ID}] Retrying in {wait_time} seconds...\n")
            time.sleep(wait_time)
        else:
            print(f"🚨 [Admin ID: {ADMIN_ID}] All retry attempts failed. Bypassing this connection attempt.")
            return

# Start command handler
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("Hello! Send me a movie or TV show name and I’ll find it for you.")

# Admin-only /api command
@app.on_message(filters.command("api"))
async def api_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if user_id != ADMIN_ID:
        await message.reply("🚫 You are not authorized to use this command.")
        await client.send_message(
            ADMIN_ID,
            f"⚠️ Unauthorized attempt to use /api command by {user_name} (ID: {user_id})."
        )
        return

    check_site_connection()
    status = "✅ Connected" if site_connected else "❌ Not Connected"
    await message.reply(f"🔍 Site connection status: {status}")

# Search handler
@app.on_message(filters.text & ~filters.command(["start", "api"]))
async def search_movie_or_tv(client, message: Message):
    if not site_connected:
        await message.reply("🚫 The bot is currently not connected to the site. Please try again later.")
        return

    query = message.text.strip()
    user = message.from_user
    user_id = user.id
    username = user.username or user.first_name

    await client.send_message(ADMIN_ID, f"🧐 User `{username}` searched for: `{query}`")

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        requests.post(
            "https://api.cinema4u.xyz/api/log-search",
            json={"user_id": user_id, "username": username, "query": query},
            headers=headers,
            timeout=10
        )
    except Exception as e:
        logging.warning(f"Failed to send search query to Laravel site: {e}")

    loading_msg = await message.reply("**AI is finding your result...**")

    try:
        movie_results = movie.search(query)
        tv_results = tv.search(query)
        results = movie_results + tv_results
    except Exception as e:
        logging.error(f"TMDb search failed: {e}")
        return await loading_msg.edit("⚠️ Error while searching. Please try again later.")

    if not results:
        return await loading_msg.edit("😕 No matching results found.")

    result_ids = [r.id for r in results]
    result_types = ["movie" if r in movie_results else "tv" for r in results]

    search_results[user_id] = {
        "results": result_ids,
        "types": result_types,
        "current_index": 0
    }

    await send_result(client, message.chat.id, user_id, 0, loading_msg)

# Send result
async def send_result(client, chat_id, user_id, index, loading_msg):
    data = search_results.get(user_id)
    if not data:
        await client.send_message(chat_id, "No search data found.")
        return

    result_ids = data.get("results", [])
    result_types = data.get("types", [])
    if index < 0 or index >= len(result_ids):
        await client.send_message(chat_id, "No more results.")
        return

    buttons = []
    for i in range(5):
        if index + i >= len(result_ids):
            break

        res_id = result_ids[index + i]
        res_type = result_types[index + i]
        full_details = movie.details(res_id) if res_type == "movie" else tv.details(res_id)
        title = full_details.title if res_type == "movie" else full_details.name
        release_date = full_details.release_date if res_type == "movie" else full_details.first_air_date
        year = release_date[:4] if release_date else "N/A"

        button_text = f"{title} ({year})"
        button_url = f"https://movielounge.in/best/result/x/{res_id}/{res_type.lower()}"
        buttons.append([InlineKeyboardButton(button_text, url=button_url)])

    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="prev"))
    if index + 5 < len(result_ids):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="next"))
    if nav_buttons:
        buttons.append(nav_buttons)

    res_id = result_ids[index]
    res_type = result_types[index]
    full_details = movie.details(res_id) if res_type == "movie" else tv.details(res_id)
    title = full_details.title if res_type == "movie" else full_details.name
    release_date = full_details.release_date if res_type == "movie" else full_details.first_air_date
    year = release_date[:4] if release_date else "N/A"
    genres = ", ".join([g.name for g in full_details.genres]) if full_details.genres else "Unknown"
    poster_url = f"https://image.tmdb.org/t/p/w500{full_details.poster_path}" if full_details.poster_path else None

    caption = f"**{title}** ({year})\n\n**Genres:** {genres}"

    if poster_url:
        await client.send_photo(chat_id=chat_id, photo=poster_url, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(chat_id=chat_id, text=caption, reply_markup=InlineKeyboardMarkup(buttons))

    await loading_msg.delete()

# Pagination
@app.on_callback_query()
async def handle_pagination(client, callback_query):
    user_id = callback_query.from_user.id
    data = search_results.get(user_id)
    if not data:
        await callback_query.answer("No search data found.", show_alert=True)
        return

    current_index = data.get("current_index", 0)
    if callback_query.data == "next":
        current_index += 5
    elif callback_query.data == "prev":
        current_index -= 5
    else:
        await callback_query.answer("Invalid action.", show_alert=True)
        return

    search_results[user_id]["current_index"] = current_index
    await callback_query.message.delete()
    await send_result(client, callback_query.message.chat.id, user_id, current_index, callback_query.message)

# Flask server runner
def run_flask():
    port = int(os.environ.get("PORT", 5000))  # <-- fixed here
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

# Start Flask and Bot
if __name__ == "__main__":
    try:
        check_site_connection()
        Thread(target=run_flask).start()
        app.run()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
