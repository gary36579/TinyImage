import io
import os
import tempfile
import pytest
from PIL import Image


@pytest.fixture
def tmp_output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def rgb_image():
    img = Image.new('RGB', (100, 100), color=(128, 128, 128))
    return img


@pytest.fixture
def rgba_image():
    img = Image.new('RGBA', (100, 100), color=(128, 128, 128, 255))
    return img


@pytest.fixture
def jpeg_bytes(rgb_image):
    buf = io.BytesIO()
    rgb_image.save(buf, format='JPEG', quality=95)
    return buf.getvalue()


@pytest.fixture
def png_bytes(rgba_image):
    buf = io.BytesIO()
    rgba_image.save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture
def webp_bytes(rgba_image):
    buf = io.BytesIO()
    rgba_image.save(buf, format='WebP', quality=95)
    return buf.getvalue()


@pytest.fixture
def jpeg_file(rgb_image, tmp_output_dir):
    path = os.path.join(tmp_output_dir, 'test.jpg')
    rgb_image.save(path, format='JPEG', quality=95)
    return path


@pytest.fixture
def png_file(rgba_image, tmp_output_dir):
    path = os.path.join(tmp_output_dir, 'test.png')
    rgba_image.save(path, format='PNG')
    return path


@pytest.fixture
def webp_file(rgba_image, tmp_output_dir):
    path = os.path.join(tmp_output_dir, 'test.webp')
    rgba_image.save(path, format='WebP', quality=95)
    return path


@pytest.fixture
def saved_globals():
    import main
    keys = ('SUFFIX', 'PNG_LEVEL_STREAM', 'WEBP_METHOD_STREAM',
            'IMG_EXTENSIONS', 'ARC_EXTENSIONS')
    saved = {k: getattr(main, k) for k in keys}
    yield
    for k, v in saved.items():
        setattr(main, k, v)
