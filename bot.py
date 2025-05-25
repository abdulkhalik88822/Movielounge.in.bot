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

# Load environment variables from .env file
load_dotenv()

# Configure logging to save logs to bot.log
logging.basicConfig(level=logging.INFO, filename='bot.log', format='%(asctime)s - %(levelname)s - %(message)s')

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")
mongo = MongoClient(MONGO_URI)
db = mongo["movie_bot"]
searches = db["searches"]
users = db["users"]  # Collection for user data

# Admin Telegram ID
ADMIN_ID = 6133440326

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_NAME = "DD_search_movie_bot"

# Laravel API configuration
LARAVEL_API_TOKEN = os.getenv("LARAVEL_API_TOKEN")
LARAVEL_API_URL = "https://api.cinema4u.xyz/api"
search_results = {}

# Initialize Pyrogram client
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
    # Display a countdown timer while waiting for site response
    for i in range(timeout_duration):
        if site_connected:
            break
        sys.stdout.write(f"\r⏳ [Admin ID: {ADMIN_ID}] Waiting for site response... {i + 1}/{timeout_duration} seconds")
        sys.stdout.flush()
        time.sleep(1)
    if not site_connected:
        sys.stdout.write("\n")

def check_site_connection():
    # Check connection to Laravel site
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
        print(f"\n🔄 [Admin ID: {ADMIN_ID}] Attempting to connect to Laravel site, try {attempt}...")
        logging.info(f"Attempting to connect to Laravel site, try {attempt}")

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
                logging.info("Successfully connected to Laravel site.")
                return
            else:
                try:
                    error_detail = response.json()
                except ValueError:
                    error_detail = response.text
                print(f"\n❌ [Admin ID: {ADMIN_ID}] Status: {response.status_code}, Response: {error_detail}")
                logging.error(f"Laravel site connection failed, status: {response.status_code}, response: {error_detail}")

        except requests.exceptions.RequestException as e:
            site_connected = False
            timer_thread.join()
            print(f"\n❌ [Admin ID: {ADMIN_ID}] Error: {str(e)}")
            logging.error(f"Laravel site connection error: {str(e)}")

        if attempt < max_retries:
            wait_time = retry_delay * attempt
            print(f"🔁 [Admin ID: {ADMIN_ID}] Retrying in {wait_time} seconds...")
            logging.info(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            print(f"🚨 [Admin ID: {ADMIN_ID}] All retries failed. Skipping this connection attempt.")
            logging.error("All retries failed. Skipping Laravel site connection.")
            return

# Handle /start command
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user = message.from_user
    user_id = user.id
    user_name = user.first_name
    username = user.username or user_name

    # Store user in MongoDB
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
        logging.info(f"User {user_id} stored in MongoDB.")
    except Exception as e:
        logging.error(f"Error storing user {user_id} in MongoDB: {e}")

    welcome_message = (
        f"👋 Hello, {user_name}!\n\n"
        f"🎥 I'm your personal movie and TV show assistant. "
        f"Just type the name of any movie or series, "
        f"and I'll fetch the details instantly.\n\n"
        f"🚀 Let's get started!\n\n"
        f"🙌 **Credits**:\n"
        f"👨‍💻 **Developer**: [Abdul khalik](https://t.me/Attitude2688)\n" 
        f"👑 **Owner**: [Abdul Khalik](https://t.me/Attitude2688)"
    )
    
    image_url = "https://telegra.ph/file/5d32303d074c709406576.jpg"
    buttons = [
        [InlineKeyboardButton("Add me to a group", url=f"https://t.me/{BOT_NAME}?startgroup=true")],
        [
            InlineKeyboardButton("API Status", callback_data="api_status"),
            InlineKeyboardButton("DB Status", callback_data="db_status")
        ],
        [InlineKeyboardButton("Bot Developer", url="https://t.me/Attitude2688")]
    ]
    
    await client.send_photo(
        chat_id=message.chat.id,
        photo=image_url,
        caption=welcome_message,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Handle /broadcast command (Admin only)
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("🚫 You are not authorized to use this command.")
        logging.warning(f"Unauthorized user {message.from_user.id} attempted to use /broadcast.")
        return

    # Check if the message is a reply to another message
    target_message = message.reply_to_message if message.reply_to_message else message
    logging.info(f"Broadcast initiated, target message ID: {target_message.id}")

    # Extract broadcast content (text, photo, video, document, or buttons)
    broadcast_message = None
    broadcast_photo = None
    broadcast_video = None
    broadcast_document = None
    broadcast_reply_markup = None

    # Extract text or caption
    if target_message.text:
        text_parts = target_message.text.split(maxsplit=1)
        if len(text_parts) > 1:  # If there's text after /broadcast or in replied message
            broadcast_message = text_parts[1] if target_message == message else target_message.text
    elif target_message.caption:
        caption_parts = target_message.caption.split(maxsplit=1)
        if len(caption_parts) > 1:  # If there's caption after /broadcast or in replied message
            broadcast_message = caption_parts[1] if target_message == message else target_message.caption
        else:
            broadcast_message = target_message.caption or ""

    # Extract media
    if target_message.photo:
        broadcast_photo = target_message.photo.file_id
    elif target_message.video:
        broadcast_video = target_message.video.file_id
    elif target_message.document:
        broadcast_document = target_message.document.file_id

    # Extract inline keyboard (URL buttons)
    if target_message.reply_markup and isinstance(target_message.reply_markup, InlineKeyboardMarkup):
        broadcast_reply_markup = target_message.reply_markup

    # Validate broadcast content
    if not (broadcast_message or broadcast_photo or broadcast_video or broadcast_document):
        await message.reply("⚠️ Please provide a valid message, photo, video, or document to broadcast, or reply to a message.")
        logging.error("Broadcast failed: No valid content provided.")
        return

    # Fetch all users from MongoDB
    try:
        total_users = users.count_documents({})
        user_list = users.find({}, {"user_id": 1})
        logging.info(f"Total users found: {total_users}")
    except Exception as e:
        await message.reply("❌ Error accessing user database.")
        logging.error(f"Error accessing user database: {e}")
        return

    if total_users == 0:
        await message.reply("😕 No users found to broadcast.")
        logging.info("Broadcast aborted: No users found.")
        return

    # Initialize counters
    success_count = 0
    ban_bot_count = 0  # For blocked or invalid users
    not_complete_count = 0  # For other failures
    batch_size = 100  # Update status after every 100 users
    loading_msg = await message.reply(f"📢 Starting broadcast to {total_users} users...")

    # Broadcast to users
    for i, user in enumerate(user_list):
        user_id = user["user_id"]
        try:
            if broadcast_photo:
                await client.send_photo(
                    chat_id=user_id,
                    photo=broadcast_photo,
                    caption=broadcast_message or "",
                    reply_markup=broadcast_reply_markup
                )
            elif broadcast_video:
                await client.send_video(
                    chat_id=user_id,
                    video=broadcast_video,
                    caption=broadcast_message or "",
                    reply_markup=broadcast_reply_markup
                )
            elif broadcast_document:
                await client.send_document(
                    chat_id=user_id,
                    document=broadcast_document,
                    caption=broadcast_message or "",
                    reply_markup=broadcast_reply_markup
                )
            else:
                await client.send_message(
                    chat_id=user_id,
                    text=broadcast_message,
                    reply_markup=broadcast_reply_markup
                )
            success_count += 1
            logging.info(f"Broadcast successful to user {user_id}.")
        except (pyrogram.errors.UserIsBlocked, pyrogram.errors.ChatInvalid, pyrogram.errors.UserDeactivated):
            try:
                users.delete_one({"user_id": user_id})
                logging.info(f"Blocked/invalid user {user_id} removed from database.")
                ban_bot_count += 1
            except Exception as e:
                logging.error(f"Error removing user {user_id} from MongoDB: {e}")
                ban_bot_count += 1
        except Exception as e:
            logging.warning(f"Failed to broadcast to user {user_id}: {e}")
            not_complete_count += 1

        # Update progress every batch_size users
        if (i + 1) % batch_size == 0:
            await loading_msg.edit(
                f"📢 Broadcast in progress...\n"
                f"🔄 Total Users: {total_users}\n"
                f"✅ Completed: {success_count}\n"
                f"🚫 Ban Bot: {ban_bot_count}\n"
                f"❌ Not Complete: {not_complete_count}"
            )
        await asyncio.sleep(0.1)  # 100ms delay to avoid rate limits

    # Final status update
    await loading_msg.edit(
        f"📢 Broadcast completed!\n"
        f"🔄 Total Users: {total_users}\n"
        f"✅ Completed: {success_count}\n"
        f"🚫 Ban Bot: {ban_bot_count}\n"
        f"❌ Not Complete: {not_complete_count}"
    )

    # Log broadcast details
    broadcast_type = "photo" if broadcast_photo else "video" if broadcast_video else "document" if broadcast_document else "text"
    logging.info(
        f"Broadcast by Admin ID {ADMIN_ID}: "
        f"Type: {broadcast_type}, "
        f"Message: '{broadcast_message or 'Media without caption'}', "
        f"Buttons: {broadcast_reply_markup is not None}, "
        f"Total Users: {total_users}, Completed: {success_count}, Ban Bot: {ban_bot_count}, Not Complete: {not_complete_count}"
    )

# Handle /usercount command (Admin only)
@app.on_message(filters.command("usercount") & filters.user(ADMIN_ID))
async def user_count(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("🚫 You are not authorized to use this command.")
        logging.warning(f"Unauthorized user {message.from_user.id} attempted to use /usercount.")
        return

    try:
        total_users = users.count_documents({})
        await message.reply(f"📊 Total users in database: {total_users}")
        logging.info(f"User count requested, total users: {total_users}")
    except Exception as e:
        logging.error(f"Error fetching user count: {e}")
        await message.reply("❌ Error accessing user database.")

# Handle callback queries
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
        await callback_query.message.reply(f"🔍 API Connection Status: {status}")
        logging.info(f"API status checked, result: {status}")
        return

    if data == "db_status":
        if user_id != ADMIN_ID:
            await callback_query.answer("🚫 You are not authorized to check DB status.", show_alert=True)
            return
        try:
            mongo.server_info()
            await callback_query.message.reply("✅ Database is connected.")
            logging.info("Database status check: Connected")
        except Exception as e:
            await callback_query.message.reply(f"❌ Database Error: {str(e)}")
            logging.error(f"Database status check error: {str(e)}")
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

# Handle /api command (Admin only)
@app.on_message(filters.command("api"))
async def api_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if user_id != ADMIN_ID:
        await message.reply("🚫 You are not authorized to use this command.")
        await client.send_message(
            ADMIN_ID,
            f"⚠️ Unauthorized user {user_name} (ID: {user_id}) attempted to use /api command."
        )
        logging.warning(f"Unauthorized user {user_id} attempted to use /api command.")
        return

    check_site_connection()
    status = "✅ Connected" if site_connected else "❌ Not Connected"
    await message.reply(f"🔍 Site Connection Status: {status}")
    logging.info(f"/api command, site connection status: {status}")

# Handle movie/TV search
@app.on_message(filters.text & ~filters.command(["start", "api", "broadcast", "usercount"]))
async def search_movie_or_tv(client, message: Message):
    if not site_connected:
        await message.reply("🚫 Bot is currently not connected to the site. Please try again later.")
        logging.warning("Search aborted: Not connected to site.")
        return

    query = message.text.strip()
    user = message.from_user
    user_id = user.id
    username = user.username or user.first_name

    # Store user during search
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
        logging.info(f"User {user_id} stored in MongoDB during search.")
    except Exception as e:
        logging.error(f"Error storing user {user_id} in MongoDB: {e}")

    await client.send_message(ADMIN_ID, f"🧐 User `{username}` searched: `{query}`")
    logging.info(f"User {username} searched: {query}")

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
        logging.info(f"Search query sent to Laravel site: {query}")
    except Exception as e:
        logging.warning(f"Failed to send search query to Laravel site: {e}")

    loading_msg = await message.reply("**AI is searching for your results...**")

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
        await loading_msg.edit(f"⚠️ TMDb API Error: {e}. Please try again later.")
        return
    except Exception as e:
        logging.error(f"Search failed for query '{search_query}': {e}")
        await loading_msg.edit("⚠️ Error during search. Please try again later.")
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
            logging.error(f"TMDb API error for ID {res_id}: {e}")
            await client.send_message(chat_id, f"⚠️ TMDb API Error: {e}. Skipping this result.")
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
        logging.error(f"TMDb API error for ID {res_id}: {e}")
        await loading_msg.edit(f"⚠️ TMDb API Error: {e}. Cannot display this result.")
        return
    except Exception as e:
        logging.error(f"Error fetching details for ID {res_id}: {e}")
        await loading_msg.edit("⚠️ Error fetching details. Cannot display this result.")
        return

    caption = f"**{title}** ({year})\n\n**Genre**: {genres}"

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

if __name__ == "__main__":
    try:
        # Check MongoDB connection
        mongo.server_info()
        logging.info("✅ Connected to MongoDB")
        check_site_connection()
        app.start()
        logging.info("✅ Bot started successfully")
        app.loop.create_task(cleanup_search_results())
        idle()
        app.stop()
    except Exception as e:
        logging.error(f"Error occurred: {e}")
