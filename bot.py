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
MONGO_URI = os.getenv("MONGO_URI")
mongo = MongoClient(MONGO_URI)
db = mongo["movie_bot"]
searches = db["searches"]
users = db["users"]

# Add index for better performance
users.create_index("user_id", unique=True)

# Admin Telegram ID
ADMIN_ID = 6133440326

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_NAME = "DD_search_movie_bot"

# Laravel API Configuration
LARAVEL_API_TOKEN = os.getenv("LARAVEL_API_TOKEN")
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
tmdb.api_key = os.getenv("TMDB_API_KEY")
tmdb.language = "en"
movie = Movie()
tv = TV()

site_connected = False
timeout_duration = 20
max_retries = 3
retry_delay = 5

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

# Start command handler with user storage
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user = message.from_user
    if user is None:
        await message.reply("⚠️ This command is not supported for anonymous users or channels.")
        logging.warning(f"Received /start command with no user: {message.chat.id}")
        return

    user_id = user.id
    user_name = user.first_name
    username = user.username or user_name

    try:
        users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": user_name,
                    "last_seen": time.time()
                }
            },
            upsert=True
        )
    except Exception as e:
        logging.error(f"Error storing user {user_id} in MongoDB: {e}")

    welcome_message = (
        f"👋 Hᴇʟʟᴏ, {user_name}!\n\n"
        f"🎥 I'ᴍ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ Mᴏᴠɪᴇ & TV Sʜᴏᴡ ᴀssɪsᴛᴀɴᴛ. "
        f"Jᴜsᴛ ᴛʏᴘᴇ ᴛʜᴇ ɴᴀᴍᴇ ᴏғ ᴀɴʏ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs, "
        f"ᴀɴᴅ I’ʟʟ ғᴇᴛᴄʜ ᴅᴇᴛᴀɪʟs ɪɴsᴛᴀɴᴛʟʏ.\n\n"
        f"🚀 Lᴇᴛ's ɢᴇᴛ sᴛᴀʀᴛᴇᴅ!\n\n"
        f"🙌 **Cʀᴇᴅɪᴛs**:\n"
        f"👨‍💻 **Dᴇᴠᴇʟᴏᴘᴇʀ**: [Abdul khalik](https://t.me/Attitude2688)\n"
        f"👑 **Oᴡɴᴇʀ**: [Abdul Khalik](https://t.me/Attitude2688)"
    )

    image_url = "https://telegra.ph/file/5d32303d074c709406576.jpg"
    buttons = [
        [InlineKeyboardButton("Aᴅᴅ ᴍᴇ ɪɴ ɢʀᴏᴜᴘ", url=f"https://t.me/{BOT_NAME}?startgroup=true")],
        [
            InlineKeyboardButton("API Sᴛᴀᴛᴜs", callback_data="api_status"),
            InlineKeyboardButton("DB Sᴛᴀᴛᴜs", callback_data="db_status")
        ],
        [InlineKeyboardButton("Bᴏᴛ Dᴇᴠᴇʟᴏᴘᴇʀ", url="https://t.me/Attitude2688")]
    ]

    await client.send_photo(
        chat_id=message.chat.id,
        photo=image_url,
        caption=welcome_message,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Updated Broadcast command handler to handle forwarded messages
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("🚫 You are not authorized to use this command.")
        return

    # Check if the message is a reply to another message (e.g., forwarded message)
    if message.reply_to_message:
        target_message = message.reply_to_message
    else:
        target_message = message

    # Extract the broadcast message (caption or text)
    broadcast_message = None
    if target_message.caption:  # For photos with captions
        caption_parts = target_message.caption.split(maxsplit=1)
        if len(caption_parts) > 1:  # If there's text after /broadcast (in case of direct message)
            broadcast_message = caption_parts[1]
        else:
            broadcast_message = target_message.caption
    elif target_message.text:  # For text-only messages
        text_parts = target_message.text.split(maxsplit=1)
        if len(text_parts) > 1:
            broadcast_message = text_parts[1]
        else:
            broadcast_message = target_message.text

    # Check if there's a valid broadcast (either a photo or text)
    if not target_message.photo and not broadcast_message:
        await message.reply("⚠️ Usage: /broadcast <message> or send a photo with an optional caption, or reply to a message/photo to broadcast it.")
        return

    # Get all users from MongoDB
    try:
        user_list = users.find({}, {"user_id": 1})
        total_users = users.count_documents({})
    except Exception as e:
        logging.error(f"Error fetching users from MongoDB: {e}")
        await message.reply("❌ Error accessing user database.")
        return

    if total_users == 0:
        await message.reply("😕 No users found to broadcast to.")
        return

    # Initialize counters
    success_count = 0
    failed_count = 0
    loading_msg = await message.reply(f"📢 Broadcasting to {total_users} users...")

    for user in user_list:
        user_id = user["user_id"]
        try:
            if target_message.photo:
                # Broadcast photo with optional caption
                await client.send_photo(
                    chat_id=user_id,
                    photo=target_message.photo.file_id,
                    caption=broadcast_message if broadcast_message else ""
                )
            else:
                # Broadcast text message
                await client.send_message(
                    chat_id=user_id,
                    text=broadcast_message
                )
            success_count += 1
        except (pyrogram.errors.UserIsBlocked, pyrogram.errors.ChatInvalid, pyrogram.errors.UserDeactivated):
            try:
                users.delete_one({"user_id": user_id})
                logging.info(f"Removed blocked/invalid user {user_id} from database")
            except Exception as e:
                logging.error(f"Error removing user {user_id} from MongoDB: {e}")
            failed_count += 1
        except Exception as e:
            logging.warning(f"Failed to send broadcast to user {user_id}: {e}")
            failed_count += 1
        # Rate limit: 50ms delay (20 messages per second)
        await asyncio.sleep(0.05)

    # Update status
    await loading_msg.edit(
        f"📢 Broadcast completed!\n"
        f"✅ Successfully sent to: {success_count} users\n"
        f"❌ Failed to send to: {failed_count} users"
    )

    # Log the broadcast
    broadcast_type = "photo+text" if target_message.photo else "text"
    logging.info(
        f"Broadcast by Admin ID {ADMIN_ID}: "
        f"Type: {broadcast_type}, "
        f"Message: '{broadcast_message or 'Photo with no caption'}', "
        f"Total: {total_users}, Success: {success_count}, Failed: {failed_count}"
    )

# User count command handler
@app.on_message(filters.command("usercount") & filters.user(ADMIN_ID))
async def user_count(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("🚫 You are not authorized to use this command.")
        return

    try:
        total_users = users.count_documents({})
        await message.reply(f"📊 Total users in database: {total_users}")
    except Exception as e:
        logging.error(f"Error fetching user count: {e}")
        await message.reply("❌ Error accessing user database.")

# NEW: Handler to delete messages with specific words, usernames, or URLs in groups
@app.on_message(filters.group & ~filters.bot)
async def filter_group_messages(client: Client, message: Message):
    # Skip if the message has no sender (e.g., service messages)
    if message.from_user is None:
        return

    # List of bad words to filter
    bad_words = [
        "porn", "xxx", "sex", "nude", "adult", "free", "crypto", "bitcoin",
        "earning", "money", "invest", "profit", "cash", "win", "lottery"
    ]

    # Regex patterns for URLs and usernames
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    username_pattern = r'@[a-zA-Z0-9_]+'

    # Get the message text (or caption if it's a photo/video)
    text_to_check = message.text or message.caption or ""

    # Convert text to lowercase for case-insensitive matching
    text_lower = text_to_check.lower()

    # Check for bad words
    has_bad_word = any(word in text_lower for word in bad_words)

    # Check for URLs
    has_url = bool(re.search(url_pattern, text_to_check))

    # Check for usernames
    has_username = bool(re.search(username_pattern, text_to_check))

    # If any condition is met, delete the message
    if has_bad_word or has_url or has_username:
        try:
            await message.delete()
            logging.info(
                f"Deleted message in group {message.chat.id} from user {message.from_user.id}: "
                f"Reason - Bad word: {has_bad_word}, URL: {has_url}, Username: {has_username}"
            )
        except Exception as e:
            logging.error(f"Failed to delete message in group {message.chat.id}: {e}")

# Callback query handler
@app.on_callback_query()
async def handle_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "api_status":
        if user_id != ADMIN_ID:
            await callback_query.answer("🚫 You are not authorized to check API status.", show_alert=True)
            return
        check_site_connection()
        status = "✅ Connected" if site_connected else "❌ Not Connected"
        await callback_query.message.reply(f"🔍 API connection status: {status}")
        return

    if data == "db_status":
        if user_id != ADMIN_ID:
            await callback_query.answer("🚫 You are not authorized to check DB status.", show_alert=True)
            return
        try:
            mongo.server_info()
            await callback_query.message.reply("✅ Database is connected.")
        except Exception as e:
            await callback_query.message.reply(f"❌ Database error: {str(e)}")
        return

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
@app.on_message(filters.text & ~filters.command(["start", "api", "broadcast", "usercount"]))
async def search_movie_or_tv(client, message: Message):
    if not site_connected:
        await message.reply("🚫 The bot is currently not connected to the site. Please try again later.")
        return

    query = message.text.strip()
    user = message.from_user
    if user is None:
        await message.reply("⚠️ This command is not supported for anonymous users, channels, or service messages.")
        logging.warning(f"Received message with no user: {message.chat.id}")
        return

    user_id = user.id
    username = user.username or user.first_name

    try:
        users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": user.first_name,
                    "last_seen": time.time()
                }
            },
            upsert=True
        )
    except Exception as e:
        logging.error(f"Error storing user {user_id} in MongoDB: {e}")

    await client.send_message(ADMIN_ID, f"🧐 User `{username}` searched for: `{query}`")

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        requests.post(
            "https://api.hindicinema.xyz/api/log-search",
            json={"user_id": user_id, "username": username, "query": query},
            headers=headers,
            timeout=10
        )
    except Exception as e:
        logging.warning(f"Failed to send search query to Laravel site: {e}")

    loading_msg = await message.reply("**AI is finding your result...**")

    year_match = re.search(r'\b(\d{4})\b', query)
    search_year = year_match.group(1) if year_match else None
    search_query = re.sub(r'\b\d{4}\b', '', query).strip().lower()

    if not search_query:
        await loading_msg.edit("⚠️ Please provide a valid movie or TV show name.")
        return

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
        filtered_results = results
        result_types = ["movie" if r in movie_results else "tv" for r in results]

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
        "timestamp": time.time()
    }

    await send_result(client, message.chat.id, user_id, 0, loading_msg)

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
        button_url = f"https://hindicinema.xyz/best/result/x/{res_id}/{res_type.lower()}"
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

async def cleanup_search_results():
    while True:
        await asyncio.sleep(3600)
        current_time = time.time()
        for user_id in list(search_results.keys()):
            if current_time - search_results[user_id].get("timestamp", 0) > 3600:
                del search_results[user_id]

# NEW: Periodic cleanup of inactive users
async def cleanup_users():
    while True:
        await asyncio.sleep(24 * 3600)  # Run daily
        threshold = time.time() - 30 * 24 * 3600  # 30 days
        users.delete_many({"last_seen": {"$lt": threshold}})

if __name__ == "__main__":
    try:
        mongo.server_info()
        logging.info("✅ Connected to MongoDB")
        check_site_connection()
        app.start()
        logging.info("✅ Bot started successfully")
        app.loop.create_task(cleanup_search_results())
        app.loop.create_task(cleanup_users())
        idle()
        app.stop()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
