from __future__ import annotations
import asyncio
import subprocess
import json
import random
from pathlib import Path
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from .models import FileMetadata, ImageMetadata, VideoMetadata


# Files to ignore when gathering neighbor context
IGNORE_FILES = {
    ".DS_Store", "Thumbs.db", "desktop.ini", ".gitignore",
    ".localized", "Icon\r", ".Spotlight-V100", ".Trashes"
}
IGNORE_PREFIXES = (".", "_", "~")
IGNORE_SUFFIXES = (".tmp", ".bak", ".swp", ".part", ".crdownload")
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml",
    ".log", ".ini", ".cfg", ".toml"
}
PDF_EXTENSIONS = {".pdf"}
MARKITDOWN_EXTENSIONS = {
    ".docx", ".pptx", ".xlsx", ".pdf",
    ".html", ".htm", ".xml", ".rss"
}
TEXTUTIL_EXTENSIONS = {
    ".doc", ".odt", ".rtf", ".rtfd", ".wordml",
    ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".html", ".htm"
}


class MetadataExtractor:
    """Extract metadata from files."""
    
    async def extract(
        self,
        file_path: Path,
        neighbor_count: int = 3,
        exclude_paths: set[Path] | None = None,
        include_content: bool = False,
        content_max_chars: int = 2000
    ) -> FileMetadata:
        """
        Extract all available metadata from a file.
        
        Args:
            file_path: Path to the file
            neighbor_count: Number of neighbor filenames to include
            exclude_paths: Paths to exclude from neighbor context (e.g., already renamed files)
        """
        stat = file_path.stat()
        extension = file_path.suffix.lower()
        
        # Base metadata
        metadata = FileMetadata(
            file_path=file_path,
            file_name=file_path.name,
            extension=extension,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_birthtime),  # macOS specific
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )
        
        # Extract type-specific metadata
        if extension in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tiff", ".bmp"}:
            metadata.image = await self._extract_image_metadata(file_path)
        elif extension in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
            metadata.video = await self._extract_video_metadata(file_path)
        
        # Get neighbor context
        metadata.neighbor_names = self._get_neighbor_names(
            file_path, 
            neighbor_count, 
            exclude_paths or set()
        )

        if include_content and content_max_chars > 0:
            content_excerpt, content_truncated, content_source = await self._extract_content(
                file_path,
                extension,
                content_max_chars
            )
            metadata.content_excerpt = content_excerpt
            metadata.content_truncated = content_truncated
            metadata.content_source = content_source
        
        return metadata
    
    async def _extract_image_metadata(self, file_path: Path) -> ImageMetadata:
        """Extract EXIF and image metadata."""
        def _extract():
            metadata = ImageMetadata()
            
            try:
                with Image.open(file_path) as img:
                    metadata.width = img.width
                    metadata.height = img.height
                    
                    exif_data = img._getexif()
                    if exif_data:
                        exif = {TAGS.get(k, k): v for k, v in exif_data.items()}
                        
                        # Date taken
                        date_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
                        if date_str:
                            try:
                                metadata.date_taken = datetime.strptime(
                                    date_str, "%Y:%m:%d %H:%M:%S"
                                )
                            except ValueError:
                                pass
                        
                        # Camera info
                        metadata.camera_make = exif.get("Make")
                        metadata.camera_model = exif.get("Model")
                        metadata.lens_model = exif.get("LensModel")
                        metadata.focal_length = str(exif.get("FocalLength", ""))
                        metadata.aperture = str(exif.get("FNumber", ""))
                        metadata.iso = exif.get("ISOSpeedRatings")
                        
                        # GPS
                        gps_info = exif.get("GPSInfo")
                        if gps_info:
                            gps = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}
                            
                            lat = gps.get("GPSLatitude")
                            lat_ref = gps.get("GPSLatitudeRef")
                            lon = gps.get("GPSLongitude")
                            lon_ref = gps.get("GPSLongitudeRef")
                            
                            if lat and lon:
                                metadata.gps_latitude = self._convert_gps(lat, lat_ref)
                                metadata.gps_longitude = self._convert_gps(lon, lon_ref)
            
            except Exception:
                pass  # Return partial metadata on error
            
            return metadata
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract)
    
    def _convert_gps(self, coord: tuple, ref: str) -> float:
        """Convert GPS coordinates to decimal degrees."""
        try:
            degrees = float(coord[0])
            minutes = float(coord[1])
            seconds = float(coord[2])
            
            decimal = degrees + minutes / 60 + seconds / 3600
            
            if ref in ("S", "W"):
                decimal = -decimal
            
            return round(decimal, 6)
        except (TypeError, IndexError, ValueError):
            return 0.0
    
    async def _extract_video_metadata(self, file_path: Path) -> VideoMetadata:
        """Extract video metadata using ffprobe."""
        def _extract():
            metadata = VideoMetadata()
            
            try:
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v", "quiet",
                        "-print_format", "json",
                        "-show_format",
                        "-show_streams",
                        str(file_path)
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    return metadata
                
                data = json.loads(result.stdout)
                
                # Get video stream
                video_stream = next(
                    (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                    None
                )
                
                if video_stream:
                    metadata.width = video_stream.get("width")
                    metadata.height = video_stream.get("height")
                    metadata.codec = video_stream.get("codec_name")
                    
                    # Parse frame rate
                    fps_str = video_stream.get("r_frame_rate", "0/1")
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        if int(den) != 0:
                            metadata.fps = round(int(num) / int(den), 2)
                
                # Get format info
                format_info = data.get("format", {})
                
                duration = format_info.get("duration")
                if duration:
                    metadata.duration_seconds = float(duration)
                
                bitrate = format_info.get("bit_rate")
                if bitrate:
                    metadata.bitrate = int(bitrate)
                
                # Creation time
                tags = format_info.get("tags", {})
                creation_time = tags.get("creation_time")
                if creation_time:
                    try:
                        metadata.creation_time = datetime.fromisoformat(
                            creation_time.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
            
            except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
                pass
            
            return metadata
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract)

    async def _extract_content(
        self,
        file_path: Path,
        extension: str,
        max_chars: int
    ) -> tuple[str | None, bool, str | None]:
        """Extract text content for supported file types."""
        extension = extension.lower()
        if extension in TEXT_EXTENSIONS:
            text, truncated = await self._read_text_excerpt(file_path, max_chars)
            if text:
                return text, truncated, "text"
            return None, False, None
        if extension in PDF_EXTENSIONS:
            text, truncated = await self._read_pdf_excerpt(file_path, max_chars)
            if text:
                return text, truncated, "pypdf"
            text, truncated = await self._read_markitdown_excerpt(file_path, max_chars)
            if text:
                return text, truncated, "markitdown"
            text, truncated = await self._read_textutil_excerpt(file_path, max_chars)
            if text:
                return text, truncated, "textutil"
            return None, False, None
        if extension in MARKITDOWN_EXTENSIONS:
            text, truncated = await self._read_markitdown_excerpt(file_path, max_chars)
            if text:
                return text, truncated, "markitdown"
            text, truncated = await self._read_textutil_excerpt(file_path, max_chars)
            if text:
                return text, truncated, "textutil"
        if extension in TEXTUTIL_EXTENSIONS:
            text, truncated = await self._read_textutil_excerpt(file_path, max_chars)
            if text:
                return text, truncated, "textutil"
        return None, False, None

    async def _read_text_excerpt(
        self,
        file_path: Path,
        max_chars: int
    ) -> tuple[str | None, bool]:
        """Read a text file excerpt with truncation."""
        if max_chars <= 0:
            return None, False

        max_bytes = max_chars * 4

        def _read():
            try:
                with open(file_path, "rb") as f:
                    raw = f.read(max_bytes + 1)
                if not raw:
                    return None, False
                text = raw.decode("utf-8", errors="ignore")
                text, truncated = self._truncate_text(text, max_chars)
                if not text:
                    return None, False
                if len(raw) > max_bytes:
                    truncated = True
                return text, truncated
            except OSError:
                return None, False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _read)

    async def _read_pdf_excerpt(
        self,
        file_path: Path,
        max_chars: int
    ) -> tuple[str | None, bool]:
        """Extract text from a PDF, stopping at max_chars."""
        if max_chars <= 0:
            return None, False

        def _extract():
            try:
                from pypdf import PdfReader
            except Exception:
                return None, False

            try:
                reader = PdfReader(str(file_path))
            except Exception:
                return None, False

            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception:
                    return None, False

            parts: list[str] = []
            total_chars = 0
            for page in reader.pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                if page_text:
                    parts.append(page_text.strip())
                    total_chars += len(page_text)
                if total_chars >= max_chars:
                    break

            text = "\n\n".join([p for p in parts if p])
            text, truncated_by_length = self._truncate_text(text, max_chars)
            if not text:
                return None, False

            truncated = truncated_by_length or total_chars > max_chars or len(parts) < len(reader.pages)
            return text, truncated

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract)

    async def _read_markitdown_excerpt(
        self,
        file_path: Path,
        max_chars: int
    ) -> tuple[str | None, bool]:
        """Extract text using markitdown if available."""
        def _extract():
            text = None
            try:
                from markitdown import MarkItDown
                converter = MarkItDown()
                result = converter.convert(str(file_path))
                text = self._coerce_markitdown_text(result)
            except Exception:
                text = None

            if not text:
                try:
                    result = subprocess.run(
                        ["markitdown", str(file_path)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        text = result.stdout
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    text = None

            return text

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _extract)
        return self._truncate_text(text, max_chars)

    async def _read_textutil_excerpt(
        self,
        file_path: Path,
        max_chars: int
    ) -> tuple[str | None, bool]:
        """Extract text using macOS textutil."""
        def _extract():
            try:
                result = subprocess.run(
                    ["textutil", "-convert", "txt", "-stdout", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    return None
                return result.stdout
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return None

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _extract)
        return self._truncate_text(text, max_chars)

    @staticmethod
    def _truncate_text(text: str | None, max_chars: int) -> tuple[str | None, bool]:
        """Normalize and truncate extracted text."""
        if not text:
            return None, False
        cleaned = text.strip()
        if not cleaned:
            return None, False
        if len(cleaned) <= max_chars:
            return cleaned, False
        return cleaned[:max_chars].strip(), True

    def _coerce_markitdown_text(self, result: object) -> str | None:
        """Extract text content from a markitdown result object."""
        text = self._extract_text_from_value(result)
        if text:
            return text

        for attr in ("text_content", "markdown", "text", "content", "plain_text", "value"):
            try:
                value = getattr(result, attr)
            except Exception:
                continue
            text = self._extract_text_from_value(value)
            if text:
                return text

        if hasattr(result, "to_dict"):
            try:
                text = self._extract_text_from_value(result.to_dict())
            except Exception:
                text = None
            if text:
                return text

        if hasattr(result, "__dict__"):
            text = self._extract_text_from_value(result.__dict__)
            if text:
                return text

        return None

    def _extract_text_from_value(self, value: object) -> str | None:
        """Extract text from common markitdown result shapes."""
        if isinstance(value, str):
            text = value.strip()
            if text and not self._is_object_repr(text):
                return text
            return None

        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text and not self._is_object_repr(text):
                        parts.append(text)
                elif isinstance(item, dict):
                    text = self._extract_text_from_value(item)
                    if text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
            return None

        if isinstance(value, dict):
            for key in (
                "text_content", "markdown", "text", "content",
                "plain_text", "value", "body"
            ):
                if key in value:
                    text = self._extract_text_from_value(value.get(key))
                    if text:
                        return text
            return None

        return None

    @staticmethod
    def _is_object_repr(text: str) -> bool:
        """Detect default object repr strings."""
        return text.startswith("<") and text.endswith(">") and " object at 0x" in text
    
    def _get_neighbor_names(
        self,
        file_path: Path,
        count: int,
        exclude_paths: set[Path]
    ) -> list[str]:
        """
        Get relevant sibling filenames for naming convention inference.
        
        Excludes:
        - The file itself
        - System/hidden files
        - Files already renamed in this session
        """
        if count <= 0:
            return []
        
        siblings = []
        target_ext = file_path.suffix.lower()
        
        try:
            for f in file_path.parent.iterdir():
                # Skip the file itself
                if f == file_path:
                    continue
                
                # Skip files renamed in this session
                if f in exclude_paths:
                    continue
                
                # Skip system and hidden files
                if f.name in IGNORE_FILES:
                    continue
                if f.name.startswith(IGNORE_PREFIXES):
                    continue
                if f.name.endswith(IGNORE_SUFFIXES):
                    continue
                
                # Only include actual files
                if f.is_file():
                    siblings.append(f.name)
        
        except PermissionError:
            return []
        
        # Prioritize files with the same extension
        same_ext = [s for s in siblings if s.lower().endswith(target_ext)]
        other = [s for s in siblings if not s.lower().endswith(target_ext)]
        
        # Shuffle for variety
        random.shuffle(same_ext)
        random.shuffle(other)
        
        # Take from same extension first, then others
        result = same_ext[:count]
        if len(result) < count:
            result.extend(other[:count - len(result)])
        
        return result
