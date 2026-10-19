import os
import uuid
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext_lazy as _

# Allowed extensions by media type
ALLOWED_EXTENSIONS = {
    "audio": {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"},
    "video": {".mp4", ".webm", ".avi", ".mov", ".mkv", ".wmv"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"},
    "pdf": {".pdf"},
    "document": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt", ".ods", ".odp"},
}

# Allowed MIME types by media type
ALLOWED_MIMES = {
    "audio": {
        "audio/mpeg", "audio/mp3", "audio/wav", "audio/wave", "audio/ogg",
        "audio/aac", "audio/flac", "audio/x-flac", "audio/m4a", "audio/mp4",
    },
    "video": {
        "video/mp4", "video/webm", "video/avi", "video/x-msvideo",
        "video/quicktime", "video/x-matroska", "video/x-ms-wmv",
    },
    "image": {
        "image/jpeg", "image/png", "image/gif", "image/bmp", "image/svg+xml",
        "image/webp", "image/x-ms-bmp",
    },
    "pdf": {"application/pdf"},
    "document": {
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "application/rtf",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
    },
}

# Max file size: 500 MB
MAX_FILE_SIZE = 500 * 1024 * 1024


def get_media_storage_root():
    return Path(getattr(settings, "MEDIA_ROOT", settings.BASE_DIR / "media"))


def get_media_type_from_mime(mime_type: str) -> str | None:
    mime = mime_type.lower()
    for media_type, mimes in ALLOWED_MIMES.items():
        if mime in mimes:
            return media_type
    return None


def get_media_type_from_extension(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    for media_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return media_type
    return None


def clean_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    name = Path(filename).stem
    name = "".join(c for c in name if c.isalnum() or c in "-_ ")
    name = name.strip().replace(" ", "_")
    if not name:
        name = uuid.uuid4().hex[:8]
    return f"{name}{ext}"


def validate_filename(filename: str) -> tuple[str, str]:
    if not filename or not filename.strip():
        raise ValueError(_("Filename is empty."))
    if "\\" in filename or ".." in filename:
        raise ValueError(_("Invalid filename."))
    ext = Path(filename).suffix.lower()
    if not ext:
        raise ValueError(_("File has no extension."))
    return clean_filename(filename), ext


def validate_extension(extension: str, media_type: str) -> None:
    allowed = ALLOWED_EXTENSIONS.get(media_type, set())
    if extension.lower() not in allowed:
        raise ValueError(_("Extension '%(ext)s' is not allowed for media type '%(type)s'.") % {"ext": extension, "type": media_type})


def validate_mime_type(mime_type: str, media_type: str) -> None:
    allowed = ALLOWED_MIMES.get(media_type, set())
    if mime_type.lower() not in allowed:
        raise ValueError(_("MIME type '%(mime)s' is not allowed for media type '%(type)s'.") % {"mime": mime_type, "type": media_type})


def validate_file_size(size: int) -> None:
    if size > MAX_FILE_SIZE:
        raise ValueError(_("File size exceeds maximum allowed (%(max)s bytes).") % {"max": MAX_FILE_SIZE})


def validate_path_traversal(path: str) -> None:
    if ".." in path or path.startswith("/") or path.startswith("\\"):
        raise ValueError(_("Invalid path."))


def get_safe_upload_path(folder, filename: str) -> str:
    root = get_media_storage_root()
    if folder:
        folder_path = Path(folder.name)
        validate_path_traversal(str(folder_path))
        full_path = root / folder_path
    else:
        full_path = root
    full_path.mkdir(parents=True, exist_ok=True)
    safe_name = clean_filename(filename)
    rel_path = full_path.relative_to(root) / safe_name
    validate_path_traversal(str(rel_path))
    return str(rel_path)
