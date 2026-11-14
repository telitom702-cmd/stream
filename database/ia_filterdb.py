# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import re
import base64
import asyncio

from struct import pack

from pyrogram.file_id import FileId
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from info import (
    FILE_DB_URI,
    SEC_FILE_DB_URI,
    DATABASE_NAME,
    COLLECTION_NAME,
    MULTIPLE_DATABASE,
    USE_CAPTION_FILTER,
    MAX_B_TN
)


# =========================================================
# MONGODB CONNECTION
# =========================================================

client = MongoClient(
    FILE_DB_URI,
    maxPoolSize=50,
    minPoolSize=5,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    retryWrites=True
)

db = client[DATABASE_NAME]
col = db[COLLECTION_NAME]


sec_client = MongoClient(
    SEC_FILE_DB_URI,
    maxPoolSize=50,
    minPoolSize=5,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    retryWrites=True
)

sec_db = sec_client[DATABASE_NAME]
sec_col = sec_db[COLLECTION_NAME]


# =========================================================
# INDEXES
# =========================================================

try:
    col.create_index("file_id")
    col.create_index("file_unique_id")

    sec_col.create_index("file_id")
    sec_col.create_index("file_unique_id")

    print("MongoDB indexes are ready.")

except Exception as e:
    print(f"Index creation error: {e}")


# =========================================================
# SAVE FILE
# =========================================================

async def save_file(media):
    """
    Async wrapper.
    PyMongo is synchronous, so database work runs
    in a separate thread without blocking the bot.
    """
    return await asyncio.to_thread(_save_file_sync, media)


def _save_file_sync(media):

    try:
        file_id = unpack_new_file_id(media.file_id)

        file_unique_id = getattr(
            media,
            "file_unique_id",
            None
        )

        file_name = get_file_name(media)
        file_name = clean_file_name(file_name)

        if not file_name.strip():
            file_name = "Unknown File"

        new_file_name = f"@DramaZGroup {file_name}"

        file = {
            "file_id": file_id,
            "file_unique_id": file_unique_id,
            "file_name": new_file_name,
            "file_size": getattr(media, "file_size", 0),
            "caption": (
                media.caption.html
                if media.caption
                else None
            )
        }

        # -------------------------------------------------
        # CHECK PRIMARY DATABASE
        # -------------------------------------------------

        existing = find_existing_fast(
            col,
            file_id,
            file_unique_id
        )

        if existing:

            if existing.get("file_id") != file_id:

                col.update_one(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "file_id": file_id
                        }
                    }
                )

            return False, 0

        # -------------------------------------------------
        # CHECK SECONDARY DATABASE
        # -------------------------------------------------

        if MULTIPLE_DATABASE:

            existing = find_existing_fast(
                sec_col,
                file_id,
                file_unique_id
            )

            if existing:

                if existing.get("file_id") != file_id:

                    sec_col.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "file_id": file_id
                            }
                        }
                    )

                return False, 0

        # -------------------------------------------------
        # INSERT PRIMARY
        # -------------------------------------------------

        try:

            col.insert_one(file)

            print(
                f"Saved: {new_file_name}"
            )

            return True, 1

        except DuplicateKeyError:

            return False, 0

        except Exception as e:

            # ---------------------------------------------
            # SECONDARY DATABASE FALLBACK
            # ---------------------------------------------

            if MULTIPLE_DATABASE:

                try:

                    sec_col.insert_one(file)

                    print(
                        f"Saved in secondary DB: {new_file_name}"
                    )

                    return True, 1

                except DuplicateKeyError:

                    return False, 0

                except Exception as sec_error:

                    print(
                        f"Secondary DB Error: {sec_error}"
                    )

                    return False, 3

            print(
                f"Database Error: {e}"
            )

            return False, 3

    except Exception as e:

        print(
            f"Save File Error: {e}"
        )

        return False, 3


# =========================================================
# FAST DUPLICATE CHECK
# =========================================================

def find_existing_fast(
    collection,
    file_id,
    file_unique_id
):

    conditions = []

    if file_unique_id:

        conditions.append({
            "file_unique_id": file_unique_id
        })

    conditions.append({
        "file_id": file_id
    })

    if not conditions:
        return None

    try:

        if len(conditions) == 1:

            return collection.find_one(
                conditions[0],
                {
                    "_id": 1,
                    "file_id": 1
                }
            )

        return collection.find_one(
            {
                "$or": conditions
            },
            {
                "_id": 1,
                "file_id": 1
            }
        )

    except Exception as e:

        print(
            f"Duplicate check error: {e}"
        )

        return None


# =========================================================
# GET FILE NAME
# =========================================================

def get_file_name(media):

    # First priority: Caption
    if getattr(media, "caption", None):

        try:

            caption = (
                media.caption.html
                or str(media.caption)
            )

        except Exception:

            caption = str(media.caption)

        caption = re.sub(
            r"<[^>]+>",
            " ",
            caption
        )

        caption = re.sub(
            r"\s+",
            " ",
            caption
        ).strip()

        if caption:

            return caption

    # Second priority: Telegram filename
    original_name = getattr(
        media,
        "file_name",
        None
    )

    if original_name:

        original_name = str(
            original_name
        ).strip()

        if original_name:

            return original_name

    return "Unknown File"


# =========================================================
# CLEAN FILE NAME
# =========================================================

def clean_file_name(file_name):

    if not file_name:

        return "Unknown File"

    file_name = str(
        file_name
    ).strip()

    # Remove HTML
    file_name = re.sub(
        r"<[^>]+>",
        " ",
        file_name
    )

    # HTML entities
    file_name = re.sub(
        r"&nbsp;",
        " ",
        file_name,
        flags=re.IGNORECASE
    )

    file_name = re.sub(
        r"&amp;",
        "&",
        file_name,
        flags=re.IGNORECASE
    )

    # Replace separators
    file_name = re.sub(
        r"[_\-.+]",
        " ",
        file_name
    )

    # Remove brackets
    file_name = re.sub(
        r"[\[\]\(\)\{\}]",
        "",
        file_name
    )

    words = []

    for word in file_name.split():

        lower_word = word.lower()

        if lower_word.startswith("@"):
            continue

        if lower_word.startswith("http"):
            continue

        if lower_word.startswith("www."):
            continue

        if lower_word.startswith("t.me"):
            continue

        words.append(word)

    file_name = " ".join(words)

    file_name = add_space_between_e_and_number(
        file_name
    )

    file_name = re.sub(
        r"\s+",
        " ",
        file_name
    ).strip()

    return (
        file_name
        if file_name
        else "Unknown File"
    )


# =========================================================
# ADD SPACE e.g. E01 -> E 01
# =========================================================

def add_space_between_e_and_number(
    input_string
):

    return re.sub(
        r"([eE])([0-9])",
        r"\1 \2",
        input_string
    )


# =========================================================
# UPDATE EXISTING FILE
# =========================================================

def update_existing_file(
    file_id,
    file_unique_id
):

    search_conditions = []

    if file_unique_id:

        search_conditions.append({
            "file_unique_id": file_unique_id
        })

    search_conditions.append({
        "file_id": file_id
    })

    for collection in (
        col,
        sec_col
    ):

        for condition in search_conditions:

            existing = collection.find_one(
                condition,
                {
                    "_id": 1
                }
            )

            if existing:

                collection.update_one(
                    {
                        "_id": existing["_id"]
                    },
                    {
                        "$set": {
                            "file_id": file_id
                        }
                    }
                )

                print(
                    "Existing file ID updated successfully."
                )

                return True

    return False


# =========================================================
# SEARCH RESULTS
# =========================================================

async def get_search_results(
    chat_id,
    query,
    file_type=None,
    max_results=10,
    offset=0,
    filter=False
):

    return await asyncio.to_thread(
        _get_search_results_sync,
        query,
        max_results,
        offset
    )


def _get_search_results_sync(
    query,
    max_results=10,
    offset=0
):

    query = query.strip()

    if not query:

        raw_pattern = r"."

    elif " " not in query:

        escaped_query = re.escape(
            query
        )

        raw_pattern = (
            rf"(\b|[\.\+\-_])"
            rf"{escaped_query}"
            rf"(\b|[\.\+\-_])"
        )

    else:

        words = [
            re.escape(x)
            for x in query.split()
        ]

        raw_pattern = (
            r".*[\s\.\+\-_]+"
            .join(words)
        )

    try:

        regex = re.compile(
            raw_pattern,
            flags=re.IGNORECASE
        )

    except re.error:

        regex = re.compile(
            re.escape(query),
            flags=re.IGNORECASE
        )

    search_filter = {
        "file_name": regex
    }

    files = []

    # -----------------------------------------------------
    # PRIMARY
    # -----------------------------------------------------

    cursor = (
        col.find(search_filter)
        .sort("$natural", -1)
        .skip(offset)
        .limit(max_results)
    )

    files.extend(
        list(cursor)
    )

    # -----------------------------------------------------
    # SECONDARY
    # -----------------------------------------------------

    if MULTIPLE_DATABASE:

        cursor = (
            sec_col.find(search_filter)
            .sort("$natural", -1)
            .skip(offset)
            .limit(max_results)
        )

        files.extend(
            list(cursor)
        )

    # -----------------------------------------------------
    # COUNT
    # -----------------------------------------------------

    total_results = col.count_documents(
        search_filter
    )

    if MULTIPLE_DATABASE:

        total_results += sec_col.count_documents(
            search_filter
        )

    # -----------------------------------------------------
    # NEXT OFFSET
    # -----------------------------------------------------

    if (
        offset + max_results
    ) >= total_results:

        next_offset = ""

    else:

        next_offset = (
            offset + max_results
        )

    return (
        files,
        next_offset,
        total_results
    )


# =========================================================
# BAD FILE SEARCH
# =========================================================

async def get_bad_files(
    query,
    file_type=None,
    use_filter=False
):

    return await asyncio.to_thread(
        _get_bad_files_sync,
        query
    )


def _get_bad_files_sync(query):

    query = query.strip()

    if not query:

        raw_pattern = r"."

    elif " " not in query:

        escaped_query = re.escape(
            query
        )

        raw_pattern = (
            rf"(\b|[\.\+\-_])"
            rf"{escaped_query}"
            rf"(\b|[\.\+\-_])"
        )

    else:

        words = [
            re.escape(x)
            for x in query.split()
        ]

        raw_pattern = (
            r".*[\s\.\+\-_]+"
            .join(words)
        )

    try:

        regex = re.compile(
            raw_pattern,
            flags=re.IGNORECASE
        )

    except re.error:

        return [], 0

    filter_criteria = {
        "file_name": regex
    }

    if USE_CAPTION_FILTER:

        filter_criteria = {
            "$or": [
                {
                    "file_name": regex
                },
                {
                    "caption": regex
                }
            ]
        }

    files = list(
        col.find(filter_criteria)
    )

    total_results = len(files)

    if MULTIPLE_DATABASE:

        sec_files = list(
            sec_col.find(filter_criteria)
        )

        files.extend(
            sec_files
        )

        total_results += len(
            sec_files
        )

    return (
        files,
        total_results
    )


# =========================================================
# GET FILE DETAILS
# =========================================================

async def get_file_details(query):

    return await asyncio.to_thread(
        _get_file_details_sync,
        query
    )


def _get_file_details_sync(query):

    file = col.find_one({
        "file_id": query
    })

    if file:

        return file

    if MULTIPLE_DATABASE:

        return sec_col.find_one({
            "file_id": query
        })

    return None


# =========================================================
# ENCODE FILE ID
# =========================================================

def encode_file_id(
    s: bytes
) -> str:

    r = b""
    n = 0

    for i in (
        s + bytes([22]) + bytes([4])
    ):

        if i == 0:

            n += 1

        else:

            if n:

                r += (
                    b"\x00"
                    + bytes([n])
                )

                n = 0

            r += bytes([i])

    return (
        base64.urlsafe_b64encode(r)
        .decode()
        .rstrip("=")
    )


# =========================================================
# UNPACK FILE ID
# =========================================================

def unpack_new_file_id(
    new_file_id
):

    decoded = FileId.decode(
        new_file_id
    )

    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )

    return file_id
