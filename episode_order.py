import re


_SEASON_EPISODE_RE = re.compile(
    r"\bS(?:eason)?\s*0*(\d{1,2})[\s._-]*E(?:p(?:isode)?)?\s*0*(\d{1,3})"
    r"(?:\s*(?:-|to)\s*E?(?:p(?:isode)?)?\s*0*(\d{1,3}))?\b",
    re.IGNORECASE,
)
_SEASON_X_EPISODE_RE = re.compile(
    r"\b0*(\d{1,2})\s*x\s*0*(\d{1,3})(?:\s*(?:-|to)\s*0*(\d{1,3}))?\b",
    re.IGNORECASE,
)
_EPISODE_ONLY_RE = re.compile(
    r"\b(?:EP(?:ISODE)?|E)\s*0*(\d{1,3})"
    r"(?:\s*(?:-|to)\s*(?:E(?:P(?:ISODE)?)?\s*)?0*(\d{1,3}))?\b",
    re.IGNORECASE,
)
_EPISODE_QUERY_RE = re.compile(
    r"\b(?:S\s*0*\d{1,2}|SEASON\s*0*\d{1,2}|"
    r"EP(?:ISODE)?\s*0*\d{1,3}|\d{1,2}\s*X\s*\d{1,3})\b",
    re.IGNORECASE,
)


def episode_sort_key(file):
    """Sort media by numeric season and episode, with unknown names last."""
    filename = getattr(file, "file_name", "") or ""
    caption = getattr(file, "caption", "") or ""
    text = f"{filename}\n{caption}"

    for pattern in (_SEASON_EPISODE_RE, _SEASON_X_EPISODE_RE):
        match = pattern.search(text)
        if match:
            season, episode = int(match.group(1)), int(match.group(2))
            episode_end = int(match.group(3) or episode)
            return (0, season, episode, episode_end, filename.casefold())

    match = _EPISODE_ONLY_RE.search(text)
    if match:
        episode = int(match.group(1))
        episode_end = int(match.group(2) or episode)
        return (0, 1, episode, episode_end, filename.casefold())

    return (1, 0, 0, 0, filename.casefold())


def is_episode_query(query):
    """Identify explicit season/episode searches that need global page order."""
    text = " ".join(query) if isinstance(query, list) else str(query or "")
    return bool(_EPISODE_QUERY_RE.search(text))


def dedupe_media_files(files):
    """Remove repeated records while preserving same-name files with different sizes."""
    unique_files = []
    seen_keys = set()

    for file in files:
        file_id = str(getattr(file, "file_id", "") or "").strip()
        file_name = " ".join(
            (getattr(file, "file_name", "") or "").split()
        ).casefold()
        file_size = getattr(file, "file_size", None)

        keys = []
        if file_id:
            keys.append(("file_id", file_id))
        if file_name:
            keys.append(("file_name_and_size", file_name, file_size))

        if any(key in seen_keys for key in keys):
            continue

        unique_files.append(file)
        seen_keys.update(keys)

    return unique_files


def order_episode_page(files, offset, page_size):
    """Deduplicate and sort the complete result set, then return one stable page."""
    ordered = sorted(dedupe_media_files(files), key=episode_sort_key)
    page_offset = max(0, int(offset or 0))
    page = ordered[page_offset:page_offset + page_size]
    next_offset = (
        page_offset + len(page)
        if page_offset + len(page) < len(ordered)
        else ""
    )
    return page, next_offset, len(ordered)
