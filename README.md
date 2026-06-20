# TinyImage

Batch image compression tool with parallel processing, archive support, and format conversion.

## Features

- **Configurable parallel processing** — uses `ProcessPoolExecutor` with `--workers N` (default: `os.cpu_count()`), or `--sequential` for single-threaded mode
- **Archive support** — processes images inside ZIP and 7z archives, preserving internal structure
- **Encrypted archive detection** — password-protected archives are silently skipped
- **Format conversion** — PNG → WebP and JPEG → WebP via `--png-to-webp` / `--jpg-to-webp`
- **Metadata preservation** — ICC profiles and EXIF data are kept in output
- **No-enlargement guarantee** — if compressed output is larger, the original is copied as-is
- **Recursive directory scanning** — processes images in nested subdirectories, mirroring structure in output
- **Dry-run safety** — never modifies originals unless `--delete-original` or `--soft-delete-original` is explicitly set

## Installation

```powershell
& "venv/Scripts/Activate.ps1"
pip install -r requirements.txt
```

## Usage

```powershell
python main.py
python main.py --input my_photos --output compressed
python main.py --dir single_folder
python main.py --png-to-webp --jpg-to-webp
python main.py --delete-original
python main.py --soft-delete-original
```

### Options

| Argument | Default | Description |
|---|---|---|
| `--input DIR` | `input` | Input directory |
| `--output DIR` | `output` | Output directory |
| `--dir DIR` | — | Set both input and output to the same directory (cannot be used with `--input` or `--output`) |
| `--png-to-webp` | `false` | Convert PNG images to WebP |
| `--jpg-to-webp` | `false` | Convert JPEG images to WebP |
| `--sequential` | `false` | Disable multiprocessing, process images one by one |
| `--workers N` | CPU count | Maximum parallel workers (mutually exclusive with `--sequential`) |
| `--delete-original` | `false` | Permanently delete original files after compression |
| `--soft-delete-original` | `false` | Move original files to trash (requires `send2trash`, mutually exclusive with `--delete-original`) |

## Input / Output Structure

Directories and files are processed recursively. Output mirrors the input directory structure:

```
input/
  vacation.jpg          → output/vacation [minify].jpg
  documents/
    report.png          → output/documents/report [minify].png
    assets/
      icon.webp         → output/documents/assets/icon [minify].webp
```

Files containing `[minify]` in the name are automatically skipped to avoid re-processing.

## Compression Parameters

| Format | File-based | Stream-based (ZIP in-memory) |
|---|---|---|
| JPEG | `quality=80, progressive=True, optimize=True` | same |
| PNG | `compress_level=9` | same |
| WebP | `quality=80, method=6` | same |

## Testing

```powershell
& "venv/Scripts/Activate.ps1"
python -m pytest tests/ -v
```
