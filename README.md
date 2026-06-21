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
python main.py --override
python main.py --quality 85 --png-level 7
```

### Options

| Argument | Default | Description |
|---|---|---|
| `--input DIR` | `input` | Input directory (env: `TINYIMAGE_INPUT`) |
| `--output DIR` | `output` | Output directory (env: `TINYIMAGE_OUTPUT`) |
| `--dir DIR` | — | Set both input and output to the same directory (cannot be used with `--input` or `--output`) |
| `--png-to-webp` | `false` | Convert PNG images to WebP |
| `--jpg-to-webp` | `false` | Convert JPEG images to WebP |
| `--override` | `false` | Override `[minify]` check and force re-compression |
| `--quality N` | `80` | JPEG/WebP compression quality (env: `TINYIMAGE_QUALITY`) |
| `--png-level N` | `9` | PNG compress level 0-9 (env: `TINYIMAGE_PNG_LEVEL`) |
| `--webp-method N` | `6` | WebP compression method 0-6 (env: `TINYIMAGE_WEBP_METHOD`) |
| `--jpeg-progressive` | `true` | Enable JPEG progressive encoding (env: `TINYIMAGE_JPEG_PROGRESSIVE`) |
| `--sequential` | `false` | Disable multiprocessing, process images one by one |
| `--workers N` | CPU count | Maximum parallel workers (mutually exclusive with `--sequential`) |
| `--delete-original` | `false` | Permanently delete original files after compression |
| `--soft-delete-original` | `false` | Move original files to trash (requires `send2trash`, mutually exclusive with `--delete-original`) |

### .env 配置

複製 `.env.example` 為 `.env` 即可配置，不需手動設定系統環境變數：

```powershell
cp .env.example .env
# 編輯 .env 修改數值後直接執行
python main.py                       # 自動載入 .env
python main.py --quality 90          # CLI 優先於 .env
```

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
| PNG | `compress_level=9` | `compress_level=3` (less aggressive) |
| WebP | `quality=80, method=6` | `quality=80, method=4` (faster) |

Numbers above are defaults; all are overridable via `--quality` / `--png-level` / `--webp-method` CLI flags or their corresponding environment variables.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TINYIMAGE_INPUT` | `input` | Default for `--input` |
| `TINYIMAGE_OUTPUT` | `output` | Default for `--output` |
| `TINYIMAGE_QUALITY` | `80` | Default for `--quality` |
| `TINYIMAGE_PNG_LEVEL` | `9` | Default for `--png-level` |
| `TINYIMAGE_WEBP_METHOD` | `6` | Default for `--webp-method` |
| `TINYIMAGE_JPEG_PROGRESSIVE` | `True` | Default for `--jpeg-progressive` |
| `TINYIMAGE_SUFFIX` | `[minify]` | Output filename marker |
| `TINYIMAGE_IMG_EXTS` | `.jpg,.jpeg,.png,.webp` | Processed image extensions (comma-separated) |
| `TINYIMAGE_ARC_EXTS` | `.zip,.7z` | Processed archive extensions (comma-separated) |
| `TINYIMAGE_PNG_LEVEL_STREAM` | `3` | ZIP in-memory PNG compression level |
| `TINYIMAGE_WEBP_METHOD_STREAM` | `4` | ZIP in-memory WebP compression method |

## Testing

```powershell
& "venv/Scripts/Activate.ps1"
python -m pytest tests/ -v
```
