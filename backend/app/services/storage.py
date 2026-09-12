import os
import shutil
import uuid
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        # Resolve storage directory relative to backend folder
        self.base_dir = os.path.abspath(settings.STORAGE_LOCAL_PATH)
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info("Local storage initialized at: %s", self.base_dir)

    def save_file(self, filename: str, file_bytes: bytes) -> str:
        # Generate a unique directory name or suffix to avoid conflict
        unique_id = uuid.uuid4().hex
        _, ext = os.path.splitext(filename)
        safe_filename = f"{unique_id}{ext}"
        
        # Determine path
        file_path = os.path.join(self.base_dir, safe_filename)
        
        # Save file to disk
        with open(file_path, "wb") as buffer:
            buffer.write(file_bytes)
            
        logger.info("Saved file %s to %s", filename, file_path)
        return file_path

    def get_file_path(self, storage_path: str) -> str:
        # Verify the file is within the storage directory to prevent directory traversal attacks
        abs_path = os.path.abspath(storage_path)
        base_dir = os.path.normpath(self.base_dir)
        if abs_path != base_dir and not abs_path.startswith(base_dir + os.sep):
            raise PermissionError("Access denied: File is outside storage boundaries.")
        if not os.path.exists(abs_path):
            raise FileNotFoundError("The file requested does not exist.")
        return abs_path

    def delete_file(self, storage_path: str):
        try:
            abs_path = self.get_file_path(storage_path)
            if os.path.exists(abs_path):
                os.remove(abs_path)
                logger.info("Deleted file at path: %s", abs_path)
        except Exception as e:
            logger.error("Failed to delete file %s: %s", storage_path, e)

storage_service = StorageService()
