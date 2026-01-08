import shutil
import subprocess
from importlib import metadata
from dataclasses import dataclass


@dataclass
class DependencyStatus:
    available: bool
    version: str | None
    install_hint: str


class DependencyChecker:
    """Check availability of external dependencies."""
    
    def check_all(self) -> dict[str, DependencyStatus]:
        """Check all dependencies."""
        return {
            "tag": self.check_tag(),
            "ffprobe": self.check_ffprobe(),
            "ffmpeg": self.check_ffmpeg(),
            "ollama": self.check_ollama(),
            "pypdf": self.check_pypdf(),
            "markitdown": self.check_markitdown(),
            "textutil": self.check_textutil(),
        }
    
    def check_tag(self) -> DependencyStatus:
        """Check macOS tag CLI."""
        path = shutil.which("tag")
        if path:
            try:
                result = subprocess.run(
                    ["tag", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version = result.stdout.strip() or result.stderr.strip() or "installed"
                return DependencyStatus(True, version, "")
            except Exception:
                return DependencyStatus(True, "unknown", "")
        
        return DependencyStatus(
            False, None,
            "brew install tag"
        )
    
    def check_ffprobe(self) -> DependencyStatus:
        """Check ffprobe."""
        path = shutil.which("ffprobe")
        if path:
            try:
                result = subprocess.run(
                    ["ffprobe", "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version = result.stdout.split("\n")[0] if result.stdout else "installed"
                return DependencyStatus(True, version, "")
            except Exception:
                return DependencyStatus(True, "unknown", "")
        
        return DependencyStatus(
            False, None,
            "brew install ffmpeg"
        )

    def check_ffmpeg(self) -> DependencyStatus:
        """Check ffmpeg (required for video frame extraction)."""
        path = shutil.which("ffmpeg")
        if path:
            try:
                result = subprocess.run(
                    ["ffmpeg", "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version = result.stdout.split("\n")[0] if result.stdout else "installed"
                return DependencyStatus(True, version, "")
            except Exception:
                return DependencyStatus(True, "unknown", "")
        return DependencyStatus(
            False, None,
            "brew install ffmpeg"
        )
    
    def check_ollama(self) -> DependencyStatus:
        """Check Ollama."""
        path = shutil.which("ollama")
        if path:
            try:
                result = subprocess.run(
                    ["ollama", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version = result.stdout.strip() or "installed"
                return DependencyStatus(True, version, "")
            except Exception:
                return DependencyStatus(True, "unknown", "")
        
        return DependencyStatus(
            False, None,
            "Download from https://ollama.ai"
        )

    def check_pypdf(self) -> DependencyStatus:
        """Check pypdf availability for PDF text extraction."""
        try:
            version = metadata.version("pypdf")
            return DependencyStatus(True, version, "")
        except metadata.PackageNotFoundError:
            return DependencyStatus(False, None, "pip install pypdf")

    def check_markitdown(self) -> DependencyStatus:
        """Check markitdown availability for office/doc extraction."""
        try:
            version = metadata.version("markitdown")
            return DependencyStatus(True, version, "")
        except metadata.PackageNotFoundError:
            return DependencyStatus(False, None, "pip install markitdown")

    def check_textutil(self) -> DependencyStatus:
        """Check macOS textutil availability."""
        path = shutil.which("textutil")
        if path:
            return DependencyStatus(True, "installed", "")
        return DependencyStatus(False, None, "textutil is built into macOS")
