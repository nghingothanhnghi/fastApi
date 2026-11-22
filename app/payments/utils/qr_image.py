# app/payments/utils/qr_image.py
"""Decode a QR image to text. Uses OpenCV if installed, else pyzbar.

Both are optional: if neither is installed QrReaderUnavailable is raised and the
API answers 501 (manual entry still works).
"""


class QrReaderUnavailable(RuntimeError):
    pass


class QrNotFound(ValueError):
    pass


def decode_qr(data: bytes) -> str:
    try:
        import cv2
        import numpy as np
    except ImportError:
        cv2 = None

    if cv2 is not None:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise QrNotFound("File is not a readable image")
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        if not text:
            # retry on grayscale + upscale; phone screenshots are often small
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            text, _, _ = cv2.QRCodeDetector().detectAndDecode(gray)
        if not text:
            raise QrNotFound("No QR code found in the image")
        return text

    try:
        from PIL import Image
        from pyzbar.pyzbar import decode
        import io
    except ImportError as e:
        raise QrReaderUnavailable(
            "Install opencv-python-headless (or pyzbar + pillow) to read QR images"
        ) from e

    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise QrNotFound("File is not a readable image") from e
    results = decode(img)
    if not results:
        raise QrNotFound("No QR code found in the image")
    return results[0].data.decode("utf-8", errors="strict")
