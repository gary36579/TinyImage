import io
import os
import sys
import zipfile
import tempfile
import shutil
from PIL import Image
import pytest
from main import (
    format_size,
    get_output_name,
    compress_image_stream,
    compress_image_file,
    remove_file,
    fallback_copy,
    process_zip_in_memory,
    process_7z_with_tmp,
    is_hidden,
    _convert_format,
    _build_save_kwargs,
    _build_paths,
    _env_int,
    _env_str,
    _env_bool,
    _env_list,
    SUFFIX,
    PNG_LEVEL_STREAM,
    WEBP_METHOD_STREAM,
    IMG_EXTENSIONS,
    ARC_EXTENSIONS,
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
        assert not reverted
        assert len(data) < len(webp_bytes)
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
        assert new < orig
        assert ratio > 0

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

    def test_soft_delete(self, tmp_output_dir, monkeypatch):
        import main as main_module
        monkeypatch.setattr(main_module, 'HAS_SEND2TRASH', True)
        sent = []
        def fake_send2trash(p):
            sent.append(p)
        monkeypatch.setattr('send2trash.send2trash', fake_send2trash)
        path = os.path.join(tmp_output_dir, "test.txt")
        with open(path, "w") as f:
            f.write("hello")
        remove_file(path, soft=True)
        assert sent == [path]


class TestFallbackCopy:
    def test_copies_with_original_ext(self, tmp_output_dir):
        input_path = os.path.join(tmp_output_dir, 'photo.jpg')
        output_path = os.path.join(tmp_output_dir, f'photo {SUFFIX}.webp')
        with open(input_path, 'w') as f:
            f.write('original')
        result = fallback_copy(input_path, output_path)
        assert result == os.path.join(tmp_output_dir, f'photo {SUFFIX}.jpg')
        with open(result) as f:
            assert f.read() == 'original'

    def test_removes_failed_output(self, tmp_output_dir):
        input_path = os.path.join(tmp_output_dir, 'photo.jpg')
        output_path = os.path.join(tmp_output_dir, f'photo {SUFFIX}.webp')
        with open(input_path, 'w') as f:
            f.write('original')
        with open(output_path, 'w') as f:
            f.write('failed')
        result = fallback_copy(input_path, output_path)
        assert result.endswith('.jpg')
        assert not os.path.exists(output_path)

    def test_skips_remove_when_same_ext(self, tmp_output_dir):
        input_path = os.path.join(tmp_output_dir, 'photo.jpg')
        output_path = os.path.join(tmp_output_dir, f'photo {SUFFIX}.jpg')
        with open(input_path, 'w') as f:
            f.write('original')
        with open(output_path, 'w') as f:
            f.write('compressed')
        result = fallback_copy(input_path, output_path)
        assert result == output_path
        # output_path should still exist (not deleted since same path)
        assert os.path.exists(result)


class TestCompressImageStream:
    def test_zero_quality_jpeg(self, jpeg_bytes):
        data, reverted = compress_image_stream(jpeg_bytes, 'JPEG', quality=5)
        assert not reverted
        assert len(data) < len(jpeg_bytes)

    def test_png_compress_level_zero(self, png_bytes):
        data, reverted = compress_image_stream(png_bytes, 'PNG', png_level=0)
        assert not reverted

    def test_jpeg_progressive_disabled(self, jpeg_bytes):
        data, reverted = compress_image_stream(jpeg_bytes, 'JPEG', jpeg_progressive=False)
        assert not reverted
        assert len(data) < len(jpeg_bytes)


class TestCompressImageFile:
    def test_invalid_image_fallback(self, tmp_output_dir):
        input_path = os.path.join(tmp_output_dir, 'corrupt.jpg')
        output_path = os.path.join(tmp_output_dir, f'corrupt {SUFFIX}.webp')
        with open(input_path, 'wb') as f:
            f.write(b'not an image at all')
        success, orig, new, ratio, final_path = compress_image_file(
            input_path, output_path)
        assert success
        assert orig == new
        assert ratio == 0.0
        assert os.path.exists(final_path)

    def test_with_custom_params(self, jpeg_file, tmp_output_dir):
        output_path = os.path.join(tmp_output_dir, f'test {SUFFIX}.jpg')
        success, orig, new, ratio, final_path = compress_image_file(
            jpeg_file, output_path, quality=50, jpeg_progressive=False)
        assert success
        assert new < orig


class TestEnvHelpers:
    def test_env_int_with_env(self, monkeypatch):
        monkeypatch.setenv('TEST_INT', '42')
        assert _env_int('TEST_INT', 0) == 42

    def test_env_int_without_env(self):
        assert _env_int('NONEXISTENT_INT', 99) == 99

    def test_env_int_invalid(self, monkeypatch):
        monkeypatch.setenv('TEST_INT', 'abc')
        assert _env_int('TEST_INT', 10) == 10

    def test_env_str_with_env(self, monkeypatch):
        monkeypatch.setenv('TEST_STR', 'hello')
        assert _env_str('TEST_STR', 'default') == 'hello'

    def test_env_str_without_env(self):
        assert _env_str('NONEXISTENT_STR', 'default') == 'default'

    def test_env_bool_true(self, monkeypatch):
        monkeypatch.setenv('TEST_BOOL', 'true')
        assert _env_bool('TEST_BOOL', False) is True

    def test_env_bool_false(self, monkeypatch):
        monkeypatch.setenv('TEST_BOOL', 'false')
        assert _env_bool('TEST_BOOL', True) is False

    def test_env_bool_without_env(self):
        assert _env_bool('NONEXISTENT_BOOL', True) is True

    def test_env_list_with_env(self, monkeypatch):
        monkeypatch.setenv('TEST_LIST', 'a,b,c')
        assert _env_list('TEST_LIST', ('x',)) == ('a', 'b', 'c')

    def test_env_list_without_env(self):
        assert _env_list('NONEXISTENT_LIST', ('.a',)) == ('.a',)


class TestIsHidden:
    def test_normal_file_not_hidden(self, tmp_output_dir):
        path = os.path.join(tmp_output_dir, 'visible.txt')
        with open(path, 'w') as f:
            f.write('')
        assert not is_hidden(path)

    def test_nonexistent_path_not_hidden(self):
        assert not is_hidden(r'C:\__nonexistent_path_test_12345__')


class TestProcessZipInMemory:
    def test_basic_zip_compression(self, jpeg_bytes, png_bytes, tmp_output_dir):
        input_zip = os.path.join(tmp_output_dir, 'input.zip')
        with zipfile.ZipFile(input_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('photo.jpg', jpeg_bytes)
            zf.writestr('photo.png', png_bytes)
        output_zip = os.path.join(tmp_output_dir, f'input {SUFFIX}.zip')
        o, n = process_zip_in_memory(input_zip, output_zip, executor=None,
                                      quality=80, png_level=9, webp_method=6)
        assert os.path.exists(output_zip)
        assert n > 0
        assert o > n
        with zipfile.ZipFile(output_zip, 'r') as zf:
            names = zf.namelist()
            assert 'photo.jpg' in names or f'photo {SUFFIX}.jpg' in names

    def test_zip_skips_already_processed(self, jpeg_bytes, tmp_output_dir):
        input_zip = os.path.join(tmp_output_dir, 'input.zip')
        with zipfile.ZipFile(input_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f'photo {SUFFIX}.jpg', jpeg_bytes)
        output_zip = os.path.join(tmp_output_dir, f'input {SUFFIX}.zip')
        o, n = process_zip_in_memory(input_zip, output_zip, executor=None, override=False)
        assert os.path.exists(output_zip)
        with zipfile.ZipFile(output_zip, 'r') as zf:
            assert f'photo {SUFFIX}.jpg' in zf.namelist()

    def test_zip_png_to_webp(self, png_bytes, tmp_output_dir):
        input_zip = os.path.join(tmp_output_dir, 'input.zip')
        with zipfile.ZipFile(input_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('photo.png', png_bytes)
        output_zip = os.path.join(tmp_output_dir, f'input {SUFFIX}.zip')
        o, n = process_zip_in_memory(input_zip, output_zip, executor=None,
                                      png_to_webp=True)
        assert os.path.exists(output_zip)
        with zipfile.ZipFile(output_zip, 'r') as zf:
            assert any(name.endswith('.webp') for name in zf.namelist())


class TestProcess7zWithTmp:
    def test_basic_7z_compression(self, jpeg_file, png_file, tmp_output_dir):
        try:
            import py7zr
        except ImportError:
            pytest.skip('py7zr not installed')
        input_7z = os.path.join(tmp_output_dir, 'input.7z')
        with py7zr.SevenZipFile(input_7z, 'w') as szf:
            szf.write(jpeg_file, 'photo.jpg')
            szf.write(png_file, 'photo.png')
        output_7z = os.path.join(tmp_output_dir, f'input {SUFFIX}.7z')
        o, n = process_7z_with_tmp(input_7z, output_7z, executor=None)
        assert os.path.exists(output_7z)
        assert n > 0
        assert o > n

    def test_7z_skips_already_processed(self, jpeg_file, tmp_output_dir):
        try:
            import py7zr
        except ImportError:
            pytest.skip('py7zr not installed')
        input_7z = os.path.join(tmp_output_dir, 'input.7z')
        with py7zr.SevenZipFile(input_7z, 'w') as szf:
            szf.write(jpeg_file, f'photo {SUFFIX}.jpg')
        output_7z = os.path.join(tmp_output_dir, f'input {SUFFIX}.7z')
        o, n = process_7z_with_tmp(input_7z, output_7z, executor=None, override=False)
        assert os.path.exists(output_7z)


class TestConvertFormat:
    def test_png_to_webp(self):
        assert _convert_format('PNG', png_to_webp=True, jpg_to_webp=False) == 'WEBP'

    def test_jpeg_to_webp(self):
        assert _convert_format('JPEG', png_to_webp=False, jpg_to_webp=True) == 'WEBP'

    def test_no_conversion(self):
        assert _convert_format('PNG', png_to_webp=False, jpg_to_webp=False) == 'PNG'

    def test_webp_unchanged(self):
        assert _convert_format('WEBP', png_to_webp=True, jpg_to_webp=True) == 'WEBP'

    def test_jpg_to_webp_priority(self):
        assert _convert_format('JPEG', png_to_webp=True, jpg_to_webp=True) == 'WEBP'


class TestBuildSaveKwargs:
    def test_jpeg_kwargs(self):
        kw = _build_save_kwargs('JPEG', None, None, quality=85, png_level=9, webp_method=6, jpeg_progressive=False)
        assert kw == {'optimize': True, 'quality': 85, 'progressive': False}

    def test_webp_kwargs(self):
        kw = _build_save_kwargs('WEBP', None, None, quality=75, png_level=9, webp_method=4, jpeg_progressive=True)
        assert kw == {'optimize': True, 'quality': 75, 'method': 4}

    def test_png_kwargs(self):
        kw = _build_save_kwargs('PNG', None, None, quality=80, png_level=7, webp_method=6, jpeg_progressive=True)
        assert kw == {'optimize': True, 'compress_level': 7}

    def test_with_exif_and_icc(self):
        kw = _build_save_kwargs('JPEG', b'exif', b'icc', quality=80, png_level=9, webp_method=6, jpeg_progressive=True)
        assert kw['exif'] == b'exif'
        assert kw['icc_profile'] == b'icc'


class TestBuildPaths:
    def test_basic_paths(self, tmp_output_dir):
        root = os.path.join(tmp_output_dir, 'sub')
        os.makedirs(root)
        src = os.path.join(root, 'photo.jpg')
        with open(src, 'w') as f:
            f.write('')
        inp, out = _build_paths(root, 'photo.jpg', 'photo.jpg', tmp_output_dir, png_to_webp=False, jpg_to_webp=False)
        assert inp == src
        assert out == os.path.join(tmp_output_dir, f'photo {SUFFIX}.jpg')

    def test_with_rel_subdir(self, tmp_output_dir):
        root = os.path.join(tmp_output_dir, 'nested')
        os.makedirs(root)
        src = os.path.join(root, 'img.png')
        with open(src, 'w') as f:
            f.write('')
        inp, out = _build_paths(root, 'img.png', 'nested/img.png', tmp_output_dir, png_to_webp=True, jpg_to_webp=False)
        assert inp == src
        assert out == os.path.join(tmp_output_dir, 'nested', f'img {SUFFIX}.webp')


def _clean_ansi(text):
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


class TestThreeTierPriority:
    """Integration tests: CLI > env > default via main() --show-config."""

    @pytest.mark.usefixtures('saved_globals')
    def test_default_values_in_show_config(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '80   (default)' in clean
        assert '[minify]   (default)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_env_overrides_default(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_QUALITY', '95')
        monkeypatch.setenv('TINYIMAGE_SUFFIX', '_from_env')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '95   (env)' in clean
        assert '_from_env   (env)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_cli_overrides_env(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_QUALITY', '95')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config', '--quality', '70'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '70   (CLI)' in clean
        assert '95   (env)' not in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_cli_overrides_default(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config', '--webp-method', '4'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '4   (CLI)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_img_exts_from_cli(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config', '--img-exts', '.png,.webp'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '.png, .webp   (CLI)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_suffix_from_cli(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config', '--suffix', '_custom'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '_custom   (CLI)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_png_level_stream_from_cli(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config', '--png-level-stream', '7'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '7   (CLI)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_png_to_webp_from_env(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_PNG_TO_WEBP', 'true')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert 'True   (env)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_jpg_to_webp_from_env(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_JPG_TO_WEBP', 'true')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert 'True   (env)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_override_from_env(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_OVERRIDE', 'true')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert 'True   (env)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_workers_from_env(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_WORKERS', '2')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '2   (env)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_png_to_webp_cli_overrides_env(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_PNG_TO_WEBP', 'false')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config', '--png-to-webp'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert 'True   (CLI)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_workers_cli_overrides_env(self, capsys, monkeypatch):
        monkeypatch.setenv('TINYIMAGE_WORKERS', '8')
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config', '--workers', '4'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert '4   (CLI)' in clean

    @pytest.mark.usefixtures('saved_globals')
    def test_jpg_to_webp_default_false(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['main.py', '--show-config'])
        import main
        main.main()
        clean = _clean_ansi(capsys.readouterr().out)
        assert 'False   (default)' in clean


class TestEdgeCases:
    def test_empty_file_bypass(self, tmp_output_dir):
        input_path = os.path.join(tmp_output_dir, 'empty.jpg')
        output_path = os.path.join(tmp_output_dir, f'empty {SUFFIX}.webp')
        with open(input_path, 'wb') as f:
            f.write(b'')
        success, orig, new, ratio, final_path = compress_image_file(
            input_path, output_path)
        assert success
        assert orig == new
        assert ratio == 0.0
        assert os.path.exists(final_path)

    def test_unsupported_format_passthrough(self, tmp_output_dir):
        input_path = os.path.join(tmp_output_dir, 'readme.txt')
        output_path = os.path.join(tmp_output_dir, f'readme {SUFFIX}.txt')
        with open(input_path, 'w') as f:
            f.write('not an image')
        # Falls through except → fallback_copy
        success, orig, new, ratio, final_path = compress_image_file(
            input_path, output_path)
        assert success
        assert orig == new
        assert os.path.exists(final_path)
