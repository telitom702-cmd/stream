# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import logging
import re
import asyncio

from utils import temp
from info import ADMINS

from pyrogram import (
    Client,
    filters,
    enums
)

from pyrogram.errors import (
    FloodWait,
    MessageNotModified
)

from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid,
    ChatAdminRequired,
    UsernameInvalid,
    UsernameNotModified
)

from info import INDEX_REQ_CHANNEL as LOG_CHANNEL

from database.ia_filterdb import save_file

from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

lock = asyncio.Lock()


# =========================================================
# INDEX CALLBACK
# =========================================================

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):

    if query.data.startswith('index_cancel'):

        temp.CANCEL = True

        try:
            await query.answer(
                "Cancelling Indexing..."
            )
        except:
            pass

        return

    try:

        _, raju, chat, lst_msg_id, from_user = (
            query.data.split("#")
        )

    except Exception as e:

        logger.exception(e)

        return await query.answer(
            "Invalid indexing request.",
            show_alert=True
        )

    # -----------------------------------------------------
    # REJECT
    # -----------------------------------------------------

    if raju == 'reject':

        try:
            await query.message.delete()
        except:
            pass

        try:
            await bot.send_message(
                int(from_user),

                f"Your Submission for indexing "
                f"{chat} has been declined by our moderators.",

                reply_to_message_id=int(lst_msg_id)
            )
        except Exception as e:

            logger.exception(e)

        return

    # -----------------------------------------------------
    # LOCK
    # -----------------------------------------------------

    if lock.locked():

        return await query.answer(
            "Wait until previous process complete.",
            show_alert=True
        )

    msg = query.message

    await query.answer(
        "Processing...⏳",
        show_alert=True
    )

    # -----------------------------------------------------
    # USER NOT ADMIN
    # -----------------------------------------------------

    if int(from_user) not in ADMINS:

        try:

            await bot.send_message(
                int(from_user),

                f"Your Submission for indexing "
                f"{chat} has been accepted by our moderators "
                f"and will be added soon.",

                reply_to_message_id=int(lst_msg_id)
            )

        except Exception as e:

            logger.exception(e)

    # -----------------------------------------------------
    # START MESSAGE
    # -----------------------------------------------------

    try:

        await msg.edit(
            "Starting Indexing...",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Cancel",
                            callback_data="index_cancel"
                        )
                    ]
                ]
            )
        )

    except MessageNotModified:
        pass

    # -----------------------------------------------------
    # CHAT ID
    # -----------------------------------------------------

    try:
        chat = int(chat)
    except:
        pass

    # -----------------------------------------------------
    # START INDEXING
    # -----------------------------------------------------

    await index_files_to_db(
        int(lst_msg_id),
        chat,
        msg,
        bot
    )


# =========================================================
# /INDEX
# =========================================================

@Client.on_message(
    filters.private &
    filters.command('index')
)
async def send_for_index(bot, message):

    vj = await bot.ask(
        message.chat.id,

        "**Now Send Me Your Channel Last Post Link "
        "Or Forward A Last Message From Your Index Channel.**\n\n"
        "**And You Can Set Skip Number By - "
        "/setskip yourskipnumber**"
    )

    # =====================================================
    # FORWARDED MESSAGE
    # =====================================================

    if (
        vj.forward_from_chat
        and
        vj.forward_from_chat.type ==
        enums.ChatType.CHANNEL
    ):

        last_msg_id = vj.forward_from_message_id

        chat_id = (
            vj.forward_from_chat.username
            or
            vj.forward_from_chat.id
        )

    # =====================================================
    # MESSAGE LINK
    # =====================================================

    elif vj.text:

        regex = re.compile(
            r"(https://)?"
            r"(t\.me/|telegram\.me/|telegram\.dog/)"
            r"(c/)?"
            r"(\d+|[a-zA-Z_0-9]+)/"
            r"(\d+)$"
        )

        match = regex.match(
            vj.text.strip()
        )

        if not match:

            return await vj.reply(
                "Invalid link\n\n"
                "Try again by /index"
            )

        chat_id = match.group(4)

        last_msg_id = int(
            match.group(5)
        )

        if chat_id.isnumeric():

            chat_id = int(
                "-100" + chat_id
            )

    else:

        return

    # =====================================================
    # CHECK CHAT
    # =====================================================

    try:

        await bot.get_chat(chat_id)

    except ChannelInvalid:

        return await vj.reply(
            "This may be a private channel / group. "
            "Make me an admin over there to index the files."
        )

    except (
        UsernameInvalid,
        UsernameNotModified
    ):

        return await vj.reply(
            "Invalid Link specified."
        )

    except Exception as e:

        logger.exception(e)

        return await vj.reply(
            f"Errors - {e}"
        )

    # =====================================================
    # CHECK LAST MESSAGE
    # =====================================================

    try:

        k = await bot.get_messages(
            chat_id,
            last_msg_id
        )

    except Exception:

        return await message.reply(
            "Make Sure That Iam An Admin In The Channel, "
            "if channel is private"
        )

    if k.empty:

        return await message.reply(
            "This may be group and Iam not a admin of the group."
        )

    # =====================================================
    # ADMIN
    # =====================================================

    if message.from_user.id in ADMINS:

        buttons = [
            [
                InlineKeyboardButton(
                    "Yes",
                    callback_data=(
                        f"index#accept#"
                        f"{chat_id}#"
                        f"{last_msg_id}#"
                        f"{message.from_user.id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    "Close",
                    callback_data="close_data"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(
            buttons
        )

        return await message.reply(
            f"Do you Want To Index This Channel/Group?\n\n"

            f"Chat ID/Username: "
            f"<code>{chat_id}</code>\n"

            f"Last Message ID: "
            f"<code>{last_msg_id}</code>",

            reply_markup=reply_markup
        )

    # =====================================================
    # NON ADMIN
    # =====================================================

    if type(chat_id) is int:

        try:

            link = (
                await bot.create_chat_invite_link(
                    chat_id
                )
            ).invite_link

        except ChatAdminRequired:

            return await message.reply(
                "Make sure I am an admin in the chat "
                "and have permission to invite users."
            )

    else:

        link = (
            f"@{message.forward_from_chat.username}"
        )

    buttons = [
        [
            InlineKeyboardButton(
                "Accept Index",
                callback_data=(
                    f"index#accept#"
                    f"{chat_id}#"
                    f"{last_msg_id}#"
                    f"{message.from_user.id}"
                )
            )
        ],
        [
            InlineKeyboardButton(
                "Reject Index",
                callback_data=(
                    f"index#reject#"
                    f"{chat_id}#"
                    f"{message.id}#"
                    f"{message.from_user.id}"
                )
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(
        buttons
    )

    await bot.send_message(
        LOG_CHANNEL,

        f"#IndexRequest\n\n"

        f"By : {message.from_user.mention} "
        f"(<code>{message.from_user.id}</code>)\n"

        f"Chat ID/Username - "
        f"<code>{chat_id}</code>\n"

        f"Last Message ID - "
        f"<code>{last_msg_id}</code>\n"

        f"InviteLink - {link}",

        reply_markup=reply_markup
    )

    await message.reply(
        "ThankYou For the Contribution, "
        "Wait For My Moderators to verify the files."
    )


# =========================================================
# /SETSKIP
# =========================================================

@Client.on_message(
    filters.command('setskip') &
    filters.user(ADMINS)
)
async def set_skip_number(bot, message):

    if len(message.command) < 2:

        return await message.reply(
            "Give me a skip number.\n\n"
            "Example: `/setskip 100`"
        )

    try:

        skip = int(
            message.command[1]
        )

    except ValueError:

        return await message.reply(
            "Skip number should be an integer."
        )

    if skip < 0:

        return await message.reply(
            "Skip number cannot be negative."
        )

    temp.CURRENT = skip

    await message.reply(
        f"Successfully set SKIP number as "
        f"<code>{skip}</code>"
    )


# =========================================================
# INDEX FILES TO DATABASE
# =========================================================

async def index_files_to_db(
    lst_msg_id,
    chat,
    msg,
    bot
):

    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    processed = 0

    async with lock:

        try:

            # ------------------------------------------------
            # GET SKIP VALUE
            # ------------------------------------------------

            skip = int(
                getattr(
                    temp,
                    "CURRENT",
                    0
                ) or 0
            )

            # খুব গুরুত্বপূর্ণ:
            # এই skip value শুধু এই indexing-এ ব্যবহার হবে
            temp.CURRENT = 0

            temp.CANCEL = False

            logger.info(
                f"Starting indexing: "
                f"chat={chat}, "
                f"last_msg_id={lst_msg_id}, "
                f"skip={skip}"
            )

            # ------------------------------------------------
            # ITERATE MESSAGES
            # ------------------------------------------------

            async for message in bot.iter_messages(
                chat,
                offset_id=lst_msg_id,
                offset=skip
            ):

                # ============================================
                # CANCEL
                # ============================================

                if temp.CANCEL:

                    await msg.edit_text(

                        f"Indexing Cancelled! ❌\n\n"

                        f"Total Processed: "
                        f"<code>{processed}</code>\n"

                        f"Successfully Saved: "
                        f"<code>{total_files}</code>\n"

                        f"Duplicate Files: "
                        f"<code>{duplicate}</code>\n"

                        f"Deleted Messages: "
                        f"<code>{deleted}</code>\n"

                        f"Non-Media: "
                        f"<code>{no_media}</code>\n"

                        f"Unsupported Media: "
                        f"<code>{unsupported}</code>\n"

                        f"Errors: "
                        f"<code>{errors}</code>"
                    )

                    return

                processed += 1

                # ============================================
                # PROGRESS
                # ============================================

                if processed % 30 == 0:

                    buttons = [
                        [
                            InlineKeyboardButton(
                                "Cancel",
                                callback_data="index_cancel"
                            )
                        ]
                    ]

                    reply_markup = InlineKeyboardMarkup(
                        buttons
                    )

                    try:

                        await msg.edit_text(

                            text=(

                                f"📊 Indexing...\n\n"

                                f"Total Messages Processed: "
                                f"<code>{processed}</code>\n"

                                f"Successfully Saved: "
                                f"<code>{total_files}</code>\n"

                                f"Duplicate Files Skipped: "
                                f"<code>{duplicate}</code>\n"

                                f"Deleted Messages Skipped: "
                                f"<code>{deleted}</code>\n"

                                f"Non-Media Messages: "
                                f"<code>{no_media}</code>\n"

                                f"Unsupported Media: "
                                f"<code>{unsupported}</code>\n"

                                f"Errors: "
                                f"<code>{errors}</code>"
                            ),

                            reply_markup=reply_markup
                        )

                    except MessageNotModified:
                        pass

                    except Exception as e:

                        logger.warning(
                            f"Progress update failed: {e}"
                        )

                # ============================================
                # DELETED MESSAGE
                # ============================================

                if message.empty:

                    deleted += 1

                    continue

                # ============================================
                # NO MEDIA
                # ============================================

                if not message.media:

                    no_media += 1

                    continue

                # ============================================
                # SUPPORTED MEDIA CHECK
                # ============================================

                if message.media not in (

                    enums.MessageMediaType.VIDEO,

                    enums.MessageMediaType.AUDIO,

                    enums.MessageMediaType.DOCUMENT

                ):

                    unsupported += 1

                    continue

                # ============================================
                # GET MEDIA
                # ============================================

                media = getattr(
                    message,
                    message.media.value,
                    None
                )

                if not media:

                    unsupported += 1

                    continue

                # ============================================
                # ADD CAPTION
                # ============================================

                try:

                    media.caption = (
                        message.caption
                    )

                except Exception:

                    pass

                # ============================================
                # SAVE FILE
                # ============================================

                try:

                    saved, status = (
                        await save_file(media)
                    )

                    if saved:

                        total_files += 1

                    elif status == 0:

                        duplicate += 1

                    elif status == 3:

                        errors += 1

                    else:

                        errors += 1

                    # ========================================
                    # SAVE ERROR CONTINUES NEXT MESSAGE
                    # ========================================

                except FloodWait as e:

                    logger.warning(
                        f"FloodWait: {e.value} seconds"
                    )

                    await asyncio.sleep(
                        e.value
                    )

                    continue

                except Exception as e:

                    errors += 1

                    logger.exception(
                        f"Error saving message "
                        f"{message.id}: {e}"
                    )

                    continue

        # =====================================================
        # MAIN INDEX ERROR
        # =====================================================

        except FloodWait as e:

            logger.warning(
                f"Index FloodWait: "
                f"{e.value} seconds"
            )

            await asyncio.sleep(
                e.value
            )

            try:

                await msg.edit_text(
                    f"FloodWait occurred.\n"
                    f"Please start indexing again after "
                    f"{e.value} seconds."
                )

            except:
                pass

            return

        except Exception as e:

            logger.exception(
                f"Indexing Error: {e}"
            )

            try:

                await msg.edit_text(
                    f"Indexing Error ❌\n\n"
                    f"<code>{e}</code>"
                )

            except:
                pass

            try:

                await msg.reply_text(

                    f"Successfully Saved: "
                    f"<code>{total_files}</code>\n"

                    f"Duplicate Files Skipped: "
                    f"<code>{duplicate}</code>\n"

                    f"Deleted Messages Skipped: "
                    f"<code>{deleted}</code>\n"

                    f"Non-Media Messages: "
                    f"<code>{no_media}</code>\n"

                    f"Unsupported Media: "
                    f"<code>{unsupported}</code>\n"

                    f"Errors Occurred: "
                    f"<code>{errors}</code>"
                )

            except:
                pass

            return

        # =====================================================
        # FINAL RESULT
        # =====================================================

        try:

            await msg.edit_text(

                f"Indexing Completed Successfully! ✅\n\n"

                f"Total Messages Processed: "
                f"<code>{processed}</code>\n\n"

                f"Successfully Saved: "
                f"<code>{total_files}</code>\n"

                f"Duplicate Files Skipped: "
                f"<code>{duplicate}</code>\n"

                f"Deleted Messages Skipped: "
                f"<code>{deleted}</code>\n"

                f"Non-Media Messages: "
                f"<code>{no_media}</code>\n"

                f"Unsupported Media: "
                f"<code>{unsupported}</code>\n"

                f"Errors Occurred: "
                f"<code>{errors}</code>"
            )

        except Exception as e:

            logger.exception(
                f"Final message update error: {e}"
            )
