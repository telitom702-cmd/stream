# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import os
import re
from html import unescape
from pyrogram import Client
from typing import Any, Optional
from pyrogram.types import Message
from pyrogram.file_id import FileId
from pyrogram.raw.types.messages import Messages
from TechVJ.server.exceptions import FIleNotFound


KNOWN_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".webm", ".flv", ".m4v", ".ts", ".wmv", ".3gp", ".mpg", ".mpeg",
    ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus",
    ".zip", ".rar", ".7z", ".pdf", ".srt", ".ass", ".apk", ".iso",
}


def build_display_name(caption, original_name=""):
    """
    Stream / Download / Watch এ দেখানোর নাম।
    ক্যাপশন থাকলে ক্যাপশন (যেমন: "Dude (2025) WEB-DL ... .mkv"), না থাকলে ফাইলের আসল নাম।
    ক্যাপশনে এক্সটেনশন না থাকলে আসল ফাইলের এক্সটেনশন জুড়ে দেওয়া হয়।
    """
    original_name = original_name or ""
    text = unescape(re.sub(r"<[^>]+>", "", str(caption or "")))
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = text.replace("/", " ").replace("\\", " ").replace('"', "'")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return original_name

    ext = os.path.splitext(original_name)[1]
    has_known_ext = os.path.splitext(text)[1].lower() in KNOWN_EXTENSIONS
    if ext and not has_known_ext and not text.lower().endswith(ext.lower()):
        text += ext

    if len(text) > 200:  # নাম খুব বড় হলে ছেঁটে এক্সটেনশন রেখে দেওয়া
        cur_ext = os.path.splitext(text)[1] if len(os.path.splitext(text)[1]) <= 6 else ""
        text = text[:200 - len(cur_ext)].rstrip() + cur_ext
    return text


async def parse_file_id(message: "Message") -> Optional[FileId]:
    media = get_media_from_message(message)
    if media:
        return FileId.decode(media.file_id)

async def parse_file_unique_id(message: "Messages") -> Optional[str]:
    media = get_media_from_message(message)
    if media:
        return media.file_unique_id

async def get_file_ids(client: Client, chat_id: int, id: int) -> Optional[FileId]:
    message = await client.get_messages(chat_id, id)
    if message.empty:
        raise FIleNotFound
    media = get_media_from_message(message)
    file_unique_id = await parse_file_unique_id(message)
    file_id = await parse_file_id(message)
    setattr(file_id, "file_size", getattr(media, "file_size", 0))
    setattr(file_id, "mime_type", getattr(media, "mime_type", ""))
    setattr(
        file_id,
        "file_name",
        build_display_name(getattr(message, "caption", None), getattr(media, "file_name", ""))
    )
    setattr(file_id, "unique_id", file_unique_id)
    return file_id

def get_media_from_message(message: "Message") -> Any:
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )
    for attr in media_types:
        media = getattr(message, attr, None)
        if media:
            return media


def get_hash(media_msg: Message) -> str:
    media = get_media_from_message(media_msg)
    return getattr(media, "file_unique_id", "")[:6]

def get_name(media_msg: Message) -> str:
    media = get_media_from_message(media_msg)
    return build_display_name(
        getattr(media_msg, "caption", None),
        getattr(media, 'file_name', "") or ""
    )

def get_media_file_size(m):
    media = get_media_from_message(m)
    return getattr(media, "file_size", 0)

