import os
import sys
import zipfile
import argparse
import py7zr
import shutil
import tempfile
import time
from PIL import Image
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import colorama
import io

colorama.init()

try:
    import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

IMG_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
ARC_EXTENSIONS = ('.zip', '.7z')
SUFFIX = "[minify]"


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


def compress_image_stream(img_bytes, fmt, exif=None, icc_profile=None, png_to_webp=False, jpg_to_webp=False):
    """在記憶體中直接壓縮圖片，不產生實體檔案，用於縮短 Zip 處理時間"""
    try:
        if fmt == 'PNG' and png_to_webp:
            fmt = 'WEBP'
        elif fmt == 'JPEG' and jpg_to_webp:
            fmt = 'WEBP'

        with Image.open(io.BytesIO(img_bytes)) as img:
            save_kwargs = {'optimize': True}

            if exif:
                save_kwargs['exif'] = exif

            if icc_profile:
                save_kwargs['icc_profile'] = icc_profile

            if fmt == 'JPEG':
                save_kwargs.update({'quality': 80, 'progressive': True})
            elif fmt == 'WEBP':
                save_kwargs.update({'quality': 80, 'method': 6})
            elif fmt == 'PNG':
                save_kwargs['compress_level'] = 9

            out_io = io.BytesIO()
            img.save(out_io, format=fmt, **save_kwargs)
            compressed_data = out_io.getvalue()

            if len(compressed_data) >= len(img_bytes):
                return img_bytes, True

            return compressed_data, False
    except Exception:
        return img_bytes, True


def compress_image_file(input_path, output_path, png_to_webp=False, jpg_to_webp=False):
    """壓縮單一圖片檔案（供多進程呼叫）"""
    try:
        orig_size = os.path.getsize(input_path)

        with Image.open(input_path) as img:
            fmt = img.format
            if fmt == 'PNG' and png_to_webp:
                fmt = 'WEBP'
            elif fmt == 'JPEG' and jpg_to_webp:
                fmt = 'WEBP'

            exif = img.info.get('exif')
            icc_profile = img.info.get('icc_profile')
            save_kwargs = {'optimize': True}

            if exif:
                save_kwargs['exif'] = exif

            if icc_profile:
                save_kwargs['icc_profile'] = icc_profile

            if fmt == 'JPEG':
                save_kwargs.update({'quality': 80, 'progressive': True})
            elif fmt == 'WEBP':
                save_kwargs.update({'quality': 80, 'method': 6})
            elif fmt == 'PNG':
                save_kwargs['compress_level'] = 9

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


def process_zip_in_memory(input_path, output_path, executor=None, png_to_webp=False, jpg_to_webp=False, override=False):
    """全記憶體優化版：針對 ZIP 進行流式壓縮，不釋放至硬碟"""
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
                                future = executor.submit(compress_image_stream, orig_data, fmt, exif, icc_profile, png_to_webp, jpg_to_webp)
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
                            new_data, is_reverted = compress_image_stream(orig_data, fmt, exif, icc_profile, png_to_webp, jpg_to_webp)
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


def process_7z_with_tmp(input_path, output_path, executor=None, png_to_webp=False, jpg_to_webp=False, override=False):
    """7z 格式保持暫存區，但內部檔案複製改用效率優化"""
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
                    futures = {executor.submit(compress_image_file, src, dst, png_to_webp, jpg_to_webp): (src, dst) for src, dst in image_tasks}
                    for future in as_completed(futures):
                        success, o, n, r, final_path = future.result()
                        if success:
                            total_orig += o
                            total_new += n
                            img_count += 1
                        else:
                            src, dst = futures[future]
                            orig_ext = os.path.splitext(src)[1]
                            dst_name, dst_ext = os.path.splitext(dst)
                            real_dst = dst_name + orig_ext
                            if os.path.exists(dst) and dst != real_dst:
                                try:
                                    os.remove(dst)
                                except Exception:
                                    pass
                            shutil.copy2(src, real_dst)
                else:
                    for src, dst in image_tasks:
                        success, o, n, r, final_path = compress_image_file(src, dst, png_to_webp, jpg_to_webp)
                        if success:
                            total_orig += o
                            total_new += n
                            img_count += 1
                        else:
                            orig_ext = os.path.splitext(src)[1]
                            dst_name, dst_ext = os.path.splitext(dst)
                            real_dst = dst_name + orig_ext
                            if os.path.exists(dst) and dst != real_dst:
                                try:
                                    os.remove(dst)
                                except Exception:
                                    pass
                            shutil.copy2(src, real_dst)

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


def main():
    parser = argparse.ArgumentParser(description="TinyImage - Image Optimization Tool")
    parser.add_argument('--dir', help="Set both input and output directory (cannot be used with --input or --output)")
    parser.add_argument('--input', default='input', help="Input directory (default: input)")
    parser.add_argument('--output', default='output', help="Output directory (default: output)")
    parser.add_argument('--png-to-webp', action='store_true', default=False, help="Convert PNG images to WebP format")
    parser.add_argument('--jpg-to-webp', action='store_true', default=False, help="Convert JPEG images to WebP format")
    parser.add_argument('--override', action='store_true', default=False, help="Override [minify] check and force re-compression")

    exec_group = parser.add_mutually_exclusive_group()
    exec_group.add_argument('--sequential', action='store_true', default=False, help="Disable multiprocessing, process images sequentially")
    exec_group.add_argument('--workers', type=int, default=None, help="Maximum number of parallel workers (default: CPU core count)")

    del_group = parser.add_mutually_exclusive_group()
    del_group.add_argument('--delete-original', action='store_true', default=False, help="Permanently delete original files after compression")
    del_group.add_argument('--soft-delete-original', action='store_true', default=False, help="Move original files to trash instead of permanent delete")

    args = parser.parse_args()

    png_to_webp = args.png_to_webp
    jpg_to_webp = args.jpg_to_webp
    override = args.override
    delete_original = args.delete_original
    soft_delete = args.soft_delete_original
    sequential = args.sequential
    workers = args.workers

    if soft_delete and not HAS_SEND2TRASH:
        parser.error("--soft-delete-original requires send2trash. Install with: pip install send2trash")

    if workers is not None:
        if workers < 1:
            parser.error("--workers must be at least 1")
        workers = min(workers, os.cpu_count())
    else:
        workers = os.cpu_count()

    if args.dir:
        if '--input' in sys.argv or '--output' in sys.argv:
            parser.error("--dir cannot be used with --input or --output")
        input_dir = args.dir
        output_dir = args.dir
    else:
        input_dir = args.input
        output_dir = args.output

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    term_width = shutil.get_terminal_size().columns
    print(f"{colorama.Fore.CYAN}{'=' * term_width}{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}TinyImage - Image Optimization Tool{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN} - Multi-Core Turbo Speed Version{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}{'=' * term_width}{colorama.Style.RESET_ALL}")

    overall_start_time = time.time()

    # 使用 os.walk 遞迴掃描所有子資料夾
    image_tasks = []
    archive_tasks = []
    found_any = False

    for root, dirs, files in os.walk(input_dir):
        for filename in sorted(files):
            if not override and SUFFIX in filename:
                rel_path = os.path.relpath(os.path.join(root, filename), input_dir)
                print(f"{colorama.Fore.LIGHTBLACK_EX}[Skipped] {rel_path} (already processed){colorama.Style.RESET_ALL}")
                continue

            ext = os.path.splitext(filename)[1].lower()
            rel_path = os.path.relpath(os.path.join(root, filename), input_dir)

            if ext in IMG_EXTENSIONS:
                image_tasks.append((root, filename, rel_path))
                found_any = True
            elif ext in ARC_EXTENSIONS:
                archive_tasks.append((root, filename, rel_path))
                found_any = True

    if not found_any:
        print(f"{colorama.Fore.YELLOW}Input folder is empty.{colorama.Style.RESET_ALL}")

        return

    total_bytes_orig = 0
    total_bytes_new = 0

    total_items = len(image_tasks) + len(archive_tasks)

    if sequential:
        with tqdm(total=total_items, desc="Total", unit="item", dynamic_ncols=True, ascii=" #", colour='cyan', bar_format='\033[32m{desc}: {percentage:3.0f}%\033[0m|{bar}|\033[90m {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]\033[0m', position=1) as pbar:
            with tqdm(total=1, bar_format='{desc}', position=0, leave=True) as status_bar:
                for root, filename, rel_path in image_tasks:
                    input_path = os.path.join(root, filename)
                    out_filename = get_output_name(filename, png_to_webp, jpg_to_webp)
                    out_rel_dir = os.path.join(output_dir, os.path.dirname(rel_path))
                    os.makedirs(out_rel_dir, exist_ok=True)
                    output_path = os.path.join(out_rel_dir, out_filename)

                    status_bar.set_description(f"{colorama.Fore.YELLOW}  Processing: {rel_path}{colorama.Style.RESET_ALL}")

                    try:
                        success, o, n, r, final_output_path = compress_image_file(input_path, output_path, png_to_webp, jpg_to_webp)
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
                    input_path = os.path.join(root, filename)
                    ext = os.path.splitext(filename)[1].lower()
                    out_filename = get_output_name(filename, png_to_webp, jpg_to_webp)
                    out_rel_dir = os.path.join(output_dir, os.path.dirname(rel_path))
                    os.makedirs(out_rel_dir, exist_ok=True)
                    output_path = os.path.join(out_rel_dir, out_filename)

                    if ext == '.zip':
                        o, n = process_zip_in_memory(input_path, output_path, None, png_to_webp, jpg_to_webp, override)
                        total_bytes_orig += o
                        total_bytes_new += n
                    elif ext == '.7z':
                        o, n = process_7z_with_tmp(input_path, output_path, None, png_to_webp, jpg_to_webp, override)
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
                input_path = os.path.join(root, filename)
                out_filename = get_output_name(filename, png_to_webp, jpg_to_webp)
                out_rel_dir = os.path.join(output_dir, os.path.dirname(rel_path))
                os.makedirs(out_rel_dir, exist_ok=True)
                output_path = os.path.join(out_rel_dir, out_filename)
                future = executor.submit(compress_image_file, input_path, output_path, png_to_webp, jpg_to_webp)
                future_to_file[future] = (rel_path, out_filename, input_path)

            with tqdm(total=total_items, desc="Total", unit="item", dynamic_ncols=True, ascii=" #", colour='cyan', bar_format='\033[32m{desc}: {percentage:3.0f}%\033[0m|{bar}|\033[90m {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]\033[0m', position=1) as pbar:
                with tqdm(total=1, bar_format='{desc}', position=0, leave=True) as status_bar:
                    for future in as_completed(future_to_file):
                        rel_path, out_filename, input_path = future_to_file[future]
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
                        input_path = os.path.join(root, filename)
                        ext = os.path.splitext(filename)[1].lower()
                        out_filename = get_output_name(filename, png_to_webp, jpg_to_webp)
                        out_rel_dir = os.path.join(output_dir, os.path.dirname(rel_path))
                        os.makedirs(out_rel_dir, exist_ok=True)
                        output_path = os.path.join(out_rel_dir, out_filename)

                        if ext == '.zip':
                            o, n = process_zip_in_memory(input_path, output_path, executor, png_to_webp, jpg_to_webp, override)
                            total_bytes_orig += o
                            total_bytes_new += n
                        elif ext == '.7z':
                            o, n = process_7z_with_tmp(input_path, output_path, executor, png_to_webp, jpg_to_webp, override)
                            total_bytes_orig += o
                            total_bytes_new += n

                        if delete_original or soft_delete:
                            remove_file(input_path, soft_delete)
                            label = "Moved to trash" if soft_delete else "Deleted"
                            tqdm.write(f"{colorama.Fore.RED}  [{label}] {rel_path}{colorama.Style.RESET_ALL}")

                        pbar.update(1)

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
