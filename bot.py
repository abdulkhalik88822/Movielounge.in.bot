from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from tmdbv3api import TMDb, Movie, TV
from tmdbv3api.exceptions import TMDbException
from pymongo import MongoClient
import logging
import requests
import time
import socket
import sys
import threading
import os
import re
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(level=logging.INFO)

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI")  # Store in .env file
mongo = MongoClient(MONGO_URI)
db = mongo["movie_bot"]
searches = db["searches"]

# Admin Telegram ID
ADMIN_ID = 6133440326  # Replace with your Telegram user ID

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Store in .env file
API_ID = int(os.getenv("API_ID"))  # Store in .env file
API_HASH = os.getenv("API_HASH")  # Store in .env file
BOT_NAME = "Movielunge.in"  # Replace with your bot's name

# Laravel API Configuration
LARAVEL_API_TOKEN = os.getenv("LARAVEL_API_TOKEN")  # Store in .env file
LARAVEL_API_URL = "https://api.cinema4u.xyz/api"
search_results = {}

# Pyrogram Client
app = Client(
    "movie_bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# TMDB setup
tmdb = TMDb()
tmdb.api_key = os.getenv("TMDB_API_KEY")  # Store in .env file
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

# Start command handler with custom message, image, and buttons
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user_name = message.from_user.first_name  # Get user's first name
    # Custom message with user's name
    welcome_message = (
        f"👋 Hᴇʟʟᴏ, {user_name}!\n\n"
        f"🎥 I'ᴍ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ Mᴏᴠɪᴇ & TV Sʜᴏᴡ ᴀssɪsᴛᴀɴᴛ. "
        f"Jᴜsᴛ ᴛʏᴘᴇ ᴛʜᴇ ɴᴀᴍᴇ ᴏғ ᴀɴʏ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs, "
        f"ᴀɴᴅ I’ʟʟ ғᴇᴛᴄʜ ᴅᴇᴛᴀɪʟs ɪɴsᴛᴀɴᴛʟʏ.\n\n"
        f"🚀 Lᴇᴛ's ɢᴇᴛ sᴛᴀʀᴛᴇᴅ!"
    )
    
    # Placeholder image URL (replace with your own image URL)
    image_url = "https://telegra.ph/file/5d32303d074c709406576.jpg"  # Replace this with your actual image URL
    
    # Inline buttons
    buttons = [
        [
            InlineKeyboardButton("Add me in group", url=f"https://t.me/{BOT_NAME}?startgroup=true"),
            InlineKeyboardButton("API Status", callback_data="api_status"),
        ],
        [
            InlineKeyboardButton("DB Status", callback_data="db_status"),
            InlineKeyboardButton("Developer Support", url="https://t.me/Attitude2688"),  # Replace with your support link
        ]
    ]
    
    # Send the welcome message with image and buttons
    await client.send_photo(
        chat_id=message.chat.id,
        photo=image_url,
        caption=welcome_message,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Callback query handler for buttons
@app.on_callback_query()
async def handle_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    # Handle API Status button
    if data == "api_status":
        if user_id != ADMIN_ID:
            await callback_query.answer("🚫 You are not authorized to check API status.", show_alert=True)
            return
        check_site_connection()
        status = "✅ Connected" if site_connected else "❌ Not Connected"
        await callback_query.message.reply(f"🔍 API connection status: {status}")
        return

    # Handle DB Status button
    if data == "db_status":
        if user_id != ADMIN_ID:
            await callback_query.answer("🚫 You are not authorized to check DB status.", show_alert=True)
            return
        try:
            # Check MongoDB connection
            mongo.server_info()
            await callback_query.message.reply("✅ Database is connected.")
        except Exception as e:
            await callback_query.message.reply(f"❌ Database error: {str(e)}")
        return

    # Handle pagination (existing functionality)
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

# Admin-only /api command (existing functionality)
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

# Search handler with year handling
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

    # Step 1: Extract movie title and year from the query using regex
    year_match = re.search(r'\b(\d{4})\b', query)  # Look for a 4-digit year
    search_year = year_match.group(1) if year_match else None
    # Remove the year from the query to search only the title
    search_query = re.sub(r'\b\d{4}\b', '', query).strip().lower()

    if not search_query:
        await loading_msg.edit("⚠️ Please provide a valid movie or TV show name.")
        return

    # Step 2: Search TMDB using the cleaned query (title only) with better error handling
    try:
        movie_results = movie.search(search_query)
        tv_results = tv.search(search_query)
        results = movie_results + tv_results
    except TMDbException as e:
        logging.error(f"TMDb API error: {e}")
        await loading_msg.edit(f"⚠️ TMDB API error: {e}. Please try again later.")
        return
    except Exception as e:
        logging.error(f"TMDb search failed for query '{search_query}': {e}")
        await loading_msg.edit("⚠️ Error while searching. Please try again later.")
        return

    if not results:
        await loading_msg.edit("😕 No matching results found.")
        return

    # Step 3: Filter results based on the year (if provided)
    filtered_results = []
    result_types = []
    if search_year:
        for result in results:
            release_date = getattr(result, 'release_date', None) or getattr(result, 'first_air_date', None)
            if release_date:
                result_year = release_date[:4]
                if result_year == search_year:
                    filtered_results.append(result)
                    result_types.append("movie" if result in movie_results else "tv")
    else:
        # If no year is provided, use all results
        filtered_results = results
        result_types = ["movie" if r in movie_results else "tv" for r in results]

    # Step 4: If no exact year match but results exist, show closest matches with a message
    if not filtered_results and results and search_year:
        await loading_msg.edit(
            f"⚠️ No results found for '{search_query}' in {search_year}. Showing closest matches instead:"
        )
        filtered_results = results
        result_types = ["movie" if r in movie_results else "tv" for r in results]

    if not filtered_results:
        await loading_msg.edit("😕 No matching results found.")
        return

    result_ids = [r.id for r in filtered_results]
    search_results[user_id] = {
        "results": result_ids,
        "types": result_types,
        "current_index": 0,
        "timestamp": time.time()  # Add timestamp for cleanup
    }

    await send_result(client, message.chat.id, user_id, 0, loading_msg)

# Send result with better error handling for TMDB details
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
        try:
            full_details = movie.details(res_id) if res_type == "movie" else tv.details(res_id)
            title = full_details.title if res_type == "movie" else full_details.name
            release_date = full_details.release_date if res_type == "movie" else full_details.first_air_date
            year = release_date[:4] if release_date else "N/A"
        except TMDbException as e:
            logging.error(f"TMDb API error while fetching details for ID {res_id}: {e}")
            await client.send_message(chat_id, f"⚠️ TMDB API error: {e}. Skipping this result.")
            continue
        except Exception as e:
            logging.error(f"Error fetching details for ID {res_id}: {e}")
            await client.send_message(chat_id, "⚠️ Error fetching details. Skipping this result.")
            continue

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
    try:
        full_details = movie.details(res_id) if res_type == "movie" else tv.details(res_id)
        title = full_details.title if res_type == "movie" else full_details.name
        release_date = full_details.release_date if res_type == "movie" else full_details.first_air_date
        year = release_date[:4] if release_date else "N/A"
        genres = ", ".join([g.name for g in full_details.genres]) if full_details.genres else "Unknown"
        poster_url = f"https://image.tmdb.org/t/p/w500{full_details.poster_path}" if full_details.poster_path else None
    except TMDbException as e:
        logging.error(f"TMDb API error while fetching details for ID {res_id}: {e}")
        await loading_msg.edit(f"⚠️ TMDB API error: {e}. Cannot display this result.")
        return
    except Exception as e:
        logging.error(f"Error fetching details for ID {res_id}: {e}")
        await loading_msg.edit("⚠️ Error fetching details. Cannot display this result.")
        return

    caption = f"**{title}** ({year})\n\n**Genres:** {genres}"

    if poster_url:
        await client.send_photo(chat_id=chat_id, photo=poster_url, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(chat_id=chat_id, text=caption, reply_markup=InlineKeyboardMarkup(buttons))

    await loading_msg.delete()

# Cleanup old search results (run within Pyrogram's event loop)
async def cleanup_search_results():
    while True:
        await asyncio.sleep(3600)  # Run hourly
        current_time = time.time()
        for user_id in list(search_results.keys()):
            if current_time - search_results[user_id].get("timestamp", 0) > 3600:
                del search_results[user_id]

# Start Bot and Cleanup Task
if __name__ == "__main__":
    try:
        check_site_connection()
        # Start the bot
        app.start()
        # Run cleanup_search_results within Pyrogram's event loop
        app.loop.create_task(cleanup_search_results())
        # Keep the bot running
        idle()
        # Stop the bot gracefully
        app.stop()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
