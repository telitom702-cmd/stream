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

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------
# Global cache for DB size
# ---------------------------------------------------------

_db_stats_cache = {
    "timestamp": None,
    "primary_size": 0.0
}

# ---------------------------------------------------------
# Primary DB
# ---------------------------------------------------------

client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

# ---------------------------------------------------------
# Secondary DB
# ---------------------------------------------------------

client2 = AsyncIOMotorClient(DATABASE_URI2)
db2 = client2[DATABASE_NAME]
instance2 = Instance.from_db(db2)


# ---------------------------------------------------------
# Primary Media Model
# ---------------------------------------------------------

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
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME


# ---------------------------------------------------------
# Secondary Media Model
# ---------------------------------------------------------

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
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME


# ---------------------------------------------------------
# Check Database Size
# ---------------------------------------------------------

async def check_db_size(db):
    try:
        now = datetime.utcnow()

        cache_stale_by_time = (
            _db_stats_cache["timestamp"] is None
            or (
                now - _db_stats_cache["timestamp"]
                > timedelta(minutes=10)
            )
        )

        refresh_if_size_threshold = (
            _db_stats_cache["primary_size"] >= 10.0
        )

        if not cache_stale_by_time and not refresh_if_size_threshold:
            return _db_stats_cache["primary_size"]

        stats = await db.command("dbstats")

        db_logical_size = stats["dataSize"]
        db_index_size = stats["indexSize"]

        db_logical_size_mb = db_logical_size / (1024 * 1024)
        db_index_size_mb = db_index_size / (1024 * 1024)

        db_size_mb = db_logical_size_mb + db_index_size_mb

        _db_stats_cache["primary_size"] = db_size_mb
        _db_stats_cache["timestamp"] = now

        return db_size_mb

    except Exception as e:
        print(f"Error Checking Database Size: {e}")
        return 0


# ---------------------------------------------------------
# Save File
# Caption থাকলে Caption → File Name
# Caption না থাকলে Original File Name
# ---------------------------------------------------------

async def save_file(media):
    """Save file in database with caption-based file naming."""

    # -----------------------------------------------------
    # 1. Get file ID and file reference
    # -----------------------------------------------------

    file_id, file_ref = unpack_new_file_id(media.file_id)

    # -----------------------------------------------------
    # 2. Get Caption
    # -----------------------------------------------------

    caption_text = None

    if media.caption and INDEX_CAPTION:
        try:
            caption_text = media.caption.html.strip()
        except Exception:
            caption_text = str(media.caption).strip()

    # -----------------------------------------------------
    # 3. Get Original Telegram File Name
    # -----------------------------------------------------

    original_file_name = getattr(media, "file_name", None)

    # -----------------------------------------------------
    # 4. Caption Priority
    # -----------------------------------------------------

    if caption_text:
        raw_file_name = caption_text

        logger.info(
            f"[NAME SOURCE] Caption used: {caption_text}"
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
            "[NAME SOURCE] No caption or file name. "
            "Using Unknown File."
        )

    # -----------------------------------------------------
    # 5. Clean File Name
    # -----------------------------------------------------

    file_name = re.sub(
        r"[_\-\.#+$%^&*()!~`,;:\"'?/<>\[\]{}=|\\]",
        " ",
        str(raw_file_name)
    )

    file_name = re.sub(
        r"\s+",
        " ",
        file_name
    ).strip()

    if not file_name:
        file_name = "Unknown File"

    # -----------------------------------------------------
    # 6. Select Database
    # -----------------------------------------------------

    saveMedia = Media
    target_db = "Primary"

    # A stable, normalized file_id is used as the database key. Refresh the
    # sendable ID and file reference whenever the same media is indexed again.
    models_to_check = [Media, Media2] if MULTIPLE_DB else [Media]
    try:
        for existing_model in models_to_check:
            exists = await existing_model.count_documents(
                {"file_id": file_id},
                limit=1
            )
            if exists:
                await existing_model.collection.update_one(
                    {"_id": file_id},
                    {
                        "$set": {
                            "file_ref": file_ref,
                            "send_file_id": media.file_id,
                        }
                    }
                )
                logger.info(
                    f"[REFRESH] Updated Telegram file reference for "
                    f"'{file_name}'."
                )
                return False, 0
    except Exception:
        logger.exception(
            f"[ERROR] Could not check or refresh existing file '{file_name}'."
        )
        return False, 3

    if MULTIPLE_DB:
        try:
            primary_db_size = await check_db_size(db)

            if primary_db_size >= 407:
                saveMedia = Media2
                target_db = "Secondary"

                logger.warning(
                    "Switching to Secondary DB "
                    "due to size threshold."
                )

        except Exception as e:
            logger.error(
                "Error during MULTIPLE_DB check; "
                "defaulting to primary DB.",
                exc_info=e
            )

    # -----------------------------------------------------
    # 7. Create Database Record
    # -----------------------------------------------------

    try:
        record = saveMedia(
            file_id=file_id,
            file_ref=file_ref,
            send_file_id=media.file_id,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,

            # Original Caption আলাদাভাবে সেভ হবে
            caption=(
                media.caption.html
                if media.caption and INDEX_CAPTION
                else None
            ),
        )

    except ValidationError as e:
        logger.exception(
            f"[VALIDATION ERROR] '{file_name}' → {e}"
        )
        return False, 2

    # -----------------------------------------------------
    # 8. Commit to Database
    # -----------------------------------------------------

    try:
        await record.commit()

    except DuplicateKeyError:
        # Another indexing worker may have inserted this record after the
        # preflight check; refresh its current Telegram file ID as well.
        await saveMedia.collection.update_one(
            {"_id": file_id},
            {
                "$set": {
                    "file_ref": file_ref,
                    "send_file_id": media.file_id,
                }
            }
        )
        logger.info(
            f"[REFRESH] Updated Telegram file reference for "
            f"'{file_name}' in {target_db} DB."
        )
        return False, 0

    except Exception as e:
        logger.exception(
            f"[ERROR] Failed commit of "
            f"'{file_name}' to {target_db} DB.",
            exc_info=e
        )
        return False, 3

    logger.info(
        f"[SUCCESS] '{file_name}' saved to {target_db} DB."
    )

    return True, 1


# ---------------------------------------------------------
# Search Results
# ---------------------------------------------------------

def _build_search_filter(query, file_type=None):
    if isinstance(query, list):
        raw_pattern = "|".join(
            re.escape(item.strip())
            for item in query
            if item and item.strip()
        )
        if not raw_pattern:
            return None
        regex_list = [re.compile(raw_pattern, re.IGNORECASE)]
        if USE_CAPTION_FILTER:
            filter_mongo = {
                "$or": (
                    [{"file_name": regex} for regex in regex_list]
                    + [{"caption": regex} for regex in regex_list]
                )
            }
        else:
            filter_mongo = {"$or": [{"file_name": regex} for regex in regex_list]}
    else:
        query = (query or "").strip()
        if not query:
            return None

        words = [re.escape(word) for word in query.split()]
        raw_pattern = r".*".join(words)
        try:
            regex = re.compile(raw_pattern, flags=re.IGNORECASE)
        except re.error:
            return None

        if USE_CAPTION_FILTER:
            filter_mongo = {
                "$or": [
                    {"file_name": regex},
                    {"caption": regex},
                ]
            }
        else:
            filter_mongo = {"file_name": regex}

    if file_type:
        filter_mongo["file_type"] = file_type

    return filter_mongo


async def get_search_results(
    chat_id,
    query,
    file_type=None,
    max_results=None,
    offset=0,
    filter=False
):

    if chat_id is not None:
        settings = await get_settings(int(chat_id))

        if max_results is None:
            try:
                max_results = (
                    10
                    if settings.get("max_btn")
                    else int(MAX_B_TN)
                )

            except KeyError:
                await save_group_settings(
                    int(chat_id),
                    "max_btn",
                    True
                )

                settings = await get_settings(int(chat_id))

                max_results = (
                    10
                    if settings.get("max_btn")
                    else int(MAX_B_TN)
                )

    # -----------------------------------------------------
    # List Query
    # -----------------------------------------------------

    filter_mongo = _build_search_filter(query, file_type=file_type)
    if filter_mongo is None:
        return [], None, 0

    # -----------------------------------------------------
    # Ultra Fast Mode
    # -----------------------------------------------------

    if ULTRA_FAST_MODE:

        limit = max_results + 1

        find_tasks = [
            Media.find(filter_mongo)
            .sort("$natural", -1)
            .skip(offset)
            .limit(limit)
            .to_list(length=limit)
        ]

        if MULTIPLE_DB:
            find_tasks.append(
                Media2.find(filter_mongo)
                .sort("$natural", -1)
                .skip(offset)
                .limit(limit)
                .to_list(length=limit)
            )

        results = await asyncio.gather(*find_tasks)

        files = results[0]

        if MULTIPLE_DB and len(results) > 1:
            files.extend(results[1])

        files = files[:limit]

        has_next_page = len(files) > max_results

        if has_next_page:
            files = files[:-1]

        next_offset = (
            offset + len(files)
            if has_next_page
            else ""
        )

        total_results = (
            offset
            + len(files)
            + (1 if has_next_page else 0)
        )

    # -----------------------------------------------------
    # Normal Mode
    # -----------------------------------------------------

    else:

        count_tasks = [
            Media.count_documents(filter_mongo)
        ]

        find_tasks = [
            Media.find(filter_mongo)
            .sort("$natural", -1)
            .skip(offset)
            .limit(max_results)
            .to_list(length=max_results)
        ]

        if MULTIPLE_DB:

            count_tasks.append(
                Media2.count_documents(filter_mongo)
            )

            find_tasks.append(
                Media2.find(filter_mongo)
                .sort("$natural", -1)
                .skip(offset)
                .limit(max_results)
                .to_list(length=max_results)
            )

        count_results, find_results = await asyncio.gather(
            asyncio.gather(*count_tasks),
            asyncio.gather(*find_tasks)
        )

        total_results = sum(count_results)

        files = find_results[0]

        if MULTIPLE_DB and len(find_results) > 1:
            files.extend(find_results[1])

        files = files[:max_results]

        next_offset = offset + len(files)

        if next_offset >= total_results:
            next_offset = ""

    is_explicit_episode_query = is_episode_query(query)
    page_has_episodes = any(episode_sort_key(file)[0] == 0 for file in files)
    if max_results and (is_explicit_episode_query or page_has_episodes):
        try:
            ordered_files, too_many_files = await get_all_search_results(
                chat_id,
                query,
                file_type=file_type,
                max_results=None if is_explicit_episode_query else 5000,
            )
            if not too_many_files:
                files, next_offset, total_results = order_episode_page(
                    ordered_files,
                    offset,
                    max_results,
                )
        except Exception:
            logger.exception("Could not apply global episode ordering")

    return files, next_offset, total_results


async def get_all_search_results(
    chat_id,
    query,
    file_type=None,
    max_results=1000,
):
    """Fetch every matching file for the All send action, up to a safe cap."""
    filter_mongo = _build_search_filter(query, file_type=file_type)
    if filter_mongo is None:
        return [], False

    sources = [Media]
    if MULTIPLE_DB:
        sources.append(Media2)

    async def fetch_source(source):
        cursor = source.find(filter_mongo)
        if max_results is None:
            return await cursor.to_list(length=None)
        return await cursor.limit(max_results + 1).to_list(length=max_results + 1)

    results = await asyncio.gather(*(fetch_source(source) for source in sources))
    files = [file for source_results in results for file in source_results]
    if max_results is None:
        return files, False
    return files[:max_results], len(files) > max_results


# ---------------------------------------------------------
# Get Bad Files
# ---------------------------------------------------------

async def get_bad_files(query, file_type=None):

    query = query.strip()

    if not query:
        raw_pattern = "."

    elif " " not in query:

        raw_pattern = (
            r"(\b|[\.\+\-_])"
            + query
            + r"(\b|[\.\+\-_])"
        )

    else:

        raw_pattern = query.replace(
            " ",
            r".*[\s\.\+\-_()]"
        )

    try:
        regex = re.compile(
            raw_pattern,
            flags=re.IGNORECASE
        )

    except:
        return []

    if USE_CAPTION_FILTER:

        filter = {
            "$or": [
                {"file_name": regex},
                {"caption": regex}
            ]
        }

    else:

        filter = {
            "file_name": regex
        }

    if file_type:
        filter["file_type"] = file_type

    cursor1 = (
        Media.find(filter)
        .sort("$natural", -1)
    )

    files1 = await cursor1.to_list(
        length=await Media.count_documents(filter)
    )

    if MULTIPLE_DB:

        cursor2 = (
            Media2.find(filter)
            .sort("$natural", -1)
        )

        files2 = await cursor2.to_list(
            length=await Media2.count_documents(filter)
        )

        files = files1 + files2

    else:

        files = files1

    total_results = len(files)

    return files, total_results


# ---------------------------------------------------------
# Get File Details
# ---------------------------------------------------------

async def get_file_details(query):

    filter = {
        "file_id": query
    }

    tasks = [
        Media.find(filter)
        .to_list(length=1)
    ]

    if MULTIPLE_DB:
        tasks.append(
            Media2.find(filter)
            .to_list(length=1)
        )

    results = await asyncio.gather(*tasks)

    for filedetails in results:

        if filedetails:
            return filedetails

    return []


# ---------------------------------------------------------
# Encode File ID
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Encode File Reference
# ---------------------------------------------------------

def encode_file_ref(file_ref: bytes) -> str:

    return base64.urlsafe_b64encode(
        file_ref
    ).decode().rstrip("=")


# ---------------------------------------------------------
# Unpack New File ID
# ---------------------------------------------------------

def unpack_new_file_id(new_file_id):

    """Return file_id, file_ref"""

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


# ---------------------------------------------------------
# Fetch Media
# ---------------------------------------------------------

async def dreamxbotz_fetch_media(limit: int) -> List[dict]:

    try:

        if MULTIPLE_DB:

            db_size = await check_db_size(db)

            if db_size > 407:

                cursor = (
                    Media2.find()
                    .sort("$natural", -1)
                    .limit(limit)
                )

                files = await cursor.to_list(
                    length=limit
                )

                return files

        cursor = (
            Media.find()
            .sort("$natural", -1)
            .limit(limit)
        )

        files = await cursor.to_list(
            length=limit
        )

        return files

    except Exception as e:

        logger.error(
            f"Error in dreamxbotz_fetch_media: {e}"
        )

        return []


# ---------------------------------------------------------
# Clean Title
# ---------------------------------------------------------

async def dreamxbotz_clean_title(
    filename: str,
    is_series: bool = False
) -> str:

    try:

        year_match = re.search(
            r"^(.*?(\d{4}|\(\d{4}\)))",
            filename,
            re.IGNORECASE
        )

        if year_match:

            title = (
                year_match.group(1)
                .replace("(", "")
                .replace(")", "")
            )

            return (
                re.sub(
                    r"(?:@[^ \n\r\t.,:;!?()\[\]{}<>\\\/\"'=_%]+|[._\-\[\]@()]+)",
                    " ",
                    title,
                )
                .strip()
                .title()
            )

        if is_series:

            season_match = re.search(
                r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))(?:\s*Combined)?",
                filename,
                re.IGNORECASE
            )

            if season_match:

                title = season_match.group(1).strip()

                season = (
                    season_match.group(2)
                    or season_match.group(3)
                    or season_match.group(4)
                )

                title = (
                    re.sub(
                        r"(?:@[^ \n\r\t.,:;!?()\[\]{}<>\\\/\"'=_%]+|[._\-\[\]@()]+)",
                        " ",
                        title,
                    )
                    .strip()
                    .title()
                )

                return f"{title} S{int(season):02}"

        title = filename

        return (
            re.sub(
                r"(?:@[^ \n\r\t.,:;!?()\[\]{}<>\\\/\"'=_%]+|[._\-\[\]@()]+)",
                " ",
                title
            )
            .strip()
            .title()
        )

    except Exception as e:

        logger.error(
            f"Error in truncate_title: {e}"
        )

        return filename


# ---------------------------------------------------------
# Get Movies
# ---------------------------------------------------------

async def dreamxbotz_get_movies(
    limit: int = 20
) -> List[str]:

    try:

        cursor = await dreamxbotz_fetch_media(
            limit * 2
        )

        results = set()

        pattern = (
            r"(?:s\d{1,2}|season\s*\d+|season\d+)"
            r"(?:\s*combined)?"
            r"(?:e\d{1,2}|episode\s*\d+)?\b"
        )

        for file in cursor:

            file_name = getattr(
                file,
                "file_name",
                ""
            )

            if not re.search(
                pattern,
                file_name,
                re.IGNORECASE
            ):

                title = await dreamxbotz_clean_title(
                    file_name
                )

                results.add(title)

            if len(results) >= limit:
                break

        return sorted(list(results))[:limit]

    except Exception as e:

        logger.error(
            f"Error in dreamxbotz_get_movies: {e}"
        )

        return []


# ---------------------------------------------------------
# Get Series
# ---------------------------------------------------------

async def dreamxbotz_get_series(
    limit: int = 30
) -> Dict[str, List[int]]:

    try:

        cursor = await dreamxbotz_fetch_media(
            limit * 5
        )

        grouped = defaultdict(list)

        pattern = (
            r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))"
            r"(?:\s*Combined)?"
            r"(?:E(\d{1,2})|Episode\s*(\d+))?\b"
        )

        for file in cursor:

            file_name = getattr(
                file,
                "file_name",
                ""
            )

            match = re.search(
                pattern,
                file_name,
                re.IGNORECASE
            )

            if match:

                title = await dreamxbotz_clean_title(
                    match.group(1),
                    is_series=True
                )

                season = int(
                    match.group(2)
                    or match.group(3)
                    or match.group(4)
                )

                grouped[title].append(season)

        return {
            title: sorted(set(seasons))[:10]
            for title, seasons in grouped.items()
            if seasons
        }

    except Exception as e:

        logger.error(
            f"Error in dreamxbotz_get_series: {e}"
        )

        return []
