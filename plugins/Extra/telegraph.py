# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import os
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


async def upload_to_telegraph(file_path):
    """Telegraph upload বন্ধ, তাই catbox.moe ব্যবহার করা হয়েছে।"""
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            with open(file_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("reqtype", "fileupload")
                form.add_field(
                    "fileToUpload",
                    f,
                    filename=os.path.basename(file_path)
                )

                async with session.post(
                    "https://catbox.moe/user/api.php",
                    data=form
                ) as response:
                    text = (await response.text()).strip()

                    if response.status == 200 and text.startswith("http"):
                        return text

                    print(f"Upload error: {response.status} {text}")

        return None

    except Exception as e:
        print(f"Upload error: {e}")
        return None


@Client.on_message(filters.command("telegraph") & filters.private)
async def telegraph_upload(bot, update):

    t_msg = await bot.ask(
        chat_id=update.from_user.id,
        text="📸 **Send me a Photo under 5MB.**"
    )

    if not t_msg.photo:
        return await update.reply_text("**❌ Only Photo Supported.**")

    # Check 5MB limit
    if t_msg.photo.file_size and t_msg.photo.file_size > 5 * 1024 * 1024:
        return await update.reply_text("**❌ File size must be under 5MB.**")

    path = await t_msg.download()
    uploading_message = await update.reply_text("<b>Uploading...</b>")

    try:
        image_url = await upload_to_telegraph(path)
    except Exception as error:
        image_url = None
        print(f"Upload failed: {error}")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

    if not image_url:
        return await uploading_message.edit_text(
            "**❌ Failed to upload image.**"
        )

    await uploading_message.edit_text(
        text=f"<b>Link :-</b>\n\n<code>{image_url}</code>",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(text="Open Link", url=image_url),
                InlineKeyboardButton(
                    text="Share Link",
                    url=f"https://telegram.me/share/url?url={image_url}"
                )
            ],
            [
                InlineKeyboardButton(text="❌ Close ❌", callback_data="close")
            ]
        ])
                )
