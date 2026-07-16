import io
from pathlib import Path

import requests
from PIL import Image, ImageEnhance

from core import xhs_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = PROJECT_ROOT / "data" / "drafts"

TARGET_RATIO = 3 / 4  # width / height, XHS's common image-note ratio
BRIGHTNESS_FACTOR = 1.03
CONTRAST_FACTOR = 1.05


def _center_crop_to_ratio(img):
    width, height = img.size
    current_ratio = width / height
    if current_ratio > TARGET_RATIO:
        new_width = int(height * TARGET_RATIO)
        left = (width - new_width) // 2
        img = img.crop((left, 0, left + new_width, height))
    elif current_ratio < TARGET_RATIO:
        new_height = int(width / TARGET_RATIO)
        top = (height - new_height) // 2
        img = img.crop((0, top, width, top + new_height))
    return img


def process_note_images(draft_id, image_urls):
    """Fetch watermark-free versions of each image, crop to 3:4, adjust brightness/contrast,
    and save under data/drafts/<draft_id>/. Returns local file paths."""
    out_dir = DRAFTS_DIR / str(draft_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for idx, url in enumerate(image_urls):
        no_water_url = xhs_client.call("pc", "get_note_no_water_img", {"img_url": url})
        resp = requests.get(no_water_url, timeout=30)
        resp.raise_for_status()

        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img = _center_crop_to_ratio(img)
        img = ImageEnhance.Brightness(img).enhance(BRIGHTNESS_FACTOR)
        img = ImageEnhance.Contrast(img).enhance(CONTRAST_FACTOR)

        out_path = out_dir / f"{idx}.jpg"
        img.save(out_path, "JPEG", quality=92)
        saved_paths.append(str(out_path))

    return saved_paths
