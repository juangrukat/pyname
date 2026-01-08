import re
import unicodedata
from pathlib import Path


# Characters illegal in macOS filenames
ILLEGAL_CHARS = re.compile(r'[:\x00/]')

# Additional characters to sanitize for safety
UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Maximum filename length (macOS HFS+ limit is 255 UTF-16 code units)
MAX_FILENAME_LENGTH = 200


class SafetyChecker:
    """Filename sanitization and collision resolution."""
    
    def sanitize_filename(self, name: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
        """
        Make a name safe for use as a macOS filename.
        
        Args:
            name: Proposed filename (without extension)
            max_length: Maximum length for the name
            
        Returns:
            Sanitized filename
        """
        if not name:
            return "unnamed"
        
        # Normalize Unicode (NFC is standard for macOS)
        name = unicodedata.normalize("NFC", name)
        
        # Remove/replace unsafe characters
        name = UNSAFE_CHARS.sub("_", name)
        
        # Remove leading/trailing dots and spaces (problematic on macOS)
        name = name.strip(". ")
        
        # Collapse multiple underscores/hyphens
        name = re.sub(r'[-_]{2,}', '-', name)
        
        # Truncate if necessary
        if len(name) > max_length:
            name = name[:max_length].rstrip("-_. ")
        
        # Final check
        if not name:
            return "unnamed"
        
        return name
    
    def resolve_collision(self, target_path: Path) -> Path:
        """
        Find a unique path if the target already exists.
        
        Args:
            target_path: Desired file path
            
        Returns:
            Unique path (original if no collision)
        """
        if not target_path.exists():
            return target_path
        
        parent = target_path.parent
        stem = target_path.stem
        suffix = target_path.suffix
        
        counter = 1
        while True:
            new_name = f"{stem}_v{counter}{suffix}"
            new_path = parent / new_name
            
            if not new_path.exists():
                return new_path
            
            counter += 1
            
            # Sanity limit
            if counter > 9999:
                raise RuntimeError(
                    f"Could not find unique filename for {target_path.name} "
                    f"after {counter} attempts"
                )
    
    def validate_rename_operation(
        self,
        source: Path,
        target: Path
    ) -> tuple[bool, str]:
        """
        Validate that a rename operation is safe.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Source must exist
        if not source.exists():
            return False, f"Source file does not exist: {source}"
        
        # Source must be a file
        if not source.is_file():
            return False, f"Source is not a file: {source}"
        
        # Target directory must exist
        if not target.parent.exists():
            return False, f"Target directory does not exist: {target.parent}"
        
        # Source and target must be different
        if source.resolve() == target.resolve():
            return False, "Source and target are the same file"
        
        # Check filename length
        if len(target.name.encode('utf-8')) > 255:
            return False, f"Filename too long: {target.name}"
        
        return True, ""