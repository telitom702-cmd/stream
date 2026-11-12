# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import os
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


async def upload_to_telegraph(file_path):
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field(
                    "file",
                    f,
                    filename=os.path.basename(file_path),
                    content_type="image/jpeg"
                )

                async with session.post(
                    "https://telegra.ph/upload",
                    data=form
                ) as response:

                    if response.status == 200:
                        result = await response.json()

                        if isinstance(result, list) and result:
                            return "https://telegra.ph" + result[0]["src"]

        return None

    except Exception as e:
        print(f"Telegraph upload error: {e}")
        return None


@Client.on_message(filters.command("telegraph") & filters.private)
async def telegraph_upload(bot, update):

    t_msg = await bot.ask(
        chat_id=update.from_user.id,
        text="📸 **Send me a Photo under 5MB.**"
    )

    if not t_msg.photo:
        return await update.reply_text(
            "**❌ Only Photo Supported.**"
        )

    # Check 5MB limit
    if t_msg.photo.file_size and t_msg.photo.file_size > 5 * 1024 * 1024:
        return await update.reply_text(
            "**❌ File size must be under 5MB.**"
        )

    path = await t_msg.download()

    uploading_message = await update.reply_text(
        "<b>ᴜᴘʟᴏᴀᴅɪɴɢ...</b>"
    )

    try:
        image_url = await upload_to_telegraph(path)

        if not image_url:
            return await uploading_message.edit_text(
                "**❌ Failed to upload image.**"
            )

    except Exception as error:
        await uploading_message.edit_text(
            f"**❌ Upload failed:** `{error}`"
        )
        return

    try:
        os.remove(path)
    except:
        pass

    await uploading_message.edit_text(
        text=f"<b>Link :-</b>\n\n<code>{image_url}</code>",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="Open Link",
                    url=image_url
                ),
                InlineKeyboardButton(
                    text="Share Link",
                    url=f"https://telegram.me/share/url?url={image_url}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✗ Close ✗",
                    callback_data="close"
                )
            ]
        ])
    )
