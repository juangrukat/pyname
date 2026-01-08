# Pynamer



https://github.com/user-attachments/assets/5c551a24-71bd-4e56-9b5f-6cc53e949496



A macOS-native application that uses vision-capable LLMs to intelligently rename files based on their content, metadata, and surrounding context.

![macOS](https://img.shields.io/badge/macOS-13.0+-blue?logo=apple)
![Python](https://img.shields.io/badge/Python-3.11+-green?logo=python)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- 🖼️ **Vision-Powered Renaming** — Analyzes image content using local or cloud LLMs
- 📁 **Smart Context** — Uses neighboring filenames to match your existing naming conventions
- 🏷️ **Automatic Tagging** — Applies relevant Finder tags based on content
- 🔄 **Full Undo Support** — Every operation is logged and reversible
- 🎨 **12 Case Styles** — From `kebab-case` to `PascalCase` and everything in between
- ☁️ **OpenAI-First** — Optimized for OpenAI vision models with optional local providers
- 📊 **Rich Metadata** — Extracts EXIF, GPS, video info to improve suggestions
- 🧾 **Optional Content Extraction** — Includes text/PDF excerpts with configurable limits
- 🧭 **Prompt Preview** — Inspect the exact prompts sent to the model

## Quick Start (OpenAI)

### Prerequisites

```bash
# Install Python 3.11+
brew install python@3.11

# Optional: Install tag CLI for Finder tags
brew install tag

# Optional: Install ffmpeg for video metadata
brew install ffmpeg
```

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/pynamer.git
cd pynamer

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configure OpenAI

Create or edit `data/config.json` with your OpenAI settings:

```json
{
    "llm": {
        "provider": "openai",
        "model": "gpt-5-nano",
        "api_base": "https://api.openai.com/v1",
        "api_key": "sk-..."
    }
}
```

### Running

```bash
# Start the application
python main.py
```

## Usage

### Basic Workflow

1. **Select Files** — Click the drop zone or drag files into the window
2. **Generate Names** — Click "Generate Names" to analyze files with AI
3. **Review & Edit** — Check suggestions, edit names inline if needed
4. **Apply** — Click "Apply Selected" to rename files
5. **Undo** — Made a mistake? Click "Undo Last" to restore original names

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `⌘ + O` | Open file picker |
| `⌘ + G` | Generate names |
| `⌘ + Enter` | Apply selected |
| `⌘ + Z` | Undo last batch |
| `⌘ + ,` | Open settings |
| `Escape` | Cancel processing |

### Case Styles

| Style | Example |
|-------|---------|
| `camelCase` | `sunsetBeachPhoto` |
| `capitalCase` | `Sunset Beach Photo` |
| `constantCase` | `SUNSET_BEACH_PHOTO` |
| `dotCase` | `sunset.beach.photo` |
| `kebabCase` | `sunset-beach-photo` |
| `noCase` | `sunset beach photo` |
| `pascalCase` | `SunsetBeachPhoto` |
| `pascalSnakeCase` | `Sunset_Beach_Photo` |
| `pathCase` | `sunset/beach/photo` |
| `sentenceCase` | `Sunset beach photo` |
| `snakeCase` | `sunset_beach_photo` |
| `trainCase` | `Sunset-Beach-Photo` |

## Configuration

### OpenAI (Recommended)

```json
{
    "llm": {
        "provider": "openai",
        "model": "gpt-5-nano",
        "api_base": "https://api.openai.com/v1",
        "api_key": "sk-..."
    }
}
```

### Alternative Providers

#### Ollama (Local)

```json
{
    "llm": {
        "provider": "ollama",
        "model": "llava:latest",
        "api_base": "http://localhost:11434"
    }
}
```

#### LM Studio (Local - OpenAI Compatible)

```json
{
    "llm": {
        "provider": "lmstudio",
        "model": "llama-3.1-8b-instruct",
        "api_base": "http://localhost:1234/v1",
        "api_key": null
    }
}
```

### Configuration File

Settings are stored in `data/config.json`:

```json
{
    "llm": {
        "provider": "ollama",
        "model": "llava:latest",
        "api_base": "http://localhost:11434",
        "api_key": null,
        "image_mode": "auto",
        "temperature": 0.3,
        "max_tokens": 500,
        "timeout_seconds": 60
    },
    "processing": {
        "case_style": "kebabCase",
        "preserve_extension": true,
        "include_date_prefix": false,
        "date_format": "%Y-%m-%d",
        "include_current_filename": true,
        "include_parent_folder": false,
        "include_neighbor_names": true,
        "neighbor_context_count": 3,
        "folder_context_depth": 1,
        "include_file_content": false,
        "content_max_chars": 2000,
        "video_extract_count": 3,
        "max_concurrency": 1,
        "auto_apply_tags": true,
        "tag_count": 5,
        "tag_prompt": "",
        "tag_mode": "append",
        "drop_folder_depth": 1,
        "dry_run": true
    },
    "confirm_before_apply": true,
    "show_reasoning": true,
    "show_prompt_preview": false,
    "prompt_preview_chars": 2000,
    "prompts": {
        "system": {
            "image": null,
            "video": null,
            "document": null,
            "generic": null
        },
        "user": {
            "image": null,
            "video": null,
            "document": null,
            "generic": null
        }
    }
}
```

You can edit settings directly in the app (⌘ + ,) or by editing `data/config.json`. Changes are saved immediately and reused next launch, and the UI maps 1:1 to these keys.

Prompt overrides are optional. Leave values as `null` to use built-in defaults.

### Customizing What Gets Sent

These controls let you tune how much context the model sees and what influences the final name:

- `include_current_filename` includes the existing filename in the prompt (useful for keeping numbering or prefix styles).
- `include_parent_folder` and `folder_context_depth` add folder names (0 disables, 1 = parent, 2 = grandparent, etc.).
- `include_neighbor_names` + `neighbor_context_count` include nearby filenames to mirror your current naming conventions.
- `include_file_content` + `content_max_chars` add text/PDF excerpts for document-aware naming.
- `video_extract_count` samples video frames and sends them for vision analysis (OpenAI only, uses ffmpeg).
- `max_tokens` caps the model's output length (not the input prompt size).
- `case_style`, `include_date_prefix`, and `date_format` control the final name format.

### Tags & Prompt Overrides

- `tag_count`, `tag_prompt`, and `tag_mode` control Finder tag suggestions and how they are applied.
- `prompts.system.*` and `prompts.user.*` let you override prompts per file type (`image`, `video`, `document`, `generic`).
- `show_prompt_preview` + `prompt_preview_chars` reveal the exact prompt payloads in the results list.

## Supported File Types

| Type | Extensions | AI Analysis | Metadata |
|------|------------|-------------|----------|
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.heic`, `.heif`, `.tiff`, `.bmp` | ✅ Vision | EXIF, GPS, Camera |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.m4v` | 📊 Metadata + optional frame extracts | Duration, Resolution, Codec |
| Documents | `.pdf`, `.doc`, `.docx`, `.ppt`, `.pptx`, `.xls`, `.xlsx`, `.rtf`, `.odt`, `.ods`, `.odp`, `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.yml`, `.html`, `.htm`, `.xml`, `.rss` | 📊 Metadata + optional text excerpt | Size, Dates, Content (text/PDF/Office) |

## Project Structure

```
pynamer/
├── main.py                    # Entry point
├── api.py                     # pywebview JS bridge
├── core/
│   ├── models.py              # Pydantic data models
│   ├── config.py              # Configuration management
│   ├── llm.py                 # LLM client factory
│   ├── providers/             # LLM provider implementations
│   │   ├── ollama.py
│   │   ├── openai.py
│   │   └── anthropic.py
│   ├── metadata.py            # File metadata extraction
│   ├── processor.py           # Main processing pipeline
│   ├── safety.py              # Filename sanitization
│   ├── transformer.py         # Case transformations
│   ├── tagging.py             # macOS Finder tags
│   └── history.py             # Undo/redo system
├── assets/
│   ├── index.html
│   ├── ui.js
│   └── style.css
└── data/
    ├── config.json            # User configuration
    └── history.json           # Operation history
```

## Privacy & Security

- **No Telemetry** — The app doesn't collect or send usage data
- **API Keys** — Stored locally in `config.json` (add to `.gitignore`)
- **File Access** — Only accesses files you explicitly select
- **Provider Choice** — Use OpenAI for cloud or Ollama/LM Studio for local processing

## Troubleshooting

<details>
<summary><strong>Ollama connection refused</strong></summary>

Make sure Ollama is running:
```bash
ollama serve
```

Check if it's accessible:
```bash
curl http://localhost:11434/api/tags
```
</details>

<details>
<summary><strong>Vision model not working</strong></summary>

Ensure you have a vision-capable model:
```bash
ollama pull llava
```

Check available models:
```bash
ollama list
```
</details>

<details>
<summary><strong>Tags not being applied</strong></summary>

Install the `tag` CLI:
```bash
brew install tag
```

Verify it works:
```bash
tag --help
```
</details>

<details>
<summary><strong>Video metadata not extracted</strong></summary>

Install ffmpeg:
```bash
brew install ffmpeg
```

Verify ffprobe works:
```bash
ffprobe --version
```
</details>

<details>
<summary><strong>Video frame extracts not showing</strong></summary>

Ensure ffmpeg is installed (not just ffprobe):
```bash
brew install ffmpeg
```
</details>

<details>
<summary><strong>PDF content not showing</strong></summary>

Install the PDF parser:
```bash
pip install pypdf
```
</details>

<details>
<summary><strong>Office document content not showing</strong></summary>

Install the document parser:
```bash
pip install markitdown
```

Legacy `.doc`/`.rtf`/`.odt` files use macOS `textutil`.
</details>

<details>
<summary><strong>HEIC images not loading</strong></summary>

Install HEIC support for Pillow:
```bash
pip install pillow-heif
```
</details>

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Building for Distribution

```bash
# Install pyinstaller
pip install pyinstaller

# Build standalone app
pyinstaller --windowed --name "Pynamer" --icon assets/icon.jpeg main.py
```

## Roadmap

- [ ] Batch processing with progress persistence
- [ ] Custom naming templates
- [ ] Folder watching mode
- [ ] Quick Look preview integration
- [ ] Export/import naming rules
- [ ] Multi-language support

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## License

GNU General Public License (GPL)

## Acknowledgments

- [pywebview](https://pywebview.flowrl.com/) — Native GUI framework
- [Ollama](https://ollama.ai/) — Local LLM runtime
- [Pydantic](https://docs.pydantic.dev/) — Data validation
- [tag](https://github.com/jdberry/tag) — macOS tagging CLI
