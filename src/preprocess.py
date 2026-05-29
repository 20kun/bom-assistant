"""Image preprocessing for BOM extraction — deskew, enhance, sharpen."""

import io
from typing import Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


MAX_DIM = 2048  # max width/height, resize if larger
MIN_DIM = 480   # min dimension, skip if too small


def preprocess_image(
    image_bytes: bytes,
    sharpen: bool = True,
    contrast: bool = True,
    deskew: bool = True,
) -> bytes:
    """Preprocess image for better OCR/vision recognition.

    Pipeline: resize → grayscale-detect-skew → contrast → sharpen → encode back
    """
    img = Image.open(io.BytesIO(image_bytes))

    # Convert RGBA/P to RGB
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Resize large images (keep aspect ratio)
    w, h = img.size
    if max(w, h) > MAX_DIM:
        scale = MAX_DIM / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    if min(img.size) < MIN_DIM:
        # Too small, skip processing
        return _to_bytes(img)

    # Convert to numpy for OpenCV operations
    img_np = np.array(img)

    if deskew:
        angle = _detect_skew_angle(img_np)
        if abs(angle) > 0.3:
            img = _rotate_image(img, angle)
            img_np = np.array(img)

    if contrast:
        # CLAHE on L channel of LAB
        try:
            import cv2
            lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            img_np = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
            img = Image.fromarray(img_np)
        except ImportError:
            # Fallback: PIL enhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)

    if sharpen:
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

    return _to_bytes(img)


def _detect_skew_angle(img_np: np.ndarray) -> float:
    """Detect skew angle using line detection on edges."""
    try:
        import cv2
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) < 100:
            return 0.0

        angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
        if angle < -45:
            angle = 90 + angle
        return -angle
    except ImportError:
        return 0.0


def _rotate_image(image: Image.Image, angle: float) -> Image.Image:
    """Rotate image by angle, expand canvas to fit."""
    return image.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(255, 255, 255))


def _to_bytes(img: Image.Image, format: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=format, optimize=True)
    buf.seek(0)
    return buf.getvalue()
