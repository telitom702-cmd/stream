# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import os
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


MAX_FILE_SIZE = 10 * 1024 * 1024


async def upload_image(file_path):
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as file:

                form = aiohttp.FormData()
                form.add_field(
                    "file",
                    file,
                    filename=os.path.basename(file_path)
                )
                form.add_field("visibility", "unlisted")

                async with session.post(
                    "https://picrd.com/api/upload",
                    data=form
                ) as response:

                    data = await response.json(content_type=None)

                    if response.status == 200:
                        return data.get("image_url")

                    print(f"Upload failed: {response.status} - {data}")
                    return None

    except Exception as e:
        print(f"Upload error: {e}")
        return None


@Client.on_message(filters.command("telegraph") & filters.private)
async def telegraph_upload(bot, update):

    t_msg = await bot.ask(
        chat_id=update.from_user.id,
        text="📸 **Send Me Your Photo Under 10MB.**"
    )

    if not t_msg.photo:
        return await update.reply_text(
            "**❌ Only Photo Supported.**"
        )

    # 10MB limit
    if t_msg.photo.file_size and t_msg.photo.file_size > MAX_FILE_SIZE:
        return await update.reply_text(
            "**❌ File size must be under 10MB.**"
        )

    path = None

    try:
        path = await t_msg.download()

        uploading_message = await update.reply_text(
            "<b>ᴜᴘʟᴏᴀᴅɪɴɢ...</b>"
        )

        image_url = await upload_image(path)

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

    except Exception as e:
        print(f"Telegraph command error: {e}")

        if "uploading_message" in locals():
            await uploading_message.edit_text(
                f"**❌ Upload failed:** `{e}`"
            )
        else:
            await update.reply_text(
                f"**❌ Upload failed:** `{e}`"
            )

    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except:
                passpass
