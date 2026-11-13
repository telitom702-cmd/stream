# Don't Remove Credit @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import re, base64, json
from struct import pack
from pyrogram.file_id import FileId
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from info import FILE_DB_URI, SEC_FILE_DB_URI, DATABASE_NAME, COLLECTION_NAME, MULTIPLE_DATABASE, USE_CAPTION_FILTER, MAX_B_TN

# First Database For File Saving 
client = MongoClient(FILE_DB_URI)
db = client[DATABASE_NAME]
col = db[COLLECTION_NAME]

# Second Database For File Saving
sec_client = MongoClient(SEC_FILE_DB_URI)
sec_db = sec_client[DATABASE_NAME]
sec_col = sec_db[COLLECTION_NAME]


async def save_file(media):
    """Save file in the database."""

    file_id = unpack_new_file_id(media.file_id)

    # ==================================================
    # File Name Selection
    # Caption থাকলে Caption থেকে নাম নেওয়া হবে
    # Caption থেকে valid নাম না পাওয়া গেলে Original File Name
    # দুটোই না থাকলে Unknown File
    # ==================================================

    file_name = get_file_name(media)

    # File Name Clean করা
    file_name = clean_file_name(file_name)

    # Clean করার পর নাম খালি হলে fallback
    if not file_name.strip():
        file_name = "Unknown File"

    # Prefix
    new_file_name = f"@DramaZGroup {file_name}"

    file = {
        'file_id': file_id,
        'file_name': new_file_name,
        'file_size': media.file_size,
        'caption': media.caption.html if media.caption else None
    }

    # Saved name দিয়েই duplicate check
    if is_file_already_saved(file_id, new_file_name):
        return False, 0

    try:
        col.insert_one(file)
        print(f"{new_file_name} is successfully saved.")
        return True, 1

    except DuplicateKeyError:
        print(f"{new_file_name} is already saved.")
        return False, 0

    except:
        if MULTIPLE_DATABASE:
            try:
                sec_col.insert_one(file)
                print(f"{new_file_name} is successfully saved.")
                return True, 1

            except DuplicateKeyError:
                print(f"{new_file_name} is already saved.")
                return False, 0

        else:
            print(
                "Your Current File Database Is Full, "
                "Turn On Multiple Database Feature And Add Second File Mongodb To Save File."
            )


def get_file_name(media):
    """Get the best possible file name from caption or original file name."""

    # ---------------------------------------------
    # 1. Caption থেকে নাম নেওয়ার চেষ্টা
    # ---------------------------------------------
    if media.caption:
        caption = media.caption.html or str(media.caption)

        # HTML tag remove
        caption = re.sub(r'<[^>]+>', ' ', caption)

        # Multiple spaces remove
        caption = re.sub(r'\s+', ' ', caption).strip()

        # Caption থেকে usable text পাওয়া গেলে সেটাই filename
        if caption:
            return caption

    # ---------------------------------------------
    # 2. Original Telegram File Name
    # ---------------------------------------------
    original_name = getattr(media, "file_name", None)

    if original_name:
        original_name = str(original_name).strip()

        if original_name:
            return original_name

    # ---------------------------------------------
    # 3. Fallback
    # ---------------------------------------------
    return "Unknown File"


def clean_file_name(file_name):
    """Clean and format the file name."""

    if not file_name:
        return "Unknown File"

    file_name = str(file_name).strip()

    # HTML tag remove
    file_name = re.sub(r'<[^>]+>', ' ', file_name)

    # HTML entities clean
    file_name = re.sub(r'&nbsp;', ' ', file_name, flags=re.IGNORECASE)
    file_name = re.sub(r'&amp;', '&', file_name, flags=re.IGNORECASE)

    # Special characters replace
    file_name = re.sub(r"(_|\-|\.|\+)", " ", file_name)

    # Unwanted characters remove
    unwanted_chars = ['[', ']', '(', ')', '{', '}']

    for char in unwanted_chars:
        file_name = file_name.replace(char, '')

    # URL / Telegram username / link বাদ
    words = []

    for word in file_name.split():

        lower_word = word.lower()

        if lower_word.startswith('@'):
            continue

        if lower_word.startswith('http'):
            continue

        if lower_word.startswith('www.'):
            continue

        if lower_word.startswith('t.me'):
            continue

        words.append(word)

    file_name = ' '.join(words)

    # e01 / E01 → e 01
    file_name = add_space_between_e_and_number(file_name)

    # Multiple spaces clean
    file_name = re.sub(r'\s+', ' ', file_name).strip()

    return file_name if file_name else "Unknown File"


def add_space_between_e_and_number(input_string):
    # e01 / E01 → e 01
    output_string = re.sub(
        r'([eE])([0-9])',
        r'\1 \2',
        input_string
    )

    return output_string


def is_file_already_saved(file_id, file_name):
    """Check if the file is already saved in either collection."""

    found1 = {'file_name': file_name}
    found = {'file_id': file_id}

    for collection in [col, sec_col]:

        if collection.find_one(found1) or collection.find_one(found):
            print(f"{file_name} is already saved.")
            return True

    return False


async def get_search_results(chat_id, query, file_type=None, max_results=10, offset=0, filter=False):
    """For given query return (results, next_offset)"""

    query = query.strip()

    if not query:
        raw_pattern = '.'

    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'

    else:
        raw_pattern = query.replace(
            ' ',
            r'.*[\s\.\+\-_]'
        )

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)

    except:
        regex = query

    filter = {'file_name': regex}
    files = []

    if MULTIPLE_DATABASE:

        cursor1 = col.find(filter).sort(
            '$natural', -1
        ).skip(offset).limit(max_results)

        cursor2 = sec_col.find(filter).sort(
            '$natural', -1
        ).skip(offset).limit(max_results)

        for file in cursor1:
            files.append(file)

        for file in cursor2:
            files.append(file)

    else:

        cursor = col.find(filter).sort(
            '$natural', -1
        ).skip(offset).limit(max_results)

        for file in cursor:
            files.append(file)

    total_results = (
        col.count_documents(filter)
        if not MULTIPLE_DATABASE
        else (
            col.count_documents(filter)
            + sec_col.count_documents(filter)
        )
    )

    next_offset = (
        ""
        if (offset + max_results) >= total_results
        else (offset + max_results)
    )

    return files, next_offset, total_results


async def get_bad_files(query, file_type=None, use_filter=False):
    """For given query return (results, next_offset)"""

    query = query.strip()

    if not query:
        raw_pattern = '.'

    elif ' ' not in query:
        raw_pattern = rf'(\b|[.+-_]){query}(\b|[.+-_])'

    else:
        raw_pattern = query.replace(
            ' ',
            r'.*[s.+-_]'
        )

    try:
        regex = re.compile(
            raw_pattern,
            flags=re.IGNORECASE
        )

    except re.error:
        return [], 0

    filter_criteria = {
        'file_name': regex
    }

    if USE_CAPTION_FILTER:
        filter_criteria = {
            '$or': [
                filter_criteria,
                {'caption': regex}
            ]
        }

    def count_documents(collection):
        return collection.count_documents(
            filter_criteria
        )

    total_results = (
        count_documents(col) + count_documents(sec_col)
        if MULTIPLE_DATABASE
        else count_documents(col)
    )

    def find_documents(collection):
        return list(
            collection.find(filter_criteria)
        )

    files = (
        find_documents(col) + find_documents(sec_col)
        if MULTIPLE_DATABASE
        else find_documents(col)
    )

    return files, total_results


async def get_file_details(query):
    return (
        col.find_one({'file_id': query})
        or sec_col.find_one({'file_id': query})
    )


def encode_file_id(s: bytes) -> str:

    r = b""
    n = 0

    for i in s + bytes([22]) + bytes([4]):

        if i == 0:
            n += 1

        else:

            if n:
                r += b"\x00" + bytes([n])
                n = 0

            r += bytes([i])

    return base64.urlsafe_b64encode(
        r
    ).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    """Return file_id"""

    decoded = FileId.decode(new_file_id)

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
