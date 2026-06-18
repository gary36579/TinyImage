import io
import os
from PIL import Image
from main import (
    format_size,
    get_output_name,
    compress_image_stream,
    compress_image_file,
    remove_file,
    SUFFIX,
)


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500.00 B"

    def test_kilobytes(self):
        assert format_size(1500) == "1.46 KB"

    def test_megabytes(self):
        assert format_size(2_500_000) == "2.38 MB"

    def test_gigabytes(self):
        assert format_size(2_500_000_000) == "2.33 GB"

    def test_terabytes(self):
        assert format_size(2_500_000_000_000) == "2.27 TB"


class TestGetOutputName:
    def test_no_conversion(self):
        name = get_output_name("photo.jpg")
        assert name == f"photo {SUFFIX}.jpg"

    def test_png_to_webp(self):
        name = get_output_name("photo.png", png_to_webp=True)
        assert name == f"photo {SUFFIX}.webp"

    def test_jpg_to_webp(self):
        name = get_output_name("photo.jpg", jpg_to_webp=True)
        assert name == f"photo {SUFFIX}.webp"

    def test_jpeg_to_webp(self):
        name = get_output_name("photo.jpeg", jpg_to_webp=True)
        assert name == f"photo {SUFFIX}.webp"

    def test_webp_no_conversion(self):
        name = get_output_name("photo.webp", png_to_webp=True)
        assert name == f"photo {SUFFIX}.webp"

    def test_uppercase_ext(self):
        name = get_output_name("photo.PNG", png_to_webp=True)
        assert name == f"photo {SUFFIX}.webp"


class TestCompressImageStream:
    def test_jpeg_compression(self, jpeg_bytes):
        data, reverted = compress_image_stream(jpeg_bytes, 'JPEG')
        assert not reverted
        assert len(data) < len(jpeg_bytes)

    def test_png_compression(self, png_bytes):
        data, reverted = compress_image_stream(png_bytes, 'PNG')
        assert not reverted
        assert len(data) < len(png_bytes)

    def test_webp_compression(self, webp_bytes):
        data, reverted = compress_image_stream(webp_bytes, 'WEBP')
        with Image.open(io.BytesIO(data)) as img:
            assert img.format == 'WEBP'

    def test_png_to_webp(self, png_bytes):
        data, reverted = compress_image_stream(png_bytes, 'PNG', png_to_webp=True)
        assert not reverted
        with Image.open(io.BytesIO(data)) as img:
            assert img.format == 'WEBP'

    def test_jpg_to_webp(self, jpeg_bytes):
        data, reverted = compress_image_stream(jpeg_bytes, 'JPEG', jpg_to_webp=True)
        assert not reverted
        with Image.open(io.BytesIO(data)) as img:
            assert img.format == 'WEBP'

    def test_preserves_exif(self, jpeg_bytes):
        fake_exif = b"Exif\x00\x00"
        data, reverted = compress_image_stream(jpeg_bytes, 'JPEG', exif=fake_exif)
        assert not reverted
        with Image.open(io.BytesIO(data)) as img:
            exif = img.info.get('exif')
            assert exif is not None

    def test_preserves_icc(self, jpeg_bytes):
        fake_icc = b"ICC_PROFILE"
        data, reverted = compress_image_stream(jpeg_bytes, 'JPEG', icc_profile=fake_icc)
        assert not reverted
        with Image.open(io.BytesIO(data)) as img:
            icc = img.info.get('icc_profile')
            assert icc is not None

    def test_returns_original_on_exception(self):
        data, reverted = compress_image_stream(b"notanimage", 'JPEG')
        assert reverted
        assert data == b"notanimage"


class TestCompressImageFile:
    def test_jpeg_compression(self, jpeg_file, tmp_output_dir):
        output_path = os.path.join(tmp_output_dir, f"test {SUFFIX}.jpg")
        success, orig, new, ratio, final_path = compress_image_file(jpeg_file, output_path)
        assert success
        assert new < orig
        assert ratio > 0
        assert os.path.exists(final_path)

    def test_png_compression(self, png_file, tmp_output_dir):
        output_path = os.path.join(tmp_output_dir, f"test {SUFFIX}.png")
        success, orig, new, ratio, final_path = compress_image_file(png_file, output_path)
        assert success
        assert new < orig
        assert ratio > 0

    def test_webp_compression(self, webp_file, tmp_output_dir):
        output_path = os.path.join(tmp_output_dir, f"test {SUFFIX}.webp")
        success, orig, new, ratio, final_path = compress_image_file(webp_file, output_path)
        assert success
        assert new <= orig

    def test_png_to_webp(self, png_file, tmp_output_dir):
        output_path = os.path.join(tmp_output_dir, f"test {SUFFIX}.webp")
        success, orig, new, ratio, final_path = compress_image_file(png_file, output_path, png_to_webp=True)
        assert success
        assert final_path.endswith('.webp')

    def test_jpg_to_webp(self, jpeg_file, tmp_output_dir):
        output_path = os.path.join(tmp_output_dir, f"test {SUFFIX}.webp")
        success, orig, new, ratio, final_path = compress_image_file(jpeg_file, output_path, jpg_to_webp=True)
        assert success
        assert final_path.endswith('.webp')


class TestRemoveFile:
    def test_hard_delete(self, tmp_output_dir):
        path = os.path.join(tmp_output_dir, "test.txt")
        with open(path, "w") as f:
            f.write("hello")
        remove_file(path, soft=False)
        assert not os.path.exists(path)
