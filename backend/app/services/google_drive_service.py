import io
import os
from functools import lru_cache

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Native Google files (Docs, Sheets, Slides) have no binary content, so
# get_media() fails on them. They must be exported to a normal format.
GOOGLE_EXPORT_TYPES = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.presentation": "application/pdf",
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
}

FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

NUM_RETRIES = 3  # retries on 429 / 5xx with backoff


@lru_cache(maxsize=1)
def _get_service():
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not credentials_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS is not configured"
        )

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES,
    )

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def _http_error_reason(error: HttpError) -> str:
    try:
        details = error.error_details or []
        reasons = [d.get("reason") for d in details if isinstance(d, dict)]
        return ", ".join(r for r in reasons if r) or str(error)
    except Exception:
        return str(error)


def download_drive_file_with_metadata(file_id: str) -> tuple[bytes, str, str]:
    """Return (content, file_name, mime_type) for a Drive file.

    Binary files (PDF, DOCX, TXT, ...) are downloaded as-is.
    Google Docs/Slides are exported to PDF, Sheets to XLSX.
    """
    service = _get_service()

    try:
        meta = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size",
            supportsAllDrives=True,
        ).execute(num_retries=NUM_RETRIES)

        mime_type = meta["mimeType"]
        name = meta["name"]

        if mime_type == FOLDER_MIME:
            raise ValueError("This Drive ID is a folder, not a file")

        if mime_type == SHORTCUT_MIME:
            raise ValueError(
                "This Drive ID is a shortcut; use the target file's ID"
            )

        if mime_type in GOOGLE_EXPORT_TYPES:
            export_type = GOOGLE_EXPORT_TYPES[mime_type]
            request = service.files().export_media(
                fileId=file_id,
                mimeType=export_type,
            )
            result_type = export_type
        else:
            request = service.files().get_media(
                fileId=file_id,
                supportsAllDrives=True,
            )
            result_type = mime_type

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            _, done = downloader.next_chunk(num_retries=NUM_RETRIES)

        return buffer.getvalue(), name, result_type

    except HttpError as error:
        status = error.resp.status
        reason = _http_error_reason(error)

        if status == 404:
            raise FileNotFoundError(
                "Google Drive file not found, or it is not shared with "
                "the service account"
            ) from error

        if status == 403:
            # 403 is not always a sharing problem: it can also be
            # fileNotDownloadable, exportSizeLimitExceeded, or rate limits.
            raise PermissionError(
                f"Google Drive denied access ({reason})"
            ) from error

        raise RuntimeError(
            f"Google Drive download failed (HTTP {status}: {reason})"
        ) from error


def download_drive_file(file_id: str) -> bytes:
    """Backwards-compatible wrapper that returns only the file bytes."""
    content, _name, _mime = download_drive_file_with_metadata(file_id)
    return content