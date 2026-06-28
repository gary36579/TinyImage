import os
import sys
import zipfile
import argparse
import py7zr
import shutil
import tempfile
import time
import signal
from PIL import Image
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import colorama
import io
import ctypes
from dotenv import load_dotenv

load_dotenv()
colorama.init()


def _env_int(key, default):
    try:
        return int(os.environ[key])
    except (KeyError, ValueError, TypeError):
        return default


def _env_str(key, default):
    return os.environ.get(key, default)


def _env_bool(key, default):
    v = os.environ.get(key)
    return default if v is None else v.lower() in ('1', 'true', 'yes')


def _env_list(key, default):
    raw = os.environ.get(key)
    return tuple(x.strip() for x in raw.split(',')) if raw else default


FILE_ATTRIBUTE_HIDDEN = 0x2


def is_hidden(path):
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        return attrs != -1 and bool(attrs & FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        return False


try:
    import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

IMG_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
ARC_EXTENSIONS = ('.zip', '.7z')
SUFFIX = '[minify]'
PNG_LEVEL_STREAM = 3
WEBP_METHOD_STREAM = 4


def remove_file(path, soft):
    if soft and HAS_SEND2TRASH:
        send2trash.send2trash(path)
    else:
        os.remove(path)


def fallback_copy(input_path, output_path):
    orig_ext = os.path.splitext(input_path)[1]
    out_name, out_ext = os.path.splitext(output_path)
    real_output_path = out_name + orig_ext
    if os.path.exists(output_path) and output_path != real_output_path:
        try:
            os.remove(output_path)
        except Exception:
            pass
    shutil.copy2(input_path, real_output_path)
    return real_output_path


def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def get_output_name(filename, png_to_webp=False, jpg_to_webp=False):
    name, ext = os.path.splitext(filename)
    low_ext = ext.lower()

    if low_ext == '.png' and png_to_webp:
        ext = '.webp'
    elif low_ext in ('.jpg', '.jpeg') and jpg_to_webp:
        ext = '.webp'
    return f"{name} {SUFFIX}{ext}"


def _convert_format(fmt, png_to_webp, jpg_to_webp):
    if fmt == 'PNG' and png_to_webp:
        return 'WEBP'
    if fmt == 'JPEG' and jpg_to_webp:
        return 'WEBP'
    return fmt


def _build_save_kwargs(fmt, exif, icc_profile, quality, png_level, webp_method, jpeg_progressive):
    save_kwargs = {'optimize': True}
    if exif:
        save_kwargs['exif'] = exif
    if icc_profile:
        save_kwargs['icc_profile'] = icc_profile
    if fmt == 'JPEG':
        save_kwargs.update({'quality': quality, 'progressive': jpeg_progressive})
    elif fmt == 'WEBP':
        save_kwargs.update({'quality': quality, 'method': webp_method})
    elif fmt == 'PNG':
        save_kwargs['compress_level'] = png_level
    return save_kwargs


def compress_image_stream(img_bytes, fmt, exif=None, icc_profile=None, png_to_webp=False, jpg_to_webp=False, quality=80, png_level=9, webp_method=6, jpeg_progressive=True):
    try:
        fmt = _convert_format(fmt, png_to_webp, jpg_to_webp)

        with Image.open(io.BytesIO(img_bytes)) as img:
            save_kwargs = _build_save_kwargs(fmt, exif, icc_profile, quality, png_level, webp_method, jpeg_progressive)

            out_io = io.BytesIO()
            img.save(out_io, format=fmt, **save_kwargs)
            compressed_data = out_io.getvalue()

            if len(compressed_data) >= len(img_bytes):
                return img_bytes, True

            return compressed_data, False
    except Exception:
        return img_bytes, True


def compress_image_file(input_path, output_path, png_to_webp=False, jpg_to_webp=False, quality=80, png_level=9, webp_method=6, jpeg_progressive=True):
    try:
        orig_size = os.path.getsize(input_path)

        with Image.open(input_path) as img:
            fmt = _convert_format(img.format, png_to_webp, jpg_to_webp)
            exif = img.info.get('exif')
            icc_profile = img.info.get('icc_profile')
            save_kwargs = _build_save_kwargs(fmt, exif, icc_profile, quality, png_level, webp_method, jpeg_progressive)

            img.save(output_path, format=fmt, **save_kwargs)

        new_size = os.path.getsize(output_path)

        if new_size >= orig_size:
            real_output_path = fallback_copy(input_path, output_path)
            return True, orig_size, orig_size, 0.0, real_output_path

        return True, orig_size, new_size, (1 - new_size / orig_size) * 100, output_path
    except Exception as e:
        try:
            orig_size = os.path.getsize(input_path)
            real_output_path = fallback_copy(input_path, output_path)
            return True, orig_size, orig_size, 0.0, real_output_path
        except Exception:
            return False, 0, 0, 0, output_path


def process_zip_in_memory(input_path, output_path, executor=None, png_to_webp=False, jpg_to_webp=False, override=False, quality=80, png_level=9, webp_method=6, jpeg_progressive=True, png_level_stream=3, webp_method_stream=4):
    filename = os.path.basename(input_path)
    start_time = time.time()

    total_orig = 0
    total_new = 0
    img_count = 0

    try:
        with zipfile.ZipFile(input_path, 'r') as z_in:
            for info in z_in.infolist():
                if info.flag_bits & 0x1:
                    print(f"\n  {colorama.Fore.LIGHTBLACK_EX}[Skipped] {filename} is encrypted.{colorama.Style.RESET_ALL}")
                    return 0, 0

            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
                futures = {}
                pending = []

                for item in z_in.infolist():
                    if item.is_dir():
                        continue

                    orig_data = z_in.read(item.filename)

                    if not override and SUFFIX in item.filename:
                        z_out.writestr(item.filename, orig_data)
                        continue

                    out_rel_path = get_output_name(item.filename, png_to_webp, jpg_to_webp)

                    if item.filename.lower().endswith(IMG_EXTENSIONS):
                        try:
                            with Image.open(io.BytesIO(orig_data)) as img:
                                fmt = img.format
                                exif = img.info.get('exif')
                                icc_profile = img.info.get('icc_profile')

                            if executor:
                                future = executor.submit(compress_image_stream, orig_data, fmt, exif, icc_profile, png_to_webp,
                                                         jpg_to_webp, quality, png_level_stream, webp_method_stream, jpeg_progressive)
                                futures[future] = (item.filename, out_rel_path, len(orig_data), orig_data)
                            else:
                                pending.append((item.filename, out_rel_path, orig_data, fmt, exif, icc_profile))
                        except Exception:
                            z_out.writestr(out_rel_path, orig_data)
                    else:
                        z_out.writestr(out_rel_path, orig_data)

                if executor:
                    for future in as_completed(futures):
                        orig_filename, out_rel_path, orig_size, orig_data = futures[future]
                        try:
                            new_data, is_reverted = future.result()
                            new_size = len(new_data)
                            final_out_path = get_output_name(orig_filename, png_to_webp=False, jpg_to_webp=False) if is_reverted else out_rel_path
                            z_out.writestr(final_out_path, new_data)
                            total_orig += orig_size
                            total_new += new_size
                            img_count += 1
                        except Exception:
                            final_out_path = get_output_name(orig_filename, png_to_webp=False, jpg_to_webp=False)
                            z_out.writestr(final_out_path, orig_data)
                            total_orig += orig_size
                            total_new += orig_size
                            img_count += 1
                else:
                    for orig_filename, out_rel_path, orig_data, fmt, exif, icc_profile in pending:
                        orig_size = len(orig_data)
                        try:
                            new_data, is_reverted = compress_image_stream(orig_data, fmt, exif, icc_profile, png_to_webp, jpg_to_webp,
                                                                          quality, png_level_stream, webp_method_stream, jpeg_progressive)
                            new_size = len(new_data)
                            final_out_path = get_output_name(orig_filename, png_to_webp=False, jpg_to_webp=False) if is_reverted else out_rel_path
                            z_out.writestr(final_out_path, new_data)
                            total_orig += orig_size
                            total_new += new_size
                            img_count += 1
                        except Exception:
                            final_out_path = get_output_name(orig_filename, png_to_webp=False, jpg_to_webp=False)
                            z_out.writestr(final_out_path, orig_data)
                            total_orig += orig_size
                            total_new += orig_size
                            img_count += 1

        elapsed = time.time() - start_time

        if img_count > 0:
            total_r = (1 - total_new / total_orig) * 100 if total_orig > 0 else 0
            tqdm.write(f"  Summary: {filename} — {img_count} images, {format_size(total_orig)} -> {format_size(total_new)} (-{total_r:.1f}%) [{elapsed:.2f}s]")
        else:
            tqdm.write(f"  Summary: {filename} — No images found to optimize.")

        return total_orig, total_new
    except Exception as e:
        tqdm.write(f"  [Error] {filename}: {e}")
        return 0, 0


def process_7z_with_tmp(input_path, output_path, executor=None, png_to_webp=False, jpg_to_webp=False, override=False, quality=80, png_level=9, webp_method=6, jpeg_progressive=True):
    filename = os.path.basename(input_path)
    start_time = time.time()

    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        try:
            with py7zr.SevenZipFile(input_path, mode='r') as s:
                if s.password_protected:
                    print(f"\n  {colorama.Fore.LIGHTBLACK_EX}[Skipped] {filename} is encrypted.{colorama.Style.RESET_ALL}")
                    return 0, 0

                s.extractall(tmp_in)

            total_orig = 0
            total_new = 0
            img_count = 0
            image_tasks = []

            for root, dirs, files in os.walk(tmp_in):
                for f in files:
                    src_f = os.path.join(root, f)
                    rel_path = os.path.relpath(src_f, tmp_in)

                    if not override and SUFFIX in f:
                        dst_f = os.path.join(tmp_out, rel_path)
                        os.makedirs(os.path.dirname(dst_f), exist_ok=True)
                        shutil.copy2(src_f, dst_f)
                        continue

                    out_rel_path = get_output_name(rel_path, png_to_webp, jpg_to_webp)
                    dst_f = os.path.join(tmp_out, out_rel_path)

                    os.makedirs(os.path.dirname(dst_f), exist_ok=True)

                    if f.lower().endswith(IMG_EXTENSIONS):
                        image_tasks.append((src_f, dst_f))
                    else:
                        shutil.copy2(src_f, dst_f)

            if image_tasks:
                if executor:
                    futures = {executor.submit(compress_image_file, src, dst, png_to_webp, jpg_to_webp, quality, png_level,
                                               webp_method, jpeg_progressive): (src, dst) for src, dst in image_tasks}
                    for future in as_completed(futures):
                        success, o, n, r, final_path = future.result()
                        if success:
                            total_orig += o
                            total_new += n
                            img_count += 1
                        else:
                            src, dst = futures[future]
                            fallback_copy(src, dst)
                else:
                    for src, dst in image_tasks:
                        success, o, n, r, final_path = compress_image_file(src, dst, png_to_webp, jpg_to_webp, quality, png_level, webp_method, jpeg_progressive)
                        if success:
                            total_orig += o
                            total_new += n
                            img_count += 1
                        else:
                            fallback_copy(src, dst)

            with py7zr.SevenZipFile(output_path, 'w') as s:
                for root, dirs, files in os.walk(tmp_out):
                    for f in files:
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, tmp_out)
                        s.write(full_path, arcname=rel_path)

            elapsed = time.time() - start_time

            if img_count > 0:
                total_r = (1 - total_new / total_orig) * 100 if total_orig > 0 else 0
                tqdm.write(f"  Summary: {filename} — {img_count} images, {format_size(total_orig)} -> {format_size(total_new)} (-{total_r:.1f}%) [{elapsed:.2f}s]")
            else:
                tqdm.write(f"  Summary: {filename} — No images found to optimize.")

            return total_orig, total_new
        except Exception as e:
            tqdm.write(f"  [Error] {filename}: {e}")
            return 0, 0


def _show_config(items):
    term_width = shutil.get_terminal_size().columns
    width = min(term_width, 68)

    source_colors = {
        'CLI': colorama.Fore.GREEN,
        'env': colorama.Fore.YELLOW,
        'default': colorama.Fore.LIGHTBLACK_EX,
    }

    print(f"\n{colorama.Fore.CYAN}{'=' * width}{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}{'TinyImage Configuration':^{width}}{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}{'=' * width}{colorama.Style.RESET_ALL}")

    for label, value, source in items:
        sc = source_colors.get(source, colorama.Fore.LIGHTBLACK_EX)
        print(f"  {colorama.Fore.CYAN}{label:<25}{colorama.Style.RESET_ALL} {str(value):>15}   {sc}({source}){colorama.Style.RESET_ALL}")

    print(f"{colorama.Fore.CYAN}{'=' * width}{colorama.Style.RESET_ALL}\n")


def _build_paths(root, filename, rel_path, output_dir, png_to_webp, jpg_to_webp):
    input_path = os.path.join(root, filename)
    out_filename = get_output_name(filename, png_to_webp, jpg_to_webp)
    out_rel_dir = os.path.join(output_dir, os.path.dirname(rel_path))
    os.makedirs(out_rel_dir, exist_ok=True)
    output_path = os.path.join(out_rel_dir, out_filename)
    return input_path, output_path


def _scan_directory(input_dir, img_exts, arc_exts, override, suffix):
    image_tasks = []
    archive_tasks = []
    found_any = False
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = [d for d in dirs if not is_hidden(os.path.join(root, d))]
        for filename in sorted(files):
            if is_hidden(os.path.join(root, filename)):
                continue
            if not override and suffix in filename:
                rel_path = os.path.relpath(os.path.join(root, filename), input_dir)
                print(f"{colorama.Fore.LIGHTBLACK_EX}[Skipped] {rel_path} (already processed){colorama.Style.RESET_ALL}")
                continue
            ext = os.path.splitext(filename)[1].lower()
            rel_path = os.path.relpath(os.path.join(root, filename), input_dir)
            if ext in img_exts:
                image_tasks.append((root, filename, rel_path))
                found_any = True
            elif ext in arc_exts:
                archive_tasks.append((root, filename, rel_path))
                found_any = True
    return image_tasks, archive_tasks, found_any


def _run_tasks(image_tasks, archive_tasks, output_dir, sequential, workers,
               png_to_webp, jpg_to_webp, quality, png_level, webp_method,
               jpeg_progressive, override, delete_original, soft_delete,
               png_level_stream, webp_method_stream):
    total_bytes_orig = 0
    total_bytes_new = 0
    total_items = len(image_tasks) + len(archive_tasks)

    if sequential:
        with tqdm(total=total_items, desc="Total", unit="item", dynamic_ncols=True, ascii=" #", colour='cyan', bar_format='\033[32m{desc}: {percentage:3.0f}%\033[0m|{bar}|\033[90m {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]\033[0m', position=1) as pbar:
            with tqdm(total=1, bar_format='{desc}', position=0, leave=True) as status_bar:
                for root, filename, rel_path in image_tasks:
                    input_path, output_path = _build_paths(root, filename, rel_path, output_dir, png_to_webp, jpg_to_webp)

                    status_bar.set_description(f"{colorama.Fore.YELLOW}  Processing: {rel_path}{colorama.Style.RESET_ALL}")

                    try:
                        success, o, n, r, final_output_path = compress_image_file(input_path, output_path, png_to_webp,
                                                                                  jpg_to_webp, quality, png_level, webp_method, jpeg_progressive)
                        if success:
                            final_filename = os.path.basename(final_output_path)
                            tqdm.write(f"  {colorama.Fore.GREEN}OK{colorama.Style.RESET_ALL}  {rel_path} -> {final_filename}  ({format_size(o)} -> {format_size(n)}, -{r:.1f}%)")
                            total_bytes_orig += o
                            total_bytes_new += n
                            if delete_original or soft_delete:
                                remove_file(input_path, soft_delete)
                                label = "Moved to trash" if soft_delete else "Deleted"
                                tqdm.write(f"{colorama.Fore.RED}       [{label}] {rel_path}{colorama.Style.RESET_ALL}")
                        else:
                            tqdm.write(f"  {colorama.Fore.RED}ERR{colorama.Style.RESET_ALL} {rel_path}")
                    except Exception as exc:
                        tqdm.write(f"  {colorama.Fore.RED}ERR{colorama.Style.RESET_ALL} {rel_path}: {exc}")

                    pbar.update(1)

                for root, filename, rel_path in archive_tasks:
                    status_bar.set_description(f"{colorama.Fore.YELLOW}  Processing: {rel_path}{colorama.Style.RESET_ALL}")
                    ext = os.path.splitext(filename)[1].lower()
                    input_path, output_path = _build_paths(root, filename, rel_path, output_dir, png_to_webp, jpg_to_webp)

                    if ext == '.zip':
                        o, n = process_zip_in_memory(input_path, output_path, None, png_to_webp, jpg_to_webp, override, quality,
                                                     png_level, webp_method, jpeg_progressive, png_level_stream, webp_method_stream)
                        total_bytes_orig += o
                        total_bytes_new += n
                    elif ext == '.7z':
                        o, n = process_7z_with_tmp(input_path, output_path, None, png_to_webp, jpg_to_webp, override, quality, png_level, webp_method, jpeg_progressive)
                        total_bytes_orig += o
                        total_bytes_new += n

                    if delete_original or soft_delete:
                        remove_file(input_path, soft_delete)
                        label = "Moved to trash" if soft_delete else "Deleted"
                        tqdm.write(f"{colorama.Fore.RED}  [{label}] {rel_path}{colorama.Style.RESET_ALL}")

                    pbar.update(1)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_file = {}
            for root, filename, rel_path in image_tasks:
                input_path, output_path = _build_paths(root, filename, rel_path, output_dir, png_to_webp, jpg_to_webp)
                future = executor.submit(compress_image_file, input_path, output_path, png_to_webp, jpg_to_webp, quality, png_level, webp_method, jpeg_progressive)
                future_to_file[future] = (rel_path, input_path)

            with tqdm(total=total_items, desc="Total", unit="item", dynamic_ncols=True, ascii=" #", colour='cyan', bar_format='\033[32m{desc}: {percentage:3.0f}%\033[0m|{bar}|\033[90m {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]\033[0m', position=1) as pbar:
                with tqdm(total=1, bar_format='{desc}', position=0, leave=True) as status_bar:
                    for future in as_completed(future_to_file):
                        rel_path, input_path = future_to_file[future]
                        status_bar.set_description(f"{colorama.Fore.YELLOW}  Processing: {rel_path}{colorama.Style.RESET_ALL}")

                        try:
                            success, o, n, r, final_output_path = future.result()

                            if success:
                                final_filename = os.path.basename(final_output_path)
                                tqdm.write(f"  {colorama.Fore.GREEN}OK{colorama.Style.RESET_ALL}  {rel_path} -> {final_filename}  ({format_size(o)} -> {format_size(n)}, -{r:.1f}%)")
                                total_bytes_orig += o
                                total_bytes_new += n
                                if delete_original or soft_delete:
                                    remove_file(input_path, soft_delete)
                                    label = "Moved to trash" if soft_delete else "Deleted"
                                    tqdm.write(f"{colorama.Fore.RED}       [{label}] {rel_path}{colorama.Style.RESET_ALL}")
                            else:
                                tqdm.write(f"  {colorama.Fore.RED}ERR{colorama.Style.RESET_ALL} {rel_path}")
                        except Exception as exc:
                            tqdm.write(f"  {colorama.Fore.RED}ERR{colorama.Style.RESET_ALL} {rel_path}: {exc}")

                        pbar.update(1)

                    for root, filename, rel_path in archive_tasks:
                        status_bar.set_description(f"{colorama.Fore.YELLOW}  Processing: {rel_path}{colorama.Style.RESET_ALL}")
                        ext = os.path.splitext(filename)[1].lower()
                        input_path, output_path = _build_paths(root, filename, rel_path, output_dir, png_to_webp, jpg_to_webp)

                        if ext == '.zip':
                            o, n = process_zip_in_memory(input_path, output_path, executor, png_to_webp, jpg_to_webp, override, quality,
                                                         png_level, webp_method, jpeg_progressive, png_level_stream, webp_method_stream)
                            total_bytes_orig += o
                            total_bytes_new += n
                        elif ext == '.7z':
                            o, n = process_7z_with_tmp(input_path, output_path, executor, png_to_webp, jpg_to_webp, override, quality, png_level, webp_method, jpeg_progressive)
                            total_bytes_orig += o
                            total_bytes_new += n

                        if delete_original or soft_delete:
                            remove_file(input_path, soft_delete)
                            label = "Moved to trash" if soft_delete else "Deleted"
                            tqdm.write(f"{colorama.Fore.RED}  [{label}] {rel_path}{colorama.Style.RESET_ALL}")

                        pbar.update(1)

    return total_bytes_orig, total_bytes_new


def _watch_loop(input_dir, output_dir, interval,
                sequential, workers,
                png_to_webp, jpg_to_webp, quality, png_level, webp_method,
                jpeg_progressive, override, delete_original, soft_delete,
                png_level_stream, webp_method_stream):
    print(f"\n{colorama.Fore.CYAN}Watch mode enabled. Monitoring '{input_dir}' every {interval}s...{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.LIGHTBLACK_EX}Press Ctrl+C to stop.{colorama.Style.RESET_ALL}")

    stop_requested = False

    def _sigint_handler(sig, frame):
        nonlocal stop_requested
        if not stop_requested:
            stop_requested = True
            tqdm.write(f"\n{colorama.Fore.YELLOW}Shutdown requested, finishing current batch...{colorama.Style.RESET_ALL}")

    signal.signal(signal.SIGINT, _sigint_handler)

    image_tasks, archive_tasks, found = _scan_directory(input_dir, IMG_EXTENSIONS, ARC_EXTENSIONS, override, SUFFIX)
    if image_tasks or archive_tasks:
        _run_tasks(image_tasks, archive_tasks, output_dir, sequential, workers,
                   png_to_webp, jpg_to_webp, quality, png_level, webp_method,
                   jpeg_progressive, override, delete_original, soft_delete,
                   png_level_stream, webp_method_stream)

    tracked = {}
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = [d for d in dirs if not is_hidden(os.path.join(root, d))]
        for fname in files:
            fpath = os.path.join(root, fname)
            if is_hidden(fpath):
                continue
            try:
                tracked[fpath] = os.path.getmtime(fpath)
            except OSError:
                pass

    _busy = False

    while not stop_requested:
        time.sleep(interval)

        if stop_requested or _busy:
            continue

        _busy = True
        try:
            current = {}
            for root, dirs, files in os.walk(input_dir):
                dirs[:] = [d for d in dirs if not is_hidden(os.path.join(root, d))]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if is_hidden(fpath):
                        continue
                    try:
                        current[fpath] = os.path.getmtime(fpath)
                    except OSError:
                        pass

            delta_images = []
            delta_archives = []

            for fpath, mtime in current.items():
                if fpath not in tracked or mtime != tracked[fpath]:
                    filename = os.path.basename(fpath)
                    if not override and SUFFIX in filename:
                        continue
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in IMG_EXTENSIONS and ext not in ARC_EXTENSIONS:
                        continue
                    rel_path = os.path.relpath(fpath, input_dir)
                    root = os.path.dirname(fpath)
                    if ext in IMG_EXTENSIONS:
                        delta_images.append((root, filename, rel_path))
                    else:
                        delta_archives.append((root, filename, rel_path))

            for fpath in list(tracked):
                if fpath not in current:
                    del tracked[fpath]

            if delta_images or delta_archives:
                _run_tasks(delta_images, delta_archives, output_dir, sequential, workers,
                           png_to_webp, jpg_to_webp, quality, png_level, webp_method,
                           jpeg_progressive, override, delete_original, soft_delete,
                           png_level_stream, webp_method_stream)

            tracked = current
        finally:
            _busy = False

    print(f"{colorama.Fore.GREEN}Watch mode stopped.{colorama.Style.RESET_ALL}")


def main():
    parser = argparse.ArgumentParser(description="TinyImage - Image Optimization Tool")

    del_group = parser.add_mutually_exclusive_group()
    del_group.add_argument('--delete-original', action='store_true', default=False, help="Permanently delete original files after compression")
    del_group.add_argument('--soft-delete-original', action='store_true', default=False, help="Move original files to trash instead of permanent delete")

    parser.add_argument('--arc-exts', help="Comma-separated archive extensions (env: TINYIMAGE_ARC_EXTS, default: .zip,.7z)")
    parser.add_argument('--dir', help="Set both input and output directory (cannot be used with --input or --output)")
    parser.add_argument('--file', '--files', nargs='+', dest='files', default=None, help="One or more specific files to process (cannot be used with --dir or --input)")
    parser.add_argument('--img-exts', help="Comma-separated image extensions (env: TINYIMAGE_IMG_EXTS, default: .jpg,.jpeg,.png,.webp)")
    parser.add_argument('--input', default=None, help="Input directory (env: TINYIMAGE_INPUT, default: 'input')")
    parser.add_argument('--jpeg-progressive', action='store_true', default=None, help="Enable JPEG progressive encoding (env: TINYIMAGE_JPEG_PROGRESSIVE)")
    parser.add_argument('--jpg-to-webp', action='store_true', default=None, help="Convert JPEG images to WebP format (env: TINYIMAGE_JPG_TO_WEBP)")
    parser.add_argument('--output', default=None, help="Output directory (env: TINYIMAGE_OUTPUT, default: 'output')")
    parser.add_argument('--override', action='store_true', default=None, help="Override [minify] check and force re-compression (env: TINYIMAGE_OVERRIDE)")
    parser.add_argument('--png-level', type=int, default=None, help="PNG compress level 0-9 (env: TINYIMAGE_PNG_LEVEL, default: 9)")
    parser.add_argument('--png-level-stream', type=int, default=None, help="ZIP in-memory PNG compress level 0-9 (env: TINYIMAGE_PNG_LEVEL_STREAM, default: 3)")
    parser.add_argument('--png-to-webp', action='store_true', default=None, help="Convert PNG images to WebP format (env: TINYIMAGE_PNG_TO_WEBP)")
    parser.add_argument('--quality', type=int, default=None, help="JPEG/WebP compression quality (env: TINYIMAGE_QUALITY, default: 80)")

    exec_group = parser.add_mutually_exclusive_group()
    exec_group.add_argument('--sequential', action='store_true', default=False, help="Disable multiprocessing, process images sequentially")
    exec_group.add_argument('--workers', type=int, default=None, help="Maximum number of parallel workers (env: TINYIMAGE_WORKERS, default: CPU core count)")

    parser.add_argument('--show-config', action='store_true', default=False, help="Display current configuration and exit")
    parser.add_argument('--suffix', default=None, help="Output filename suffix marker (env: TINYIMAGE_SUFFIX, default: '[minify]')")
    parser.add_argument('--webp-method', type=int, default=None, help="WebP compression method 0-6 (env: TINYIMAGE_WEBP_METHOD, default: 6)")
    parser.add_argument('--webp-method-stream', type=int, default=None, help="ZIP in-memory WebP method 0-6 (env: TINYIMAGE_WEBP_METHOD_STREAM, default: 4)")
    parser.add_argument('--watch', action='store_true', default=False, help="Enable watch mode - monitor directory for changes and process automatically")
    parser.add_argument('--watch-interval', type=int, default=None, help="Watch mode polling interval in seconds (env: TINYIMAGE_WATCH_INTERVAL, default: 3)")

    args = parser.parse_args()

    delete_original = args.delete_original
    soft_delete = args.soft_delete_original
    sequential = args.sequential

    # Three-tier priority: CLI > env > default
    quality = args.quality if args.quality is not None else _env_int('TINYIMAGE_QUALITY', 80)
    png_level = args.png_level if args.png_level is not None else _env_int('TINYIMAGE_PNG_LEVEL', 9)
    webp_method = args.webp_method if args.webp_method is not None else _env_int('TINYIMAGE_WEBP_METHOD', 6)
    jpeg_progressive = args.jpeg_progressive if args.jpeg_progressive is not None else _env_bool('TINYIMAGE_JPEG_PROGRESSIVE', True)
    png_to_webp = args.png_to_webp if args.png_to_webp is not None else _env_bool('TINYIMAGE_PNG_TO_WEBP', False)
    jpg_to_webp = args.jpg_to_webp if args.jpg_to_webp is not None else _env_bool('TINYIMAGE_JPG_TO_WEBP', False)
    override = args.override if args.override is not None else _env_bool('TINYIMAGE_OVERRIDE', False)

    global SUFFIX, PNG_LEVEL_STREAM, WEBP_METHOD_STREAM, IMG_EXTENSIONS, ARC_EXTENSIONS
    SUFFIX = args.suffix if args.suffix is not None else _env_str('TINYIMAGE_SUFFIX', '[minify]')
    PNG_LEVEL_STREAM = args.png_level_stream if args.png_level_stream is not None else _env_int('TINYIMAGE_PNG_LEVEL_STREAM', 3)
    WEBP_METHOD_STREAM = args.webp_method_stream if args.webp_method_stream is not None else _env_int('TINYIMAGE_WEBP_METHOD_STREAM', 4)

    if args.img_exts is not None:
        IMG_EXTENSIONS = tuple(x.strip() for x in args.img_exts.split(','))
    else:
        IMG_EXTENSIONS = _env_list('TINYIMAGE_IMG_EXTS', ('.jpg', '.jpeg', '.png', '.webp'))

    if args.arc_exts is not None:
        ARC_EXTENSIONS = tuple(x.strip() for x in args.arc_exts.split(','))
    else:
        ARC_EXTENSIONS = _env_list('TINYIMAGE_ARC_EXTS', ('.zip', '.7z'))

    # Input/output with three-tier, then --dir override
    input_dir = args.input if args.input else _env_str('TINYIMAGE_INPUT', 'input')
    output_dir = args.output if args.output else _env_str('TINYIMAGE_OUTPUT', 'output')

    if soft_delete and not HAS_SEND2TRASH:
        parser.error("--soft-delete-original requires send2trash. Install with: pip install send2trash")

    workers_val = args.workers if args.workers is not None else _env_int('TINYIMAGE_WORKERS', os.cpu_count())
    if workers_val < 1:
        parser.error("--workers must be at least 1")
    workers = min(workers_val, os.cpu_count())

    if args.dir:
        if '--input' in sys.argv or '--output' in sys.argv:
            parser.error("--dir cannot be used with --input or --output")
        input_dir = args.dir
        output_dir = args.dir

    if args.files:
        if args.dir or '--input' in sys.argv:
            parser.error("--file/--files cannot be used with --dir or --input")
        if not args.output and '--output' not in sys.argv:
            output_dir = '.'

    watch_interval = args.watch_interval if args.watch_interval is not None else _env_int('TINYIMAGE_WATCH_INTERVAL', 3)

    if args.show_config:
        def _source(label, value, cli_test=None, env_key=None):
            if cli_test and cli_test():
                return (label, value, 'CLI')
            if env_key and env_key in os.environ:
                return (label, value, 'env')
            return (label, value, 'default')

        items = [
            _source("Input dir", input_dir,
                    cli_test=lambda: '--dir' in sys.argv or '--input' in sys.argv,
                    env_key='TINYIMAGE_INPUT'),
            _source("Output dir", output_dir,
                    cli_test=lambda: '--dir' in sys.argv or '--output' in sys.argv,
                    env_key='TINYIMAGE_OUTPUT'),
            _source("Quality", quality,
                    cli_test=lambda: args.quality is not None,
                    env_key='TINYIMAGE_QUALITY'),
            _source("PNG level", png_level,
                    cli_test=lambda: args.png_level is not None,
                    env_key='TINYIMAGE_PNG_LEVEL'),
            _source("WebP method", webp_method,
                    cli_test=lambda: args.webp_method is not None,
                    env_key='TINYIMAGE_WEBP_METHOD'),
            _source("JPEG progressive", jpeg_progressive,
                    cli_test=lambda: args.jpeg_progressive is not None,
                    env_key='TINYIMAGE_JPEG_PROGRESSIVE'),
            _source("Suffix", SUFFIX,
                    cli_test=lambda: '--suffix' in sys.argv,
                    env_key='TINYIMAGE_SUFFIX'),
            _source("Image extensions", ', '.join(IMG_EXTENSIONS),
                    cli_test=lambda: '--img-exts' in sys.argv,
                    env_key='TINYIMAGE_IMG_EXTS'),
            _source("Archive extensions", ', '.join(ARC_EXTENSIONS),
                    cli_test=lambda: '--arc-exts' in sys.argv,
                    env_key='TINYIMAGE_ARC_EXTS'),
            _source("PNG level (stream)", PNG_LEVEL_STREAM,
                    cli_test=lambda: '--png-level-stream' in sys.argv,
                    env_key='TINYIMAGE_PNG_LEVEL_STREAM'),
            _source("WebP method (stream)", WEBP_METHOD_STREAM,
                    cli_test=lambda: '--webp-method-stream' in sys.argv,
                    env_key='TINYIMAGE_WEBP_METHOD_STREAM'),
            _source("PNG -> WebP", png_to_webp,
                    cli_test=lambda: '--png-to-webp' in sys.argv,
                    env_key='TINYIMAGE_PNG_TO_WEBP'),
            _source("JPEG -> WebP", jpg_to_webp,
                    cli_test=lambda: '--jpg-to-webp' in sys.argv,
                    env_key='TINYIMAGE_JPG_TO_WEBP'),
            _source("Override", override,
                    cli_test=lambda: '--override' in sys.argv,
                    env_key='TINYIMAGE_OVERRIDE'),
            _source("Sequential", sequential,
                    cli_test=lambda: '--sequential' in sys.argv),
            _source("Workers", workers,
                    cli_test=lambda: args.workers is not None,
                    env_key='TINYIMAGE_WORKERS'),
            _source("Delete original", delete_original,
                    cli_test=lambda: '--delete-original' in sys.argv),
            _source("Soft delete original", soft_delete,
                    cli_test=lambda: '--soft-delete-original' in sys.argv),
            _source("Watch mode", args.watch or 'off',
                    cli_test=lambda: '--watch' in sys.argv),
            _source("Watch interval (s)", watch_interval,
                    cli_test=lambda: '--watch-interval' in sys.argv,
                    env_key='TINYIMAGE_WATCH_INTERVAL'),
        ]
        _show_config(items)
        return

    if args.watch:
        if args.files:
            parser.error("--watch cannot be used with --file/--files")
        if watch_interval < 1:
            parser.error("--watch-interval must be at least 1")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        _watch_loop(input_dir, output_dir, watch_interval,
                    sequential, workers,
                    png_to_webp, jpg_to_webp, quality, png_level, webp_method,
                    jpeg_progressive, override, delete_original, soft_delete,
                    PNG_LEVEL_STREAM, WEBP_METHOD_STREAM)
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    term_width = shutil.get_terminal_size().columns
    print(f"{colorama.Fore.CYAN}{'=' * term_width}{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}TinyImage - Image Optimization Tool{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN} - Multi-Core Turbo Speed Version{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}{'=' * term_width}{colorama.Style.RESET_ALL}")

    overall_start_time = time.time()

    image_tasks = []
    archive_tasks = []
    found_any = False

    if args.files:
        for filepath in args.files:
            if not os.path.exists(filepath):
                print(f"  {colorama.Fore.RED}ERR{colorama.Style.RESET_ALL} File not found: {filepath}")
                continue
            filename = os.path.basename(filepath)
            if not override and SUFFIX in filename:
                print(f"{colorama.Fore.LIGHTBLACK_EX}[Skipped] {filepath} (already processed){colorama.Style.RESET_ALL}")
                continue
            ext = os.path.splitext(filename)[1].lower()
            root = os.path.dirname(filepath) or '.'
            if ext in IMG_EXTENSIONS:
                image_tasks.append((root, filename, filename))
                found_any = True
            elif ext in ARC_EXTENSIONS:
                archive_tasks.append((root, filename, filename))
                found_any = True
    else:
        image_tasks, archive_tasks, found_any = _scan_directory(input_dir, IMG_EXTENSIONS, ARC_EXTENSIONS, override, SUFFIX)

    if not found_any:
        msg = "No files found." if args.files else "Input folder is empty."
        print(f"{colorama.Fore.YELLOW}{msg}{colorama.Style.RESET_ALL}")

        return

    total_bytes_orig, total_bytes_new = _run_tasks(
        image_tasks, archive_tasks, output_dir, sequential, workers,
        png_to_webp, jpg_to_webp, quality, png_level, webp_method,
        jpeg_progressive, override, delete_original, soft_delete,
        PNG_LEVEL_STREAM, WEBP_METHOD_STREAM
    )

    total_elapsed = time.time() - overall_start_time

    print(f"\n{colorama.Fore.CYAN}{'=' * term_width}{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.GREEN}All tasks completed in {total_elapsed:.2f}s.{colorama.Style.RESET_ALL}")

    if total_bytes_orig > 0:
        total_saved = total_bytes_orig - total_bytes_new
        reduction_percentage = (total_saved / total_bytes_orig) * 100
        print(f"{colorama.Fore.GREEN}Total size optimized: {format_size(total_bytes_orig)} -> {format_size(total_bytes_new)} (-{reduction_percentage:.2f}%, saved {format_size(total_saved)}){colorama.Style.RESET_ALL}")

    print(f"{colorama.Fore.CYAN}{'=' * term_width}{colorama.Style.RESET_ALL}")


if __name__ == "__main__":
    main()
