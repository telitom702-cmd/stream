import re
import base64
import asyncio
import logging

from collections import defaultdict
from datetime import datetime, timedelta
from struct import pack
from typing import List, Dict

from pyrogram.file_id import FileId

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from umongo import Document, Instance, fields
from marshmallow import ValidationError

from info import (
    FILE_DB_URI,
    SEC_FILE_DB_URI,
    DATABASE_NAME,
    COLLECTION_NAME,
    MULTIPLE_DATABASE,
    USE_CAPTION_FILTER,
    MAX_B_TN,
)

try:
    from info import INDEX_CAPTION
except ImportError:
    INDEX_CAPTION = USE_CAPTION_FILTER

try:
    from info import ULTRA_FAST_MODE
except ImportError:
    ULTRA_FAST_MODE = False

try:
    from utils import get_settings, save_group_settings
except ImportError:
    get_settings = None
    save_group_settings = None


logger = logging.getLogger(__name__)


# =========================================================
# DATABASE CLIENTS
# =========================================================

# Primary File Database
client = AsyncIOMotorClient(
    FILE_DB_URI,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
)

db = client[DATABASE_NAME]


# Secondary File Database
# Only used when MULTIPLE_DATABASE=True
if MULTIPLE_DATABASE and SEC_FILE_DB_URI:
    client2 = AsyncIOMotorClient(
        SEC_FILE_DB_URI,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
    )
    db2 = client2[DATABASE_NAME]
else:
    client2 = None
    db2 = None


# =========================================================
# UMONGO INSTANCES
# =========================================================

instance = Instance.from_db(db)

if db2 is not None:
    instance2 = Instance.from_db(db2)
else:
    instance2 = None


# =========================================================
# PRIMARY MEDIA MODEL
# =========================================================

@instance.register
class Media(Document):

    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    send_file_id = fields.StrField(allow_none=True)

    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)

    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)

    caption = fields.StrField(allow_none=True)

    class Meta:
        collection_name = COLLECTION_NAME
        indexes = (
            {
                "fields": ["file_name"],
            },
        )


# =========================================================
# SECONDARY MEDIA MODEL
# =========================================================

if instance2 is not None:

    @instance2.register
    class Media2(Document):

        file_id = fields.StrField(attribute="_id")
        file_ref = fields.StrField(allow_none=True)
        send_file_id = fields.StrField(allow_none=True)

        file_name = fields.StrField(required=True)
        file_size = fields.IntField(required=True)

        file_type = fields.StrField(allow_none=True)
        mime_type = fields.StrField(allow_none=True)

        caption = fields.StrField(allow_none=True)

        class Meta:
            collection_name = COLLECTION_NAME
            indexes = (
                {
                    "fields": ["file_name"],
                },
            )

else:
    Media2 = None


# =========================================================
# DATABASE SIZE CACHE
# =========================================================

_db_stats_cache = {
    "primary": {
        "timestamp": None,
        "size_mb": 0.0,
    },
    "secondary": {
        "timestamp": None,
        "size_mb": 0.0,
    },
}


# =========================================================
# DATABASE SIZE
# =========================================================

async def check_db_size(database):

    if database is None:
        return 0.0

    cache_key = "primary"

    if database is db2:
        cache_key = "secondary"

    cache = _db_stats_cache[cache_key]

    try:

        now = datetime.utcnow()

        if (
            cache["timestamp"] is not None
            and now - cache["timestamp"] < timedelta(minutes=10)
        ):
            return cache["size_mb"]

        stats = await database.command("dbstats")

        data_size = stats.get("dataSize", 0)
        index_size = stats.get("indexSize", 0)

        total_bytes = data_size + index_size

        size_mb = total_bytes / (1024 * 1024)

        cache["size_mb"] = size_mb
        cache["timestamp"] = now

        return size_mb

    except Exception as e:

        logger.error(
            f"Error checking database size: {e}"
        )

        return 0.0


# =========================================================
# FILE ID HELPERS
# =========================================================

def encode_file_id(data: bytes) -> str:

    result = b""
    zero_count = 0

    for value in data + bytes([22]) + bytes([4]):

        if value == 0:

            zero_count += 1

        else:

            if zero_count:
                result += b"\x00" + bytes([zero_count])
                zero_count = 0

            result += bytes([value])

    return base64.urlsafe_b64encode(
        result
    ).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:

    return base64.urlsafe_b64encode(
        file_ref
    ).decode().rstrip("=")


def unpack_new_file_id(new_file_id):

    decoded = FileId.decode(new_file_id)

    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash,
        )
    )

    file_ref = encode_file_ref(
        decoded.file_reference
    )

    return file_id, file_ref


# =========================================================
# FILE NAME HELPERS
# =========================================================

def clean_file_name(file_name):

    if not file_name:
        return "Unknown File"

    file_name = str(file_name)

    file_name = re.sub(
        r"[_\-\.#+$%^&*()!~`,;:\"'?/<>\[\]{}=|\\]",
        " ",
        file_name,
    )

    file_name = re.sub(
        r"\s+",
        " ",
        file_name,
    ).strip()

    return file_name or "Unknown File"


def get_media_caption(media):

    if not getattr(media, "caption", None):
        return None

    try:
        return media.caption.html.strip()

    except Exception:

        try:
            return str(media.caption).strip()

        except Exception:
            return None


# =========================================================
# SEARCH FILTER
# =========================================================

def _build_search_filter(query, file_type=None):

    if isinstance(query, list):

        values = [
            str(item).strip()
            for item in query
            if item and str(item).strip()
        ]

        if not values:
            return None

        pattern = "|".join(
            re.escape(item)
            for item in values
        )

    else:

        query = str(query or "").strip()

        if not query:
            return None

        words = [
            re.escape(word)
            for word in query.split()
            if word
        ]

        if not words:
            return None

        pattern = r".*".join(words)

    try:
        regex = re.compile(
            pattern,
            re.IGNORECASE,
        )

    except re.error:
        return None

    if USE_CAPTION_FILTER:

        mongo_filter = {
            "$or": [
                {"file_name": regex},
                {"caption": regex},
            ]
        }

    else:

        mongo_filter = {
            "file_name": regex
        }

    if file_type:
        mongo_filter["file_type"] = file_type

    return mongo_filter


# =========================================================
# EPISODE HELPERS
# =========================================================

def is_episode_query(query):

    if isinstance(query, list):
        query = " ".join(map(str, query))

    query = str(query or "")

    return bool(
        re.search(
            r"\b(?:e|ep|episode)\s*\d+\b",
            query,
            re.IGNORECASE,
        )
    )


def episode_sort_key(file):

    file_name = getattr(
        file,
        "file_name",
        "",
    )

    season = 0
    episode = 0

    season_match = re.search(
        r"\b(?:s|season)\s*(\d+)\b",
        file_name,
        re.IGNORECASE,
    )

    episode_match = re.search(
        r"\b(?:e|ep|episode)\s*(\d+)\b",
        file_name,
        re.IGNORECASE,
    )

    if season_match:
        season = int(season_match.group(1))

    if episode_match:
        episode = int(episode_match.group(1))

    if episode:
        return 0, season, episode, file_name.lower()

    return 1, season, episode, file_name.lower()


def order_episode_page(
    files,
    offset,
    max_results,
):

    ordered = sorted(
        files,
        key=episode_sort_key,
    )

    total = len(ordered)

    page = ordered[
        offset:offset + max_results
    ]

    next_offset = (
        offset + len(page)
        if offset + len(page) < total
        else ""
    )

    return (
        page,
        False,
        total,
    )


# =========================================================
# SAVE FILE
# =========================================================

async def save_file(media):

    try:

        # -------------------------------------------------
        # Decode Telegram file ID
        # -------------------------------------------------

        file_id, file_ref = unpack_new_file_id(
            media.file_id
        )

        # -------------------------------------------------
        # Caption
        # -------------------------------------------------

        caption_text = None

        if (
            getattr(media, "caption", None)
            and INDEX_CAPTION
        ):
            caption_text = get_media_caption(media)

        # -------------------------------------------------
        # Original file name
        # -------------------------------------------------

        original_file_name = getattr(
            media,
            "file_name",
            None,
        )

        # -------------------------------------------------
        # Caption priority
        # -------------------------------------------------

        if caption_text:

            raw_file_name = caption_text

            logger.info(
                f"[NAME SOURCE] Caption used: "
                f"{caption_text}"
            )

        elif original_file_name:

            raw_file_name = original_file_name

            logger.info(
                f"[NAME SOURCE] Original file name used: "
                f"{original_file_name}"
            )

        else:

            raw_file_name = "Unknown File"

            logger.warning(
                "[NAME SOURCE] No caption or file name."
            )

        # -------------------------------------------------
        # Clean file name
        # -------------------------------------------------

        file_name = clean_file_name(
            raw_file_name
        )

        # -------------------------------------------------
        # Select model
        # -------------------------------------------------

        save_model = Media
        target_db = "Primary"

        # -------------------------------------------------
        # Check duplicate in primary
        # -------------------------------------------------

        try:

            existing = await Media.find_one(
                {
                    "_id": file_id
                }
            )

            if existing:

                await db[
                    COLLECTION_NAME
                ].update_one(
                    {
                        "_id": file_id
                    },
                    {
                        "$set": {
                            "file_ref": file_ref,
                            "send_file_id": media.file_id,
                        }
                    },
                )

                logger.info(
                    f"[REFRESH] Existing file updated: "
                    f"{file_name}"
                )

                return False, 0

        except Exception as e:

            logger.error(
                f"Primary duplicate check failed: {e}"
            )

            return False, 3

        # -------------------------------------------------
        # Check duplicate in secondary
        # -------------------------------------------------

        if MULTIPLE_DATABASE and Media2 is not None:

            try:

                existing = await Media2.find_one(
                    {
                        "_id": file_id
                    }
                )

                if existing:

                    await db2[
                        COLLECTION_NAME
                    ].update_one(
                        {
                            "_id": file_id
                        },
                        {
                            "$set": {
                                "file_ref": file_ref,
                                "send_file_id": media.file_id,
                            }
                        },
                    )

                    logger.info(
                        f"[REFRESH] Existing file updated "
                        f"in Secondary DB: {file_name}"
                    )

                    return False, 0

            except Exception as e:

                logger.error(
                    f"Secondary duplicate check failed: {e}"
                )

                return False, 3

        # -------------------------------------------------
        # Select DB by size
        # -------------------------------------------------

        if (
            MULTIPLE_DATABASE
            and Media2 is not None
            and db2 is not None
        ):

            primary_size = await check_db_size(db)

            # Keep the existing 407 MB threshold
            if primary_size >= 407:

                save_model = Media2
                target_db = "Secondary"

                logger.warning(
                    f"Primary DB size is "
                    f"{primary_size:.2f} MB. "
                    f"Switching to Secondary DB."
                )

        # -------------------------------------------------
        # Create record
        # -------------------------------------------------

        record = save_model(
            file_id=file_id,
            file_ref=file_ref,
            send_file_id=media.file_id,
            file_name=file_name,
            file_size=getattr(
                media,
                "file_size",
                0,
            ),
            file_type=getattr(
                media,
                "file_type",
                None,
            ),
            mime_type=getattr(
                media,
                "mime_type",
                None,
            ),
            caption=(
                caption_text
                if (
                    caption_text
                    and INDEX_CAPTION
                )
                else None
            ),
        )

        # -------------------------------------------------
        # Commit
        # -------------------------------------------------

        try:

            await record.commit()

        except DuplicateKeyError:

            database = (
                db2
                if target_db == "Secondary"
                else db
            )

            await database[
                COLLECTION_NAME
            ].update_one(
                {
                    "_id": file_id
                },
                {
                    "$set": {
                        "file_ref": file_ref,
                        "send_file_id": media.file_id,
                    }
                },
            )

            logger.info(
                f"[REFRESH] Duplicate file refreshed "
                f"in {target_db} DB: {file_name}"
            )

            return False, 0

        logger.info(
            f"[SUCCESS] '{file_name}' "
            f"saved to {target_db} DB."
        )

        return True, 1

    except ValidationError as e:

        logger.exception(
            f"[VALIDATION ERROR] {e}"
        )

        return False, 2

    except Exception as e:

        logger.exception(
            f"[SAVE ERROR] Could not save file: {e}"
        )

        return False, 3


# =========================================================
# SEARCH RESULTS
# =========================================================

async def get_search_results(
    chat_id,
    query,
    file_type=None,
    max_results=None,
    offset=0,
    filter=False,
):

    # -----------------------------------------------------
    # Get max button setting
    # -----------------------------------------------------

    if (
        chat_id is not None
        and get_settings is not None
    ):

        try:

            settings = await get_settings(
                int(chat_id)
            )

            if max_results is None:

                try:

                    max_results = (
                        10
                        if settings.get("max_btn")
                        else int(MAX_B_TN)
                    )

                except Exception:

                    max_results = int(
                        MAX_B_TN
                    )

        except Exception:

            max_results = (
                max_results
                or int(MAX_B_TN)
            )

    if max_results is None:
        max_results = int(MAX_B_TN)

    # -----------------------------------------------------
    # Build filter
    # -----------------------------------------------------

    mongo_filter = _build_search_filter(
        query,
        file_type=file_type,
    )

    if mongo_filter is None:
        return [], None, 0

    # -----------------------------------------------------
    # Fast mode
    # -----------------------------------------------------

    if ULTRA_FAST_MODE:

        limit = max_results + 1

        tasks = [
            Media.find(
                mongo_filter
            )
            .sort(
                "$natural",
                -1,
            )
            .skip(offset)
            .limit(limit)
            .to_list(
                length=limit
            )
        ]

        if (
            MULTIPLE_DATABASE
            and Media2 is not None
        ):

            tasks.append(
                Media2.find(
                    mongo_filter
                )
                .sort(
                    "$natural",
                    -1,
                )
                .skip(offset)
                .limit(limit)
                .to_list(
                    length=limit
                )
            )

        results = await asyncio.gather(
            *tasks
        )

        files = list(results[0])

        if len(results) > 1:
            files.extend(results[1])

        files = files[:limit]

        has_next = (
            len(files) > max_results
        )

        if has_next:
            files = files[:-1]

        next_offset = (
            offset + len(files)
            if has_next
            else ""
        )

        total_results = (
            offset
            + len(files)
            + (1 if has_next else 0)
        )

    # -----------------------------------------------------
    # Normal mode
    # -----------------------------------------------------

    else:

        count_tasks = [
            Media.count_documents(
                mongo_filter
            )
        ]

        find_tasks = [
            Media.find(
                mongo_filter
            )
            .sort(
                "$natural",
                -1,
            )
            .skip(offset)
            .limit(max_results)
            .to_list(
                length=max_results
            )
        ]

        if (
            MULTIPLE_DATABASE
            and Media2 is not None
        ):

            count_tasks.append(
                Media2.count_documents(
                    mongo_filter
                )
            )

            find_tasks.append(
                Media2.find(
                    mongo_filter
                )
                .sort(
                    "$natural",
                    -1,
                )
                .skip(offset)
                .limit(max_results)
                .to_list(
                    length=max_results
                )
            )

        count_results = await asyncio.gather(
            *count_tasks
        )

        find_results = await asyncio.gather(
            *find_tasks
        )

        total_results = sum(
            count_results
        )

        files = list(
            find_results[0]
        )

        if len(find_results) > 1:
            files.extend(
                find_results[1]
            )

        files = files[:max_results]

        next_offset = (
            offset + len(files)
            if offset + len(files)
            < total_results
            else ""
        )

    # -----------------------------------------------------
    # Episode sorting
    # -----------------------------------------------------

    if (
        max_results
        and (
            is_episode_query(query)
            or any(
                episode_sort_key(file)[0] == 0
                for file in files
            )
        )
    ):

        try:

            all_files, too_many = (
                await get_all_search_results(
                    chat_id,
                    query,
                    file_type=file_type,
                    max_results=None
                    if is_episode_query(query)
                    else 5000,
                )
            )

            if not too_many:

                (
                    files,
                    next_offset,
                    total_results,
                ) = order_episode_page(
                    all_files,
                    offset,
                    max_results,
                )

        except Exception as e:

            logger.exception(
                f"Episode sorting failed: {e}"
            )

    return (
        files,
        next_offset,
        total_results,
    )


# =========================================================
# GET ALL SEARCH RESULTS
# =========================================================

async def get_all_search_results(
    chat_id,
    query,
    file_type=None,
    max_results=1000,
):

    mongo_filter = _build_search_filter(
        query,
        file_type=file_type,
    )

    if mongo_filter is None:
        return [], False

    models = [Media]

    if (
        MULTIPLE_DATABASE
        and Media2 is not None
    ):
        models.append(Media2)

    async def fetch_source(model):

        cursor = model.find(
            mongo_filter
        )

        if max_results is None:

            return await cursor.to_list(
                length=None
            )

        return await cursor.limit(
            max_results + 1
        ).to_list(
            length=max_results + 1
        )

    results = await asyncio.gather(
        *(
            fetch_source(model)
            for model in models
        )
    )

    files = []

    for result in results:
        files.extend(result)

    if max_results is None:
        return files, False

    too_many = (
        len(files) > max_results
    )

    return (
        files[:max_results],
        too_many,
    )


# =========================================================
# GET BAD FILES
# =========================================================

async def get_bad_files(
    query,
    file_type=None,
):

    query = str(
        query or ""
    ).strip()

    if not query:

        raw_pattern = "."

    elif " " not in query:

        raw_pattern = (
            r"(\b|[\.\+\-_])"
            + re.escape(query)
            + r"(\b|[\.\+\-_])"
        )

    else:

        raw_pattern = query.replace(
            " ",
            r".*[\s\.\+\-_()]",
        )

    try:

        regex = re.compile(
            raw_pattern,
            re.IGNORECASE,
        )

    except re.error:

        return [], 0

    if USE_CAPTION_FILTER:

        mongo_filter = {
            "$or": [
                {
                    "file_name": regex
                },
                {
                    "caption": regex
                },
            ]
        }

    else:

        mongo_filter = {
            "file_name": regex
        }

    if file_type:
        mongo_filter[
            "file_type"
        ] = file_type

    tasks = [
        Media.find(
            mongo_filter
        )
        .sort(
            "$natural",
            -1,
        )
        .to_list(
            length=None
        )
    ]

    if (
        MULTIPLE_DATABASE
        and Media2 is not None
    ):

        tasks.append(
            Media2.find(
                mongo_filter
            )
            .sort(
                "$natural",
                -1,
            )
            .to_list(
                length=None
            )
        )

    results = await asyncio.gather(
        *tasks
    )

    files = []

    for result in results:
        files.extend(result)

    return (
        files,
        len(files),
    )


# =========================================================
# GET FILE DETAILS
# =========================================================

async def get_file_details(query):

    query = str(
        query
    ).strip()

    tasks = [
        Media.find_one(
            {
                "_id": query
            }
        )
    ]

    if (
        MULTIPLE_DATABASE
        and Media2 is not None
    ):

        tasks.append(
            Media2.find_one(
                {
                    "_id": query
                }
            )
        )

    results = await asyncio.gather(
        *tasks
    )

    for file_details in results:

        if file_details:
            return [file_details]

    return []


# =========================================================
# FETCH RECENT MEDIA
# =========================================================

async def dreamxbotz_fetch_media(
    limit: int
) -> List:

    try:

        model = Media

        if (
            MULTIPLE_DATABASE
            and Media2 is not None
        ):

            primary_size = await check_db_size(
                db
            )

            if primary_size >= 407:
                model = Media2

        cursor = (
            model.find()
            .sort(
                "$natural",
                -1,
            )
            .limit(limit)
        )

        return await cursor.to_list(
            length=limit
        )

    except Exception as e:

        logger.error(
            f"Error in dreamxbotz_fetch_media: {e}"
        )

        return []


# =========================================================
# CLEAN TITLE
# =========================================================

async def dreamxbotz_clean_title(
    filename: str,
    is_series: bool = False,
) -> str:

    try:

        filename = str(
            filename or ""
        )

        # -------------------------------------------------
        # Movie with year
        # -------------------------------------------------

        year_match = re.search(
            r"^(.*?)(\d{4}|\(\d{4}\))",
            filename,
            re.IGNORECASE,
        )

        if year_match:

            title = (
                year_match.group(1)
                + year_match.group(2)
            )

            title = (
                title
                .replace(
                    "(",
                    "",
                )
                .replace(
                    ")",
                    "",
                )
            )

            title = re.sub(
                r"[@._\-\[\]()]+",
                " ",
                title,
            )

            return (
                re.sub(
                    r"\s+",
                    " ",
                    title,
                )
                .strip()
                .title()
            )

        # -------------------------------------------------
        # Series
        # -------------------------------------------------

        if is_series:

            season_match = re.search(
                r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))",
                filename,
                re.IGNORECASE,
            )

            if season_match:

                title = (
                    season_match.group(1)
                    .strip()
                )

                season = (
                    season_match.group(2)
                    or season_match.group(3)
                    or season_match.group(4)
                )

                title = re.sub(
                    r"[@._\-\[\]()]+",
                    " ",
                    title,
                )

                title = re.sub(
                    r"\s+",
                    " ",
                    title,
                ).strip().title()

                return (
                    f"{title} "
                    f"S{int(season):02}"
                )

        # -------------------------------------------------
        # Normal title
        # -------------------------------------------------

        title = re.sub(
            r"[@._\-\[\]()]+",
            " ",
            filename,
        )

        title = re.sub(
            r"\s+",
            " ",
            title,
        )

        return (
            title
            .strip()
            .title()
        )

    except Exception as e:

        logger.error(
            f"Error in dreamxbotz_clean_title: {e}"
        )

        return filename


# =========================================================
# GET MOVIES
# =========================================================

async def dreamxbotz_get_movies(
    limit: int = 20
) -> List[str]:

    try:

        files = await dreamxbotz_fetch_media(
            limit * 2
        )

        results = set()

        series_pattern = (
            r"(?:s\d{1,2}|season\s*\d+|season\d+)"
            r"(?:\s*combined)?"
            r"(?:e\d{1,2}|episode\s*\d+)?\b"
        )

        for file in files:

            file_name = getattr(
                file,
                "file_name",
                "",
            )

            if not re.search(
                series_pattern,
                file_name,
                re.IGNORECASE,
            ):

                title = (
                    await dreamxbotz_clean_title(
                        file_name
                    )
                )

                if title:
                    results.add(title)

            if len(results) >= limit:
                break

        return sorted(
            results
        )[:limit]

    except Exception as e:

        logger.error(
            f"Error in dreamxbotz_get_movies: {e}"
        )

        return []


# =========================================================
# GET SERIES
# =========================================================

async def dreamxbotz_get_series(
    limit: int = 30
) -> Dict[str, List[int]]:

    try:

        files = await dreamxbotz_fetch_media(
            limit * 5
        )

        grouped = defaultdict(
            list
        )

        pattern = (
            r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))"
            r"(?:\s*Combined)?"
            r"(?:E(\d{1,2})|Episode\s*(\d+))?\b"
        )

        for file in files:

            file_name = getattr(
                file,
                "file_name",
                "",
            )

            match = re.search(
                pattern,
                file_name,
                re.IGNORECASE,
            )

            if match:

                title = (
                    await dreamxbotz_clean_title(
                        match.group(1),
                        is_series=True,
                    )
                )

                season = int(
                    match.group(2)
                    or match.group(3)
                    or match.group(4)
                )

                grouped[
                    title
                ].append(
                    season
                )

        return {
            title: sorted(
                set(seasons)
            )[:10]
            for title, seasons
            in grouped.items()
            if seasons
        }

    except Exception as e:

        logger.error(
            f"Error in dreamxbotz_get_series: {e}"
        )

        return {}
