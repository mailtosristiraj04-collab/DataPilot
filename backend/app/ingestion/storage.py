import logging
import uuid
from pathlib import Path

from app.core.config import Settings

logger = logging.getLogger(__name__)


class DatasetStorage:
    def __init__(self, settings: Settings) -> None:
        self.root = settings.storage_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if path.parent != self.root or path == self.root:
            raise ValueError("Invalid dataset storage key")
        return path

    def create_key(self, extension: str) -> str:
        return f"{uuid.uuid4()}{extension}"

    def remove(self, storage_key: str) -> None:
        path = self.path_for(storage_key)
        try:
            path.unlink()
        except FileNotFoundError:
            logger.warning("Dataset storage file was already absent key=%s", storage_key)

