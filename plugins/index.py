import logging
import os
import tempfile
import time
import re
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import ADMINS, INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp


def get_readable_time(seconds):
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
from math import ceil

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing")
    _, raju, chat, lst_msg_id, from_user = query.data.split("#")
    if raju == 'reject':
        await query.message.delete()
        await bot.send_message(int(from_user),
                               f'Your Submission for indexing {chat} has been declined by our moderators.',
                               reply_to_message_id=int(lst_msg_id))
        return

    if lock.locked():
        return await query.answer('Wait until previous process complete.', show_alert=True)
    msg = query.message

    await query.answer('Processing...⏳', show_alert=True)
    if int(from_user) not in ADMINS:
        await bot.send_message(int(from_user),
                               f'Your Submission for indexing {chat} has been accepted by our moderators and will be added soon.',
                               reply_to_message_id=int(lst_msg_id))
    await msg.edit(
        "Starting Indexing",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
        )
    )
    try:
        chat = int(chat)
    except:
        chat = chat
    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


@Client.on_message((filters.forwarded | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text ) & filters.private & filters.incoming)
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match:
            return await message.reply('Invalid link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id  = int(("-100" + chat_id))
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return
    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply('This may be a private channel / group. Make me an admin over there to index the files.')
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply('Invalid Link specified.')
    except Exception as e:
        logger.exception(e)
        return await message.reply(f'Errors - {e}')
    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except:
        return await message.reply('Make Sure That Iam An Admin In The Channel, if channel is private')
    if k.empty:
        return await message.reply('This may be group and i am not a admin of the group.')

    if message.from_user.id in ADMINS:
        buttons = [
            [InlineKeyboardButton('Yes', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
            [InlineKeyboardButton('Close', callback_data='close_data')]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        return await message.reply(
            f'Do you Want To Index This Channel/ Group ?\n\nChat ID/ Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>\n\nɴᴇᴇᴅ sᴇᴛsᴋɪᴘ 👉🏻 /setskip',
            reply_markup=reply_markup)

    if type(chat_id) is int:
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply('Make sure I am an admin in the chat and have permission to invite users.')
    else:
        link = f"@{message.forward_from_chat.username}"
    buttons = [
        [InlineKeyboardButton('Accept Index', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton('Reject Index', callback_data=f'index#reject#{chat_id}#{message.id}#{message.from_user.id}')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await bot.send_message(LOG_CHANNEL,
                           f'#IndexRequest\n\nBy : {message.from_user.mention} (<code>{message.from_user.id}</code>)\nChat ID/ Username - <code> {chat_id}</code>\nLast Message ID - <code>{last_msg_id}</code>\nInviteLink - {link}',
                           reply_markup=reply_markup)
    await message.reply('ThankYou For the Contribution, Wait For My Moderators to verify the files.')


@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    if ' ' in message.text:
        _, skip = message.text.split(" ")
        try:
            skip = int(skip)
        except:
            return await message.reply("Skip number should be an integer.")
        await message.reply(f"Successfully set SKIP number as {skip}")
        temp.CURRENT = int(skip)
    else:
        await message.reply("Give me a skip number")

def get_progress_bar(percent, length=10):
    """Creates an emoji-based progress bar."""
    filled = int(length * percent / 100)
    unfilled = length - filled
    return '🟩' * filled + '⬜️' * unfilled

FETCH_RETRY = 5
SAVE_RETRY = 3
SAVE_PARALLEL = 200


async def safe_edit(msg, text, markup=None):
    try:
        await msg.edit(text, reply_markup=markup)
    except MessageNotModified:
        pass
    except FloodWait as e:
        await asyncio.sleep(int(getattr(e, "value", 3)) + 1)
    except Exception:
        pass  # progress আপডেট ব্যর্থ হলে indexing থামবে না


async def fetch_batch(bot, chat, ids):
    for attempt in range(FETCH_RETRY):
        try:
            messages = await bot.get_messages(chat, ids)
            return messages if isinstance(messages, list) else [messages]
        except FloodWait as e:
            await asyncio.sleep(int(getattr(e, "value", 5)) + 1)
        except Exception as e:
            logger.warning(f"Fetch {ids[0]}-{ids[-1]} failed (try {attempt + 1}): {e}")
            await asyncio.sleep(2 * (attempt + 1))
    return None


async def save_with_retry(sem, media):
    """একসাথে সীমিত সংখ্যক save; DB ব্যর্থ (code 3) হলে আবার চেষ্টা।"""
    async with sem:
        result = (False, 3)
        for attempt in range(SAVE_RETRY):
            result = await save_file(media)
            if result[1] != 3:
                return result
            await asyncio.sleep(1 + attempt)
        return result


async def send_report(msg, skipped, counts):
    lines = ["INDEX REPORT", ""] + [f"{k}: {v}" for k, v in counts.items()]
    lines += ["", "Message ID | Reason", "-" * 40]
    lines += [f"{mid} | {reason}" for mid, reason in skipped]
    path = os.path.join(tempfile.gettempdir(), f"index_report_{int(time.time())}.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        await msg.reply_document(path, caption="📄 Skipped / failed messages report")
    except Exception:
        logger.exception("Could not send index report")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    BATCH_SIZE = 200
    start_time = time.time()
    skipped = []  # (message_id, reason) -- deleted/no_media বাদে
    close_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Close', callback_data='close_data')]])
    cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])

    async with lock:
        try:
            temp.CANCEL = False
            sem = asyncio.Semaphore(SAVE_PARALLEL)
            first_id = max(int(temp.CURRENT), 1)
            total_fetch = lst_msg_id - first_id + 1
            if total_fetch <= 0:
                return await safe_edit(msg, "🚫 No Messages To Index.", close_markup)
            batches = ceil(total_fetch / BATCH_SIZE)
            batch_times = []
            await safe_edit(
                msg,
                f"📊 Indexing Starting......\n"
                f"💬 Last Message ID: <code>{lst_msg_id}</code>\n"
                f"📋 Total Fetch: <code>{total_fetch}</code>",
                cancel_markup
            )
            current = first_id - 1
            for batch in range(batches):
                if temp.CANCEL:
                    break
                batch_start = time.time()
                start_id = current + 1
                end_id = min(current + BATCH_SIZE, lst_msg_id)
                if start_id > end_id:
                    break
                message_ids = list(range(start_id, end_id + 1))
                messages = await fetch_batch(bot, chat, message_ids)
                current = end_id
                if messages is None:
                    errors += len(message_ids)
                    skipped.extend((i, "fetch failed") for i in message_ids)
                    continue

                medias, meta = [], []
                for message in messages:
                    try:
                        if message.empty:
                            deleted += 1
                            continue
                        elif not message.media:
                            no_media += 1
                            continue
                        elif message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                            unsupported += 1
                            skipped.append((message.id, f"unsupported media type: {message.media.value}"))
                            continue
                        media = getattr(message, message.media.value, None)
                        if not media:
                            unsupported += 1
                            skipped.append((message.id, f"media missing: {message.media.value}"))
                            continue
                        media.file_type = message.media.value
                        media.caption = message.caption
                        medias.append(media)
                        meta.append((message.id, f"{message.media.value}: {getattr(media, 'file_name', None) or 'no file name'}"))
                    except Exception as e:
                        errors += 1
                        skipped.append((getattr(message, "id", "?"), f"handling error: {e!r}"))

                results = await asyncio.gather(*[save_with_retry(sem, m) for m in medias], return_exceptions=True)
                for (mid, label), result in zip(meta, results):
                    if isinstance(result, Exception):
                        errors += 1
                        skipped.append((mid, f"save exception: {result!r} ({label})"))
                        continue
                    ok, code = result
                    if ok:
                        total_files += 1
                    elif code == 0:
                        duplicate += 1
                        skipped.append((mid, f"duplicate - already in DB ({label})"))
                    else:
                        errors += 1
                        skipped.append((mid, f"save failed, code {code} ({label})"))

                batch_times.append(time.time() - batch_start)
                elapsed = time.time() - start_time
                progress = current - first_id + 1
                percentage = min(progress / total_fetch * 100, 100)
                avg_batch_time = sum(batch_times) / len(batch_times)
                eta = (batches - batch - 1) * avg_batch_time
                await safe_edit(
                    msg,
                    f"📊 Indexing Progress 📦 Batch {batch + 1}/{batches}\n"
                    f"{get_progress_bar(int(percentage))} <code>{percentage:.1f}%</code>\n\n"
                    f"Fetched: <code>{progress}</code> / <code>{total_fetch}</code>\n"
                    f"Saved: <code>{total_files}</code>\n"
                    f"Duplicates: <code>{duplicate}</code>\n"
                    f"Deleted: <code>{deleted}</code>\n"
                    f"Non-Media: <code>{no_media + unsupported}</code> (Unsupported: <code>{unsupported}</code>)\n"
                    f"Errors: <code>{errors}</code>\n"
                    f"⏱️ Elapsed: <code>{get_readable_time(elapsed)}</code>\n"
                    f"⏰ ETA: <code>{get_readable_time(eta)}</code>",
                    cancel_markup
                )

            title = "🛑 Indexing Cancelled!" if temp.CANCEL else "✅ Indexing Completed!"
            counts = {
                "Fetched": current - first_id + 1, "Saved": total_files, "Duplicates": duplicate,
                "Deleted": deleted, "Non-Media": no_media + unsupported,
                "Unsupported": unsupported, "Errors": errors,
            }
            await safe_edit(
                msg,
                f"{title}\n"
                f"Fetched: <code>{counts['Fetched']}</code> / <code>{total_fetch}</code>\n"
                f"Saved: <code>{total_files}</code>\n"
                f"Duplicates: <code>{duplicate}</code>\n"
                f"Deleted: <code>{deleted}</code>\n"
                f"Non-Media: <code>{no_media + unsupported}</code> (Unsupported: <code>{unsupported}</code>)\n"
                f"Errors: <code>{errors}</code>\n"
                f"⏱️ Elapsed: <code>{get_readable_time(time.time() - start_time)}</code>",
                close_markup
            )
            if skipped:
                await send_report(msg, skipped, counts)
        except Exception as e:
            logger.exception(e)
            await safe_edit(
                msg,
                f"❌ Error: <code>{e}</code>\n\n"
                f"Saved so far: <code>{total_files}</code> | Duplicates: <code>{duplicate}</code> | Errors: <code>{errors}</code>",
                close_markup
            )
