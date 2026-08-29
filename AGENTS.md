# TinyImage

> AI 回覆語言：**繁體中文**

Single-file batch image compression tool (`main.py`, ~935 lines). Python 3.14, venv at `venv/`.

## Setup

```powershell
& "venv/Scripts/Activate.ps1"
pip install -r requirements.txt   # or: pip install -r requirements-dev.txt (includes pytest, send2trash)
```

## Commands

```powershell
python main.py                                   # process input/ -> output/
python main.py --input my_photos --output compressed
python main.py --dir "C:\path\to\folder"         # input=output single dir
python main.py --file photo.jpg                  # single file (outputs to cwd or --output)
python main.py --files a.jpg b.png               # multiple files
python main.py --png-to-webp --jpg-to-webp       # format conversion
python main.py --delete-original                  # permanently delete originals
python main.py --soft-delete-original            # move to trash (requires send2trash)
python main.py --override                        # re-compress files already marked [minify]
python main.py --show-config                     # display current config with source priority
python main.py --sequential                      # single-threaded (no multiprocessing)
python main.py --workers 4                       # limit parallel workers
python main.py --quality 85 --png-level 7        # override compression params
python main.py --watch                           # poll input/ for changes until Ctrl+C
python main.py --watch --watch-interval 5
python main.py --gui                             # launch GUI (customtkinter)
python -m gui.gui                                # launch GUI directly
```

All params follow **CLI > .env > default** priority. See `--help` or the argparse block in `main.py` for the full list.

## Architecture

- **Single file**: all logic lives in `main.py`. The GUI (`gui/gui.py`) imports it as a module via `sys.path` manipulation.
- **Parallelism**: `ProcessPoolExecutor` with `--workers N` (default: `os.cpu_count()`). `--sequential` disables it. Because multiprocessing pickles callables, compression functions must remain at module level.
- **Archives**: ZIP/7z archives processed sequentially per archive, parallel per image inside. Encrypted archives silently skipped with `[Skipped]`.
- **Skip logic**: files containing `[minify]` in the name are skipped (use `--override` to force). Output naming: `{name} [minify]{ext}`.
- **No-enlargement guarantee**: if compressed output is larger, original is copied as-is with original extension.
- **Stream-based compression** (ZIP in-memory) uses lower defaults for speed: PNG `compress_level=3`, WebP `method=4`. Override via `--png-level-stream` / `--webp-method-stream`.
- **Watch mode**: polls every N seconds, processes new/modified files until Ctrl+C (graceful shutdown).
- `.env` is auto-loaded at module import via `load_dotenv()` — no manual env setup needed.

## Windows-only code

`is_hidden()` in `main.py` uses `ctypes.windll.kernel32.GetFileAttributesW`. The tool is Windows-only as written.

## Testing

```powershell
python -m pytest tests/ -v
```

Tests in `tests/test_main.py` (86 tests). `tests/conftest.py` provides fixtures (`tmp_output_dir`, `rgb_image`, `rgba_image`, `jpeg_bytes`, `png_bytes`, `webp_bytes`, `jpeg_file`, `png_file`, `webp_file`, `saved_globals`).

**Quirks**:
- `saved_globals` fixture snapshots/restores module-level constants (`SUFFIX`, `PNG_LEVEL_STREAM`, `WEBP_METHOD_STREAM`, `IMG_EXTENSIONS`, `ARC_EXTENSIONS`) — tests that modify these globals depend on this fixture.
- No linter, formatter, or CI is configured.
- Tests are pure unit tests (no network, no external services).

## File sync rules

When modifying `main.py` or `gui/gui.py`, you **must** also update per `.opencode/instructions.md`:
- CLI args → `AGENTS.md` Commands + `README.md` Options table
- Env vars → `AGENTS.md` (this file), `README.md` Environment Variables, `.env.example`
- Imports → `requirements.txt` / `requirements-dev.txt` + both READMEs
- Test count → update count in this file's Testing section
- Architecture changes → `README.md` Features + `AGENTS.md` Architecture

After changes, verify:
```powershell
python -m pytest tests/ -v
python main.py --help
python main.py --show-config
```

## Layout

| Path | Purpose |
|---|---|
| `main.py` | Entrypoint, all compression logic |
| `gui/gui.py` + `gui/__init__.py` | GUI (customtkinter) |
| `tests/test_main.py` + `tests/conftest.py` | Test suite |
| `input/` | Source images/archives (drop here) |
| `output/` | Compressed results |
| `.env.example` | Template for env config |
| `requirements.txt` | Runtime deps: Pillow, py7zr, tqdm, colorama, python-dotenv, customtkinter |
| `requirements-dev.txt` | Dev deps: adds pytest, pytest-xdist, send2trash |
| `GEMINI.md` | Chinese-language dev conventions (reference for design specs) |
