"""Local-filesystem stub for the bank's FileNet document store

Swapping this module out for a real FileNet client would be a one-day job; the rest of the codebase only depends on
the four functions exported below.

Storage layout:
    filenet_storage/
        <uuid>.<ext>     <- document bytes
        <uuid>.json      <- metadata sidecar

The UUID *is* the FileNet reference. Anything that needs the document later
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.observability import get_logger

log = get_logger(__name__)

# Small allowlist keeps MIME guessing simple. (Can add new filetypes later if needed.)
SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}


def archive(content: bytes, extension: str, metadata: Optional[dict] = None) -> str:
    """
    The reference is a UUID string; pass it to fetch_bytes / fetch_path /
    fetch_metadata to retrieve later.
    
    """
    ext = extension.lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported document extension: .{ext}")

    ref = str(uuid.uuid4())
    doc_path = settings.filenet_root / f"{ref}.{ext}"
    meta_path = settings.filenet_root / f"{ref}.json"

    doc_path.write_bytes(content)

    full_metadata = {
        "ref": ref,
        "extension": ext,
        "size_bytes": len(content),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "user_metadata": metadata or {},
    }
    meta_path.write_text(json.dumps(full_metadata, indent=2))

    log.info("filenet_archive", ref=ref, ext=ext, size=len(content))
    return ref


def fetch_metadata(ref: str) -> dict:
    """Load the metadata sidecar for a reference."""
    meta_path = settings.filenet_root / f"{ref}.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"FileNet ref not found: {ref}")
    return json.loads(meta_path.read_text())


def fetch_path(ref: str) -> Path:
    """Return the absolute path of the archived document."""
    meta = fetch_metadata(ref)
    return settings.filenet_root / f"{ref}.{meta['extension']}"


def fetch_bytes(ref: str) -> bytes:
    """Load the document bytes by reference."""
    return fetch_path(ref).read_bytes()