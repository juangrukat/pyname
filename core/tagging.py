import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _should_debug() -> bool:
    """Check if debug logging is enabled via environment."""
    import os
    return os.environ.get("PYNAME_DEBUG_TAGS", "").lower() in ("1", "true", "yes") or \
           os.environ.get("PYNAME_DEBUG", "").lower() in ("1", "true", "yes")


class TagManager:
    """Wrapper for macOS Finder tags using the `tag` CLI tool."""
    
    def __init__(self):
        self._tag_available: bool | None = None
        self._warned_unavailable: bool = False
    
    async def is_available(self) -> bool:
        """Check if the tag CLI tool is available."""
        if self._tag_available is None:
            self._tag_available = shutil.which("tag") is not None
            if not self._tag_available and not self._warned_unavailable:
                self._warned_unavailable = True
                logger.warning(
                    "macOS 'tag' CLI not found. Finder tags will not be applied. "
                    "Install with: brew install tag"
                )
        return self._tag_available
    
    async def add_tags(self, file_path: Path, tags: list[str]) -> bool:
        """
        Add Finder tags to a file.
        
        Args:
            file_path: Path to the file
            tags: List of tag names to add
            
        Returns:
            True if successful, False otherwise
        """
        if not await self.is_available():
            return False
        
        if not tags:
            return True
        
        # Sanitize tags (remove commas as they're used as separators)
        clean_tags = [tag.replace(",", " ") for tag in tags]
        tag_string = ",".join(clean_tags)
        
        if _should_debug():
            logger.info(f"Adding tags to {file_path.name}: {clean_tags}")
        
        def _run():
            try:
                result = subprocess.run(
                    ["tag", "--add", tag_string, str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    logger.warning(f"Failed to add tags to {file_path.name}: {stderr or 'unknown error'}")
                    return False
                if _should_debug():
                    logger.info(f"Successfully added tags to {file_path.name}")
                return True
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout adding tags to {file_path.name}")
                return False
            except FileNotFoundError:
                logger.warning("'tag' command not found during execution")
                return False
            except Exception as e:
                logger.warning(f"Error adding tags to {file_path.name}: {e}")
                return False
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run)

    async def apply_tags(self, file_path: Path, tags: list[str], mode: str = "append") -> bool:
        """Apply tags using append or replace mode."""
        if mode == "replace":
            existing = await self.get_tags(file_path)
            if existing:
                removed = await self.remove_tags(file_path, existing)
                if not removed:
                    return False
        return await self.add_tags(file_path, tags)
    
    async def get_tags(self, file_path: Path) -> list[str]:
        """
        Get current tags from a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of tag names
        """
        if not await self.is_available():
            return []
        
        def _run():
            try:
                result = subprocess.run(
                    ["tag", "--list", "--no-name", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    return [t.strip() for t in result.stdout.split(",") if t.strip()]
                return []
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return []
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run)
    
    async def remove_tags(self, file_path: Path, tags: list[str]) -> bool:
        """Remove specific tags from a file."""
        if not await self.is_available():
            return False
        
        if not tags:
            return True
        
        tag_string = ",".join(tags)
        
        def _run():
            try:
                result = subprocess.run(
                    ["tag", "--remove", tag_string, str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run)
