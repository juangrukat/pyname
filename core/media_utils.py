"""Shared media utilities for image and video processing across providers."""

import asyncio
import base64
import io
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

IMAGE_MAX_DIM = 1024
VIDEO_FRAME_MAX_DIM = 768
JPEG_QUALITY = 85

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tiff", ".bmp"}

# Comprehensive vision model detection
VISION_HINTS = {
    "vision", "llava", "moondream", "bakllava", "internvl",
    "minicpm-v", "phi-3-vision", "phi-3.5-vision", "phi-4-vision",
    "pixtral", "paligemma", "idefics", "qwen-vl", "qwen2-vl", "qwen3-vl"
}
VISION_TOKEN = re.compile(r"(^|[^a-z0-9])vl([^a-z0-9]|$)")


# ─────────────────────────────────────────────────────────────────────────────
# Vision Model Detection
# ─────────────────────────────────────────────────────────────────────────────

def model_supports_vision(model_name: str, provider_models: set[str] | None = None) -> bool:
    """
    Infer vision capability from model name.
    
    Args:
        model_name: The model identifier (e.g., "llava:latest", "gpt-5-mini")
        provider_models: Optional set of known vision models for the provider
    
    Returns:
        True if the model likely supports vision/images
    """
    model = model_name.lower()
    
    # Check provider-specific models first
    if provider_models:
        model_base = model.split(":")[0]
        if any(v in model_base for v in provider_models):
            return True
    
    # Check common vision hints
    if any(hint in model for hint in VISION_HINTS):
        return True
    
    # Check for "vl" token (vision-language pattern)
    return bool(VISION_TOKEN.search(model))


def is_image_file(extension: str) -> bool:
    """Check if extension is a supported image format."""
    return extension.lower() in IMAGE_EXTENSIONS


def is_video_file(extension: str) -> bool:
    """Check if extension is a supported video format."""
    return extension.lower() in VIDEO_EXTENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# Image Encoding
# ─────────────────────────────────────────────────────────────────────────────

async def encode_image_optimized(
    file_path: Path,
    max_dim: int = IMAGE_MAX_DIM,
    quality: int = JPEG_QUALITY
) -> tuple[str, str]:
    """
    Encode image as base64 with optimization.
    
    - Resizes to max dimension while preserving aspect ratio
    - Converts to JPEG for consistent compression
    - Applies EXIF rotation
    - Falls back to raw encoding if PIL unavailable
    
    Args:
        file_path: Path to the image file
        max_dim: Maximum dimension (width or height)
        quality: JPEG quality (1-100)
    
    Returns:
        Tuple of (base64_data, media_type)
    """
    def read_and_encode():
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return _encode_image_raw(file_path)

        try:
            with Image.open(file_path) as img:
                # Apply EXIF rotation
                img = ImageOps.exif_transpose(img)
                
                # Convert to RGB if necessary
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                
                # Resize if larger than max dimension
                max_side = max(img.size)
                if max_side > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
                
                # Encode to JPEG
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                return base64.b64encode(buffer.getvalue()).decode("utf-8"), "image/jpeg"
        except Exception:
            return _encode_image_raw(file_path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_and_encode)


async def encode_image_raw(file_path: Path) -> tuple[str, str]:
    """
    Encode image as base64 without processing.
    
    Use this when optimization is not needed or as a fallback.
    """
    def read_and_encode():
        return _encode_image_raw(file_path)
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_and_encode)


def _encode_image_raw(file_path: Path) -> tuple[str, str]:
    """Synchronous raw image encoding."""
    media_type = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return encoded, media_type


# ─────────────────────────────────────────────────────────────────────────────
# Video Frame Extraction
# ─────────────────────────────────────────────────────────────────────────────

async def extract_video_frames(
    file_path: Path,
    frame_count: int,
    duration_seconds: float | None = None,
    max_dim: int = VIDEO_FRAME_MAX_DIM
) -> list[str]:
    """
    Extract video frames as base64-encoded JPEGs.
    
    Uses ffmpeg to extract frames at balanced timestamps throughout the video.
    
    Args:
        file_path: Path to the video file
        frame_count: Number of frames to extract
        duration_seconds: Video duration (if known, avoids extra ffprobe call)
        max_dim: Maximum frame dimension
    
    Returns:
        List of base64-encoded JPEG frames
    """
    if frame_count <= 0:
        return []
    if shutil.which("ffmpeg") is None:
        return []

    base_dir = Path("data") / "tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamps = sample_video_timestamps(duration_seconds, frame_count)

    def _extract():
        frames: list[bytes] = []
        with tempfile.TemporaryDirectory(dir=base_dir, prefix="video_frames_") as tmpdir:
            temp_path = Path(tmpdir)
            for index, timestamp in enumerate(timestamps, start=1):
                output_path = temp_path / f"frame_{index:02d}.jpg"
                scale = (
                    f"scale='if(gt(iw,ih),min({max_dim},iw),-2)':"
                    f"'if(gt(iw,ih),-2,min({max_dim},ih))'"
                )
                cmd = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-y",
                    "-ss", f"{timestamp:.2f}",
                    "-i", str(file_path),
                    "-frames:v", "1",
                    "-vf", scale,
                    str(output_path)
                ]
                try:
                    subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue
                if output_path.exists():
                    try:
                        frames.append(output_path.read_bytes())
                    except OSError:
                        continue
        return frames

    loop = asyncio.get_event_loop()
    frames = await loop.run_in_executor(None, _extract)
    return [base64.b64encode(frame).decode("utf-8") for frame in frames]


def sample_video_timestamps(
    duration_seconds: float | None,
    frame_count: int
) -> list[float]:
    """
    Compute balanced timestamps for frame extraction.
    
    Timestamps are distributed evenly with margins to avoid intro/outro content.
    
    Args:
        duration_seconds: Video duration in seconds
        frame_count: Number of frames to extract
    
    Returns:
        List of timestamps in seconds
    """
    if frame_count <= 0:
        return []
    if duration_seconds and duration_seconds > 0:
        margin = max(duration_seconds * 0.08, 0.2)
        start = min(margin, max(duration_seconds - 0.2, 0.2))
        end = max(duration_seconds - margin, start)
        if frame_count == 1:
            return [max(0.1, duration_seconds / 2)]
        if frame_count == 2:
            return [max(0.1, start), max(0.1, end)]
        step = (end - start) / (frame_count - 1) if frame_count > 1 else 0
        return [max(0.1, start + step * index) for index in range(frame_count)]
    return [float(index + 1) for index in range(frame_count)]


# ─────────────────────────────────────────────────────────────────────────────
# Debug Utilities
# ─────────────────────────────────────────────────────────────────────────────

def should_debug(env_var: str = "PYNAME_DEBUG") -> bool:
    """Check if debug logging is enabled via environment variable."""
    value = os.getenv(env_var, "")
    return value.lower() in {"1", "true", "yes", "on"}


def format_prompt_debug(prompt: str, content_excerpt: str | None = None) -> str:
    """Format prompt info for debug logging."""
    excerpt_len = len(content_excerpt) if content_excerpt else 0
    return f"prompt_chars={len(prompt)} content_chars={excerpt_len}"


def format_response_debug(result: dict, max_len: int = 4000) -> str:
    """Serialize and truncate response payload for debugging."""
    import json
    try:
        payload = json.dumps(result, ensure_ascii=True)
    except (TypeError, ValueError):
        payload = str(result)
    if len(payload) > max_len:
        return f"{payload[:max_len]}...[truncated]"
    return payload
