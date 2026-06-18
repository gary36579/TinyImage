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

try:
    import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

IMG_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
ARC_EXTENSIONS = ('.zip', '.7z')
SUFFIX = "[minify]"


def remove_file(path, soft):
    if soft:
        send2trash.send2trash(path)
    else:
        os.remove(path)


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
    import io

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
                save_kwargs.update({'quality': 80, 'method': 4})
            elif fmt == 'PNG':
                save_kwargs['compress_level'] = 3

            out_io = io.BytesIO()
            img.save(out_io, format=fmt, **save_kwargs)
            compressed_data = out_io.getvalue()

            if len(compressed_data) >= len(img_bytes):
                return img_bytes, True

            return compressed_data, False
    except:
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
            orig_ext = os.path.splitext(input_path)[1]
            out_name, out_ext = os.path.splitext(output_path)
            real_output_path = out_name + orig_ext

            if os.path.exists(output_path) and output_path != real_output_path:
                try:
                    os.remove(output_path)
                except Exception:
                    pass

            shutil.copy2(input_path, real_output_path)

            return True, orig_size, orig_size, 0.0, real_output_path

        return True, orig_size, new_size, (1 - new_size / orig_size) * 100, output_path
    except Exception as e:
        try:
            orig_size = os.path.getsize(input_path)
            orig_ext = os.path.splitext(input_path)[1]
            out_name, out_ext = os.path.splitext(output_path)
            real_output_path = out_name + orig_ext

            if os.path.exists(output_path) and output_path != real_output_path:
                try:
                    os.remove(output_path)
                except Exception:
                    pass

            shutil.copy2(input_path, real_output_path)

            return True, orig_size, orig_size, 0.0, real_output_path
        except Exception:
            return False, 0, 0, 0, output_path


def process_zip_in_memory(input_path, output_path, executor, png_to_webp=False, jpg_to_webp=False):
    """全記憶體優化版：針對 ZIP 進行流式壓縮，不釋放至硬碟"""
    filename = os.path.basename(input_path)
    print(f"\n[Archive] Processing (Memory Stream): {filename}...", end='', flush=True)
    start_time = time.time()

    total_orig = 0
    total_new = 0
    img_count = 0

    try:
        with zipfile.ZipFile(input_path, 'r') as z_in:
            # 檢查加密
            for info in z_in.infolist():
                if info.flag_bits & 0x1:
                    print(f"\n  [Skipped] {filename} is encrypted.")
                    return 0, 0

            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
                futures = {}
                import io

                for item in z_in.infolist():
                    if item.is_dir():
                        continue

                    orig_data = z_in.read(item.filename)

                    if SUFFIX in item.filename:
                        z_out.writestr(item.filename, orig_data)
                        continue

                    out_rel_path = get_output_name(item.filename, png_to_webp, jpg_to_webp)

                    if item.filename.lower().endswith(IMG_EXTENSIONS):
                        # 獲取圖片格式
                        try:
                            with Image.open(io.BytesIO(orig_data)) as img:
                                fmt = img.format
                                exif = img.info.get('exif')
                                icc_profile = img.info.get('icc_profile')

                            future = executor.submit(compress_image_stream, orig_data, fmt, exif, icc_profile, png_to_webp, jpg_to_webp)
                            futures[future] = (item.filename, out_rel_path, len(orig_data), orig_data)
                        except Exception:
                            z_out.writestr(out_rel_path, orig_data)
                    else:
                        # 非圖片直接複製
                        z_out.writestr(out_rel_path, orig_data)

                # 實時寫入壓縮後的圖片
                for future in as_completed(futures):
                    orig_filename, out_rel_path, orig_size, orig_data = futures[future]

                    try:
                        new_data, is_reverted = future.result()
                        new_size = len(new_data)

                        if is_reverted:
                            final_out_path = get_output_name(orig_filename, png_to_webp=False, jpg_to_webp=False)
                        else:
                            final_out_path = out_rel_path

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
        print(f" Done ({elapsed:.2f}s)")

        if img_count > 0:
            total_r = (1 - total_new / total_orig) * 100 if total_orig > 0 else 0
            print(f"  Summary: {img_count} images optimized. {format_size(total_orig)} -> {format_size(total_new)} (-{total_r:.1f}%)")
        else:
            print(f"  Summary: No images found to optimize.")

        return total_orig, total_new
    except Exception as e:
        print(f"\n  [Error] {filename}: {e}")
        return 0, 0


def process_7z_with_tmp(input_path, output_path, executor, png_to_webp=False, jpg_to_webp=False):
    """7z 格式保持暫存區，但內部檔案複製改用效率優化"""
    filename = os.path.basename(input_path)
    print(f"\n[Archive] Processing (7z): {filename}...", end='', flush=True)
    start_time = time.time()

    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        try:
            with py7zr.SevenZipFile(input_path, mode='r') as s:
                if s.password_protected:
                    print(f"\n  [Skipped] {filename} is encrypted.")
                    return 0, 0

                s.extractall(tmp_in)

            total_orig = 0
            total_new = 0
            img_count = 0
            image_tasks = []

            # 收集任務
            for root, dirs, files in os.walk(tmp_in):
                for f in files:
                    src_f = os.path.join(root, f)
                    rel_path = os.path.relpath(src_f, tmp_in)

                    if SUFFIX in f:
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

            # 並行處理圖片
            if image_tasks:
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

            with py7zr.SevenZipFile(output_path, 'w') as s:
                for root, dirs, files in os.walk(tmp_out):
                    for f in files:
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, tmp_out)
                        s.write(full_path, arcname=rel_path)

            elapsed = time.time() - start_time
            print(f" Done ({elapsed:.2f}s)")

            if img_count > 0:
                total_r = (1 - total_new / total_orig) * 100 if total_orig > 0 else 0
                print(f"       Summary: {img_count} images optimized. {format_size(total_orig)} -> {format_size(total_new)} (-{total_r:.1f}%)")
            else:
                print(f"       Summary: No images found to optimize.")

            return total_orig, total_new
        except Exception as e:
            print(f"\n  [Error] {filename}: {e}")
            return 0, 0


def main():
    parser = argparse.ArgumentParser(description="TinyImage - Image Optimization Tool")
    parser.add_argument('--dir', help="Set both input and output directory (cannot be used with --input or --output)")
    parser.add_argument('--input', default='input', help="Input directory (default: input)")
    parser.add_argument('--output', default='output', help="Output directory (default: output)")
    parser.add_argument('--png-to-webp', action='store_true', default=False, help="Convert PNG images to WebP format")
    parser.add_argument('--jpg-to-webp', action='store_true', default=False, help="Convert JPEG images to WebP format")

    del_group = parser.add_mutually_exclusive_group()
    del_group.add_argument('--delete-original', action='store_true', default=False, help="Permanently delete original files after compression")
    del_group.add_argument('--soft-delete-original', action='store_true', default=False, help="Move original files to trash instead of permanent delete")

    args = parser.parse_args()

    png_to_webp = args.png_to_webp
    jpg_to_webp = args.jpg_to_webp
    delete_original = args.delete_original
    soft_delete = args.soft_delete_original

    if soft_delete and not HAS_SEND2TRASH:
        parser.error("--soft-delete-original requires send2trash. Install with: pip install send2trash")

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

    print("="*100)
    print("TinyImage - Image Optimization Tool")
    print(" - Multi-Core Turbo Speed Version")
    print("="*100)

    files_to_process = sorted(os.listdir(input_dir))

    if not files_to_process:
        print("Input folder is empty.")

        return

    overall_start_time = time.time()

    # 區分「獨立圖片」與「壓縮檔」
    image_tasks = []
    archive_tasks = []

    for filename in files_to_process:
        if SUFFIX in filename:
            print(f"[Skipped] {filename} (already processed)")
            continue

        ext = os.path.splitext(filename)[1].lower()

        if ext in IMG_EXTENSIONS:
            image_tasks.append(filename)
        elif ext in ARC_EXTENSIONS:
            archive_tasks.append((filename, ext))

    # 使用統一的執行池，避免重複創建資源
    total_bytes_orig = 0
    total_bytes_new = 0

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        # ---- 階段 1：處理獨立圖片 ----
        if image_tasks:
            print(f"\n[Parallel] Starting multi-core compression for {len(image_tasks)} images...")
            future_to_file = {}

            for filename in image_tasks:
                input_path = os.path.join(input_dir, filename)
                out_filename = get_output_name(filename, png_to_webp, jpg_to_webp)
                output_path = os.path.join(output_dir, out_filename)
                future = executor.submit(compress_image_file, input_path, output_path, png_to_webp, jpg_to_webp)
                future_to_file[future] = (filename, out_filename)

            for future in as_completed(future_to_file):
                filename, out_filename = future_to_file[future]

                try:
                    success, o, n, r, final_output_path = future.result()

                    if success:
                        final_filename = os.path.basename(final_output_path)
                        print(f"[Image] {filename} -> {final_filename}: {format_size(o)} -> {format_size(n)} (-{r:.1f}%)")
                        total_bytes_orig += o
                        total_bytes_new += n
                        if delete_original or soft_delete:
                            input_path = os.path.join(input_dir, filename)
                            remove_file(input_path, soft_delete)
                            label = "Moved to trash" if soft_delete else "Deleted"
                            print(f"  [{label}] {filename}")
                    else:
                        print(f"[Error] Failed to process {filename}")
                except Exception as exc:
                    print(f"[Error] {filename} generated an exception: {exc}")

        # ---- 階段 2：處理壓縮檔（內部圖片會並行提交至同一個 executor） ----
        for filename, ext in archive_tasks:
            input_path = os.path.join(input_dir, filename)
            out_filename = get_output_name(filename, png_to_webp, jpg_to_webp)
            output_path = os.path.join(output_dir, out_filename)

            if ext == '.zip':
                o, n = process_zip_in_memory(input_path, output_path, executor, png_to_webp, jpg_to_webp)
                total_bytes_orig += o
                total_bytes_new += n
            elif ext == '.7z':
                o, n = process_7z_with_tmp(input_path, output_path, executor, png_to_webp, jpg_to_webp)
                total_bytes_orig += o
                total_bytes_new += n

            if delete_original or soft_delete:
                remove_file(input_path, soft_delete)
                label = "Moved to trash" if soft_delete else "Deleted"
                print(f"[{label}] {filename}")

    total_elapsed = time.time() - overall_start_time

    print("\n" + "="*100)
    print(f"All tasks completed in {total_elapsed:.2f}s.")

    if total_bytes_orig > 0:
        total_saved = total_bytes_orig - total_bytes_new
        reduction_percentage = (total_saved / total_bytes_orig) * 100
        print(f"Total size optimized: {format_size(total_bytes_orig)} -> {format_size(total_bytes_new)} (-{reduction_percentage:.2f}%, saved {format_size(total_saved)})")

    print("="*100)


if __name__ == "__main__":
    main()
