"""
Storage abstraction for the Legal AI platform.
Supports local filesystem storage by default and easily swaps to S3/Appwrite/etc.
Preserves original documents verbatim and generates SHA256 checksums.
"""
from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional

from src.config import get_path


class DocumentStorage(ABC):
    """Abstract interface for storing and retrieving original uploaded files."""

    @abstractmethod
    def save_file(self, file_obj: BinaryIO, filename: str, user_id: str, doc_id: str) -> tuple[str, str, int]:
        """Saves the file and returns (storage_path_or_key, sha256_checksum, file_size_bytes)."""
        pass

    @abstractmethod
    def get_file_bytes(self, location: str) -> bytes:
        """Retrieves raw file bytes given a storage location."""
        pass

    @abstractmethod
    def delete_file(self, location: str) -> bool:
        """Deletes the stored file."""
        pass


class LocalDocumentStorage(DocumentStorage):
    """Local filesystem storage implementation with user-isolated directory layout."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            self.base_dir = get_path("raw_data_dir")
        else:
            self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, file_obj: BinaryIO, filename: str, user_id: str, doc_id: str) -> tuple[str, str, int]:
        user_dir = self.base_dir / "users" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(filename).suffix
        stored_name = f"{doc_id}{suffix}"
        target_path = user_dir / stored_name

        hasher = hashlib.sha256()
        size = 0

        file_obj.seek(0)
        with open(target_path, "wb") as f_out:
            while chunk := file_obj.read(65536):
                hasher.update(chunk)
                f_out.write(chunk)
                size += len(chunk)

        checksum = hasher.hexdigest()
        return str(target_path), checksum, size

    def get_file_bytes(self, location: str) -> bytes:
        p = Path(location)
        if not p.exists():
            raise FileNotFoundError(f"File not found at storage location: {location}")
        return p.read_bytes()

    def delete_file(self, location: str) -> bool:
        p = Path(location)
        if p.exists():
            p.unlink()
            return True
        return False


_default_storage: Optional[DocumentStorage] = None


def get_document_storage() -> DocumentStorage:
    global _default_storage
    if _default_storage is None:
        _default_storage = LocalDocumentStorage()
    return _default_storage
