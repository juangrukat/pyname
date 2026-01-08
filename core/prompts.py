"""
Prompt templates for different file types.

Each prompt is designed to extract the most relevant naming information
based on what data is available for that file type.
"""

from pathlib import Path
from .models import FileMetadata, PromptOverrides


class PromptBuilder:
    """Build optimized prompts for different file types."""

    @classmethod
    def _prompt_type(cls, metadata: FileMetadata) -> str:
        ext = metadata.extension.lower()
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tiff", ".bmp"}:
            return "image"
        if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv"}:
            return "video"
        if ext in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                   ".txt", ".md", ".rtf", ".csv", ".odt", ".ods", ".odp"}:
            return "document"
        return "generic"

    @classmethod
    def _render_template(cls, template: str, metadata: FileMetadata) -> str:
        context = cls._template_context(metadata)

        class _SafeDict(dict):
            def __missing__(self, key):
                return ""

        return template.format_map(_SafeDict(context))

    @classmethod
    def _template_context(cls, metadata: FileMetadata) -> dict[str, str]:
        image = metadata.image
        video = metadata.video
        neighbor_names = metadata.neighbor_names or []
        file_name = metadata.file_name if metadata.include_current_filename else ""
        tag_count = metadata.tag_count
        return {
            "file_name": file_name,
            "extension": metadata.extension,
            "size_human": metadata.size_human,
            "created_at": metadata.created_at.isoformat(),
            "modified_at": metadata.modified_at.isoformat(),
            "parent_folder_name": metadata.parent_folder_name or "",
            "folder_context": metadata.folder_context or "",
            "neighbor_names": "\n".join(neighbor_names),
            "neighbor_names_csv": ", ".join(neighbor_names),
            "content_excerpt": metadata.content_excerpt or "",
            "content_source": metadata.content_source or "",
            "content_truncated": "true" if metadata.content_truncated else "",
            "tag_count": f"{tag_count}" if tag_count is not None else "",
            "tag_prompt": metadata.tag_prompt or "",
            "video_extract_count": f"{metadata.video_extract_count}" if metadata.video_extract_count else "",
            "image_date_taken": image.date_taken.isoformat() if image and image.date_taken else "",
            "image_camera_make": (image.camera_make or "") if image else "",
            "image_camera_model": (image.camera_model or "") if image else "",
            "image_lens_model": (image.lens_model or "") if image else "",
            "image_gps_latitude": f"{image.gps_latitude}" if image and image.gps_latitude else "",
            "image_gps_longitude": f"{image.gps_longitude}" if image and image.gps_longitude else "",
            "image_width": f"{image.width}" if image and image.width else "",
            "image_height": f"{image.height}" if image and image.height else "",
            "video_duration_seconds": f"{video.duration_seconds}" if video and video.duration_seconds else "",
            "video_width": f"{video.width}" if video and video.width else "",
            "video_height": f"{video.height}" if video and video.height else "",
            "video_codec": (video.codec or "") if video else "",
            "video_fps": f"{video.fps}" if video and video.fps else "",
        }

    @classmethod
    def get_system_prompt(cls, metadata: FileMetadata, overrides: PromptOverrides | None = None) -> str:
        prompt_type = cls._prompt_type(metadata)
        if overrides:
            override = getattr(overrides.system, prompt_type, None)
            if override and override.strip():
                return override.strip()

        if prompt_type == "image":
            return cls.SYSTEM_PROMPT_IMAGE
        if prompt_type == "video":
            return cls.SYSTEM_PROMPT_VIDEO
        if prompt_type == "document":
            return cls.SYSTEM_PROMPT_DOCUMENT
        return cls.SYSTEM_PROMPT_BASE

    @classmethod
    def get_user_prompt(cls, metadata: FileMetadata, overrides: PromptOverrides | None = None) -> str:
        prompt_type = cls._prompt_type(metadata)
        if overrides:
            override = getattr(overrides.user, prompt_type, None)
            if override and override.strip():
                return cls._render_template(override.strip(), metadata)

        if prompt_type == "image":
            return cls.build_image_prompt(metadata)
        if prompt_type == "video":
            return cls.build_video_prompt(metadata)
        if prompt_type == "document":
            return cls.build_document_prompt(metadata)
        return cls.build_generic_prompt(metadata)

    @classmethod
    def _filename_line(cls, metadata: FileMetadata, label: str) -> str | None:
        if not metadata.include_current_filename:
            return None
        return f"- {label}: {metadata.file_name}"

    @classmethod
    def _append_folder_context(cls, sections: list[str], metadata: FileMetadata) -> None:
        if not metadata.folder_context:
            return
        sections.append("")
        sections.append("## Folder Context")
        sections.append(f"- {metadata.folder_context}")

    @classmethod
    def _append_content_excerpt(cls, sections: list[str], metadata: FileMetadata) -> None:
        if not metadata.content_excerpt:
            return
        sections.append("")
        label = "## Content Excerpt"
        details: list[str] = []
        if metadata.content_source:
            details.append(metadata.content_source)
        details.append(f"{len(metadata.content_excerpt)} chars")
        if metadata.content_truncated:
            details.append("truncated")
        if details:
            label = f"{label} ({', '.join(details)})"
        sections.append(label)
        sections.append(metadata.content_excerpt)

    @classmethod
    def _tag_guidance_lines(cls, metadata: FileMetadata, subject: str) -> list[str]:
        lines: list[str] = []
        tag_count = metadata.tag_count
        if tag_count is None:
            lines.append(f"- Suggest relevant Finder tags for {subject}.")
        elif tag_count <= 0:
            lines.append("- Return an empty tags array.")
        elif tag_count == 1:
            lines.append("- Suggest 1 Finder tag.")
        else:
            lines.append(f"- Suggest up to {tag_count} Finder tags.")
        tag_prompt = (metadata.tag_prompt or "").strip()
        if tag_prompt:
            lines.append(f"- Tag guidance: {tag_prompt}")
        return lines
    
    # ─────────────────────────────────────────────────────────────────────────
    # System Prompts
    # ─────────────────────────────────────────────────────────────────────────
    
    SYSTEM_PROMPT_BASE = """You are an expert file naming specialist trained in Library of Congress Subject Headings, controlled vocabularies, and information retrieval principles.

TASK: Generate an optimal, descriptive filename that aids future retrieval and organization.

NAMING PRINCIPLES:
- Specificity: Distinguish this file from similar files
- Retrievability: Use terms a user would likely search for
- Clarity: Prefer standard terminology over jargon or abbreviations
- Chronology: Include dates only when meaningful to content (event date, publication date, contract date) — not merely when identifiable

RESPONSE RULES:
1. Respond ONLY with valid JSON — no markdown, no explanations outside JSON
2. suggested_name: lowercase, hyphen-separated, NO extension, English only
3. Be concise but precise (typically 2-12 words)

TAG TAXONOMY:
Apply tags following Library of Congress Subject Headings (LCSH) principles — use controlled, standardized terms rather than ad-hoc labels.

TAG FORMAT:
- Title Case, hyphen-separated (e.g., "Web-Development", "Los-Angeles")
- No spaces, no abbreviations, no acronyms unless universally understood (e.g., "API" is acceptable, "ML" is not — use "Machine-Learning")

TAG STRUCTURE (always in this order):
1. Form/Genre (one) — the intellectual or physical type (what it IS)
2. Domain (one) — the broad field or discipline
3. Topic(s) (one or more) — subjects the work is ABOUT, ordered broad → narrow

TAGGING PRINCIPLES:
- Tags CLASSIFY; the filename IDENTIFIES — they are complementary, not redundant
- Topics describe "aboutness" — subjects, themes, concepts — NOT titles, names, or unique identifiers
- Never include the specific title, filename, or proper-noun identifiers as tags
- Prefer terms that would match OTHER similar items (enabling browse/discovery)
- A good test: would this tag apply to multiple files, or only this one? Tags should generally apply to many.

Examples:
- Screenshot of a book cover:
  Filename: "monster-autobiography-la-gang-member-sanyika-shakur-screenshot"
  Tags: ["Screenshot", "Books", "Autobiography", "Gangs", "Los-Angeles"]

- PDF of a consulting invoice:
  Filename: "2024-03-15-invoice-acme-corp-web-development"
  Tags: ["Invoice", "Business", "Consulting", "Web-Development"]

- Photo from a trip:
  Filename: "kyoto-fushimi-inari-shrine-torii-gates-morning"
  Tags: ["Photograph", "Travel", "Japan", "Shinto-Shrines", "Architecture"]"""

    SYSTEM_PROMPT_IMAGE = SYSTEM_PROMPT_BASE + """

IMAGE CATALOGUING (following VRA Core / Getty vocabulary standards):

Analysis priorities:
1. Primary subject — main focus (person, object, scene, concept)
2. Action/state — what is happening (portrait, event, diagram)
3. Context — where/when captured (location, setting, era)
4. Purpose — screenshot, photograph, diagram, artwork, meme
5. Distinguishing features — what makes this image unique

For multiple images: Identify the common thread and synthesize ONE cohesive name.
For visible text: Include key terms when they aid retrieval."""

    SYSTEM_PROMPT_VIDEO = SYSTEM_PROMPT_BASE + """

MOVING IMAGE CATALOGUING (following FIAF / PBCore standards):

Analysis priorities:
1. Content type — screen recording, personal footage, tutorial, presentation
2. Primary subject — main focus across frames
3. Action/narrative — what is being demonstrated or occurring
4. Context — software shown, location, event
5. Temporal span — single scene or multiple segments

Frame interpretation:
- Infer overall content from sample frames
- Note consistency or variation to gauge scope
- Identify on-screen text, UI elements, or watermarks indicating source"""

    SYSTEM_PROMPT_DOCUMENT = SYSTEM_PROMPT_BASE + """

DOCUMENT CATALOGUING (following Library of Congress standards):

Analysis priorities:
1. Document type — invoice, report, letter, contract, notes, form
2. Key entities — names, organizations, identifiers present
3. Temporal markers — dates, periods, deadlines
4. Subject matter — primary topic or transaction
5. Purpose — reference, correspondence, record-keeping

For messy filenames: Extract any meaningful components.
For business documents: Consider date-type-subject ordering."""

    # ─────────────────────────────────────────────────────────────────────────
    # User Prompts
    # ─────────────────────────────────────────────────────────────────────────
    
    @classmethod
    def build_image_prompt(cls, metadata: FileMetadata) -> str:
        """
        Build prompt for image files.
        
        Images get the richest prompts since vision models can analyze them.
        """
        sections = [
            "Analyze this image and suggest a descriptive filename.",
            "",
            "## Current File",
        ]
        filename_line = cls._filename_line(metadata, "Filename")
        if filename_line:
            sections.append(filename_line)
        sections.append(f"- Size: {metadata.size_human}")
        if metadata.parent_folder_name:
            sections.append(f"- Folder: {metadata.parent_folder_name}")
        cls._append_folder_context(sections, metadata)
        
        # Add image-specific metadata
        if metadata.image:
            img = metadata.image
            sections.append("")
            sections.append("## Image Metadata")
            
            if img.date_taken:
                sections.append(f"- Date taken: {img.date_taken.strftime('%Y-%m-%d %H:%M')}")
            
            if img.camera_make or img.camera_model:
                camera = " ".join(filter(None, [img.camera_make, img.camera_model]))
                sections.append(f"- Camera: {camera}")
            
            if img.lens_model:
                sections.append(f"- Lens: {img.lens_model}")
            
            if img.focal_length:
                sections.append(f"- Focal length: {img.focal_length}mm")
            
            if img.aperture:
                sections.append(f"- Aperture: f/{img.aperture}")
            
            if img.iso:
                sections.append(f"- ISO: {img.iso}")
            
            if img.gps_latitude and img.gps_longitude:
                sections.append(f"- GPS coordinates: {img.gps_latitude:.4f}, {img.gps_longitude:.4f}")
            
            if img.width and img.height:
                orientation = "landscape" if img.width > img.height else "portrait" if img.height > img.width else "square"
                sections.append(f"- Dimensions: {img.width}x{img.height} ({orientation})")
        
        # Add neighbor context
        if metadata.neighbor_names:
            sections.append("")
            sections.append("## Other Files in Folder (for naming convention reference)")
            for name in metadata.neighbor_names[:5]:
                sections.append(f"- {name}")

        cls._append_content_excerpt(sections, metadata)
        
        # Instructions
        sections.extend([
            "",
            "## Your Task",
            "1. Describe what you see in the image",
            "2. Identify the main subject, scene, or activity",
            "3. Consider the metadata for additional context (date, location, camera)",
            "4. Match the naming style of neighboring files if a pattern exists",
        ])
        tag_lines = cls._tag_guidance_lines(metadata, "this image")
        if tag_lines:
            sections.append("")
            sections.append("## Tag Guidance")
            sections.extend(tag_lines)
        
        return "\n".join(sections)
    
    @classmethod
    def build_video_prompt(cls, metadata: FileMetadata) -> str:
        """
        Build prompt for video files.
        
        Videos typically can't be analyzed visually, so we rely heavily on
        metadata and filename patterns.
        """
        sections = [
            "Suggest a descriptive filename for this video based on the available information.",
            "",
            "## Current File",
        ]
        filename_line = cls._filename_line(metadata, "Filename")
        if filename_line:
            sections.append(filename_line)
        sections.extend([
            f"- Size: {metadata.size_human}",
            f"- Created: {metadata.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"- Modified: {metadata.modified_at.strftime('%Y-%m-%d %H:%M')}",
        ])
        if metadata.parent_folder_name:
            sections.append(f"- Folder: {metadata.parent_folder_name}")
        cls._append_folder_context(sections, metadata)
        
        # Add video-specific metadata
        if metadata.video:
            vid = metadata.video
            sections.append("")
            sections.append("## Video Metadata")
            
            if vid.duration_seconds:
                mins, secs = divmod(int(vid.duration_seconds), 60)
                hours, mins = divmod(mins, 60)
                if hours > 0:
                    duration_str = f"{hours}h {mins}m {secs}s"
                elif mins > 0:
                    duration_str = f"{mins}m {secs}s"
                else:
                    duration_str = f"{secs}s"
                sections.append(f"- Duration: {duration_str}")
                
                # Add duration context
                if vid.duration_seconds < 30:
                    sections.append("  (Very short - likely a clip, reaction, or quick capture)")
                elif vid.duration_seconds < 180:
                    sections.append("  (Short - likely a clip or highlight)")
                elif vid.duration_seconds < 1800:
                    sections.append("  (Medium - could be a segment or short video)")
                else:
                    sections.append("  (Long - likely a full recording or movie)")
            
            if vid.width and vid.height:
                # Determine format type
                aspect = vid.width / vid.height if vid.height else 0
                if aspect > 1.7:
                    format_hint = "widescreen/cinematic"
                elif aspect < 0.7:
                    format_hint = "vertical/mobile"
                elif 0.9 < aspect < 1.1:
                    format_hint = "square"
                else:
                    format_hint = "standard"
                
                # Resolution label
                if vid.height >= 2160:
                    res_label = "4K"
                elif vid.height >= 1080:
                    res_label = "1080p"
                elif vid.height >= 720:
                    res_label = "720p"
                else:
                    res_label = "SD"
                
                sections.append(f"- Resolution: {vid.width}x{vid.height} ({res_label}, {format_hint})")
            
            if vid.codec:
                sections.append(f"- Codec: {vid.codec}")
            
            if vid.fps:
                fps_note = ""
                if vid.fps > 50:
                    fps_note = " (slow-motion capable)"
                elif vid.fps < 25:
                    fps_note = " (cinematic/timelapse)"
                sections.append(f"- Frame rate: {vid.fps} fps{fps_note}")
            
            if vid.creation_time:
                sections.append(f"- Recording date: {vid.creation_time.strftime('%Y-%m-%d %H:%M')}")
        
        # Filename analysis
        if metadata.include_current_filename:
            sections.append("")
            sections.append("## Filename Analysis")

            original_stem = Path(metadata.file_name).stem

            # Check for common patterns in original filename
            patterns_found = []

            import re
            if re.search(r'IMG_\d+|DSC\d+|MOV_\d+|VID_\d+', original_stem):
                patterns_found.append("Camera auto-generated name (not descriptive)")
            if re.search(r'screen.?record|capture|screenshot', original_stem, re.I):
                patterns_found.append("Likely a screen recording")
            if re.search(r'zoom|meet|teams|webex', original_stem, re.I):
                patterns_found.append("Likely a video call recording")
            if re.search(r'\d{4}[-_]?\d{2}[-_]?\d{2}', original_stem):
                patterns_found.append("Contains a date")
            if re.search(r'edit|final|v\d+|draft', original_stem, re.I):
                patterns_found.append("Appears to be an edited/versioned file")

            if patterns_found:
                for pattern in patterns_found:
                    sections.append(f"- {pattern}")
            else:
                sections.append(f"- Original name: {original_stem}")
        
        # Add neighbor context
        if metadata.neighbor_names:
            sections.append("")
            sections.append("## Other Files in Folder")
            for name in metadata.neighbor_names[:5]:
                sections.append(f"- {name}")

        cls._append_content_excerpt(sections, metadata)
        
        # Instructions
        filename_instruction = (
            "1. Analyze the filename and metadata for clues about content"
            if metadata.include_current_filename
            else "1. Analyze the metadata and context for clues about content"
        )
        name_instruction = (
            "3. If the current name has meaningful parts, preserve or improve them"
            if metadata.include_current_filename
            else "3. Use the available context to craft a clear descriptive name"
        )
        video_note = "NOTE: You cannot see the video content. Base your suggestion on metadata and context only."
        if metadata.video_extract_count and metadata.video_extract_count > 0:
            video_note = (
                f"NOTE: You will receive {metadata.video_extract_count} extracted video frames. "
                "Use them as visual context."
            )

        sections.extend([
            "",
            "## Your Task",
            filename_instruction,
            "2. Consider the duration and format (screen recording? phone video? professional?)",
            name_instruction,
            "4. Match the naming style of neighboring files if appropriate",
            "",
            video_note,
        ])
        tag_lines = cls._tag_guidance_lines(metadata, "this video")
        if tag_lines:
            sections.append("")
            sections.append("## Tag Guidance")
            sections.extend(tag_lines)
        
        return "\n".join(sections)
    
    @classmethod
    def build_document_prompt(cls, metadata: FileMetadata) -> str:
        """
        Build prompt for document files (PDF, Office, text).
        
        Documents are analyzed based on filename patterns, metadata, and file type.
        """
        sections = [
            "Suggest a descriptive filename for this document based on the available information.",
            "",
            "## Current File",
        ]
        filename_line = cls._filename_line(metadata, "Filename")
        if filename_line:
            sections.append(filename_line)
        sections.extend([
            f"- Type: {metadata.extension.upper()} document",
            f"- Size: {metadata.size_human}",
            f"- Created: {metadata.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"- Last modified: {metadata.modified_at.strftime('%Y-%m-%d %H:%M')}",
        ])
        if metadata.parent_folder_name:
            sections.append(f"- Folder: {metadata.parent_folder_name}")
        cls._append_folder_context(sections, metadata)
        
        # Document type hints
        sections.append("")
        sections.append("## Document Type Analysis")
        
        ext = metadata.extension.lower()
        type_hints = {
            ".pdf": "PDF - could be any document type (report, form, ebook, scan, etc.)",
            ".docx": "Word document - typically letters, reports, essays, or documentation",
            ".doc": "Legacy Word document - typically letters, reports, essays",
            ".xlsx": "Excel spreadsheet - typically data, budgets, lists, or calculations",
            ".xls": "Legacy Excel spreadsheet - typically data, budgets, lists",
            ".pptx": "PowerPoint presentation - typically slides for meetings or talks",
            ".ppt": "Legacy PowerPoint presentation",
            ".txt": "Plain text file - notes, logs, code, or simple documents",
            ".md": "Markdown file - documentation, notes, or formatted text",
            ".rtf": "Rich text file - formatted document, often exported from other apps",
            ".csv": "CSV file - tabular data, exports, or data transfers",
        }
        sections.append(f"- {type_hints.get(ext, f'{ext} file')}")

        cls._append_content_excerpt(sections, metadata)
        
        # Filename analysis
        if metadata.include_current_filename:
            sections.append("")
            sections.append("## Current Filename Analysis")

            original_stem = Path(metadata.file_name).stem

            import re

            # Extract potential meaningful parts
            observations = []

            # Check for dates
            date_match = re.search(r'(\d{4}[-_/]?\d{2}[-_/]?\d{2}|\d{2}[-_/]\d{2}[-_/]\d{4})', original_stem)
            if date_match:
                observations.append(f"Contains date: {date_match.group(1)}")

            # Check for version indicators
            version_match = re.search(r'(v\d+|version.?\d+|final|draft|revised|updated)', original_stem, re.I)
            if version_match:
                observations.append(f"Version indicator: {version_match.group(1)}")

            # Check for copy indicators
            if re.search(r'copy|копия|\(\d+\)|duplicate', original_stem, re.I):
                observations.append("Appears to be a copy/duplicate")

            # Check for common document types in name
            doc_type_match = re.search(
                r'(invoice|receipt|report|letter|resume|cv|contract|agreement|'
                r'proposal|presentation|meeting|notes|minutes|budget|schedule|'
                r'plan|guide|manual|handbook|policy|form|application|certificate|'
                r'transcript|statement|summary|analysis|review)',
                original_stem, re.I
            )
            if doc_type_match:
                observations.append(f"Document type indicator: {doc_type_match.group(1)}")

            # Check for names/entities
            if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', original_stem):
                observations.append("May contain person or company names")

            # Check for auto-generated names
            if re.search(r'^(document|file|scan|img|untitled|new)', original_stem, re.I):
                observations.append("Generic/auto-generated name (needs better description)")

            if observations:
                for obs in observations:
                    sections.append(f"- {obs}")
            else:
                sections.append(f"- Filename: \"{original_stem}\" (analyze for meaningful content)")
        
        # Size-based hints
        sections.append("")
        sections.append("## Size Analysis")
        
        size_mb = metadata.size_bytes / (1024 * 1024)
        if ext == ".pdf":
            if size_mb > 10:
                sections.append("- Large PDF: Likely contains images, scans, or many pages")
            elif size_mb < 0.1:
                sections.append("- Small PDF: Likely a simple document or form")
            else:
                sections.append("- Medium PDF: Standard document size")
        elif ext in [".xlsx", ".xls"]:
            if size_mb > 5:
                sections.append("- Large spreadsheet: Likely contains significant data")
        elif ext in [".pptx", ".ppt"]:
            if size_mb > 20:
                sections.append("- Large presentation: Likely contains many slides or embedded media")
        
        # Add neighbor context
        if metadata.neighbor_names:
            sections.append("")
            sections.append("## Other Files in Folder")
            for name in metadata.neighbor_names[:5]:
                sections.append(f"- {name}")
        
        # Instructions
        filename_instruction = (
            "1. Analyze the current filename for any meaningful information"
            if metadata.include_current_filename
            else "1. Analyze the metadata for any meaningful information"
        )
        context_instruction = (
            "4. If it contains useful info (dates, types, names), preserve and organize it"
            if metadata.include_current_filename
            else "4. Use any available context to form a clear descriptive name"
        )
        if metadata.content_excerpt:
            note_line = "NOTE: A content excerpt is included above. Use it as the primary signal."
        else:
            note_line = (
                "NOTE: You cannot read the document content. Base your suggestion on filename and metadata only."
                if metadata.include_current_filename
                else "NOTE: You cannot read the document content. Base your suggestion on metadata and context only."
            )
        sections.extend([
            "",
            "## Your Task",
            filename_instruction,
            "2. Consider the document type and typical naming conventions",
            "3. If it's auto-generated or messy, suggest a cleaner descriptive name",
            context_instruction,
            "5. Match the naming style of neighboring files if a pattern exists",
            "",
            note_line,
        ])
        tag_lines = cls._tag_guidance_lines(metadata, "this document")
        if tag_lines:
            sections.append("")
            sections.append("## Tag Guidance")
            sections.extend(tag_lines)
        
        return "\n".join(sections)
    
    @classmethod
    def get_prompt_for_file(
        cls,
        metadata: FileMetadata,
        overrides: PromptOverrides | None = None
    ) -> tuple[str, str]:
        """
        Get the appropriate system and user prompts for a file.
        
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        return cls.get_system_prompt(metadata, overrides), cls.get_user_prompt(metadata, overrides)
    
    @classmethod
    def build_generic_prompt(cls, metadata: FileMetadata) -> str:
        """Build a generic prompt for unknown file types."""
        sections = [
            "Suggest a descriptive filename for this file.",
            "",
            "## File Information",
        ]
        filename_line = cls._filename_line(metadata, "Current name")
        if filename_line:
            sections.append(filename_line)
        sections.extend([
            f"- Type: {metadata.extension}",
            f"- Size: {metadata.size_human}",
            f"- Created: {metadata.created_at.strftime('%Y-%m-%d %H:%M')}",
        ])
        if metadata.parent_folder_name:
            sections.append(f"- Folder: {metadata.parent_folder_name}")
        cls._append_folder_context(sections, metadata)

        cls._append_content_excerpt(sections, metadata)
        
        if metadata.neighbor_names:
            sections.append("")
            sections.append("## Other Files in Folder")
            for name in metadata.neighbor_names[:5]:
                sections.append(f"- {name}")
        
        prompt_line = (
            "Suggest a clear, descriptive name based on the current filename and context."
            if metadata.include_current_filename
            else "Suggest a clear, descriptive name based on the available context."
        )
        sections.extend(["", prompt_line])
        tag_lines = cls._tag_guidance_lines(metadata, "this file")
        if tag_lines:
            sections.append("")
            sections.append("## Tag Guidance")
            sections.extend(tag_lines)
        
        return "\n".join(sections)
