from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, Message
from pymongo import MongoClient
import logging
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, filename='bot.log', format='%(asctime)s - %(levelname)s - %(message)s')

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")
mongo = MongoClient(MONGO_URI)
db = mongo["movie_bot"]
users = db["users"]  # User data collection

# Admin Telegram ID
ADMIN_ID = 6133440326

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# Initialize Pyrogram client
app = Client(
    "movie_bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# Handle /broadcast command (Admin only)
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client: Client, message: Message):
    # Verify admin access
    if message.from_user.id != ADMIN_ID:
        await message.reply("🚫 You are not authorized to use this command.")
        logging.warning(f"Unauthorized user {message.from_user.id} attempted to use /broadcast.")
        return

    # Log broadcast initiation
    logging.info(f"Broadcast initiated by Admin ID {ADMIN_ID}")

    # Get target message (replied message or current message)
    target_message = message.reply_to_message if message.reply_to_message else message
    logging.info(f"Target message ID: {target_message.id}")

    # Extract broadcast content
    broadcast_message = None
    broadcast_photo = None
    broadcast_reply_markup = None

    # Extract text or caption
    if target_message.text:
        broadcast_message = target_message.text
    elif target_message.caption:
        broadcast_message = target_message.caption or ""

    # Extract photo (if any)
    if target_message.photo:
        broadcast_photo = target_message.photo.file_id

    # Extract inline keyboard (URL buttons)
    if target_message.reply_markup and isinstance(target_message.reply_markup, InlineKeyboardMarkup):
        broadcast_reply_markup = target_message.reply_markup

    # Validate content
    if not (broadcast_message or broadcast_photo):
        await message.reply("⚠️ Please provide a valid text message or photo to broadcast, or reply to a message.")
        logging.error("Broadcast failed: No valid content provided.")
        return

    # Fetch users from MongoDB
    try:
        total_users = users.count_documents({})
        user_list = list(users.find({}, {"user_id": 1}))  # Convert to list for reliability
        logging.info(f"Total users found: {total_users}")
    except Exception as e:
        await message.reply("❌ Error accessing user database. Check MongoDB connection.")
        logging.error(f"Error fetching users from MongoDB: {e}")
        return

    if total_users == 0:
        await message.reply("😕 No users found to broadcast.")
        logging.info("Broadcast aborted: No users found.")
        return

    # Initialize counters
    success_count = 0
    ban_bot_count = 0
    not_complete_count = 0
    batch_size = 50  # Update status every 50 users for testing
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
            try:
                await loading_msg.edit(
                    f"📢 Broadcast in progress...\n"
                    f"🔄 Total Users: {total_users}\n"
                    f"✅ Completed: {success_count}\n"
                    f"🚫 Ban Bot: {ban_bot_count}\n"
                    f"❌ Not Complete: {not_complete_count}"
                )
                logging.info(f"Progress update: {success_count}/{total_users} users processed.")
            except Exception as e:
                logging.error(f"Error updating progress message: {e}")

        await asyncio.sleep(0.2)  # 200ms delay to avoid rate limits

    # Final status update
    try:
        await loading_msg.edit(
            f"📢 Broadcast completed!\n"
            f"🔄 Total Users: {total_users}\n"
            f"✅ Completed: {success_count}\n"
            f"🚫 Ban Bot: {ban_bot_count}\n"
            f"❌ Not Complete: {not_complete_count}"
        )
        logging.info(
            f"Broadcast completed: Total Users: {total_users}, "
            f"Completed: {success_count}, Ban Bot: {ban_bot_count}, Not Complete: {not_complete_count}"
        )
    except Exception as e:
        logging.error(f"Error sending final status message: {e}")
        await message.reply("⚠️ Broadcast finished, but failed to update final status.")

if __name__ == "__main__":
    try:
        # Check MongoDB connection
        mongo.server_info()
        logging.info("✅ Connected to MongoDB")
        app.start()
        logging.info("✅ Bot started successfully")
        idle()
        app.stop()
    except Exception as e:
        logging.error(f"Startup error: {e}")
