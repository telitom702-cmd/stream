# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import os
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


MAX_FILE_SIZE = 5 * 1024 * 1024


async def upload_to_telegraph(file_path):
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as file:
                form = aiohttp.FormData()
                form.add_field(
                    "file",
                    file,
                    filename=os.path.basename(file_path),
                )

                async with session.post(
                    "https://telegra.ph/upload",
                    data=form
                ) as response:

                    result = await response.text()

                    if response.status != 200:
                        print(f"Telegraph HTTP {response.status}: {result}")
                        return None

                    try:
                        data = await response.json(content_type=None)
                    except Exception:
                        print(f"Invalid Telegraph response: {result}")
                        return None

                    if isinstance(data, list) and data:
                        src = data[0].get("src")

                        if src:
                            return "https://telegra.ph" + src

                    print(f"Telegraph upload failed: {data}")
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

    if t_msg.photo.file_size and t_msg.photo.file_size > MAX_FILE_SIZE:
        return await update.reply_text(
            "**❌ File size must be under 5MB.**"
        )

    path = None

    try:
        path = await t_msg.download()

        uploading_message = await update.reply_text(
            "<b>ᴜᴘʟᴏᴀᴅɪɴɢ...</b>"
        )

        image_url = await upload_to_telegraph(path)

        if not image_url:
            return await uploading_message.edit_text(
                "**❌ Failed to upload image.**"
            )

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

    except Exception as error:
        print(f"Telegraph command error: {error}")

        if 'uploading_message' in locals():
            await uploading_message.edit_text(
                f"**❌ Upload failed:** `{error}`"
            )
        else:
            await update.reply_text(
                f"**❌ Upload failed:** `{error}`"
            )

    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
