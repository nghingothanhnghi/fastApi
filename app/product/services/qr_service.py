
import qrcode
from urllib.parse import urljoin
import os
from app.core import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class QRService:
    @staticmethod
    def generate_product_qr(
        product_id: int,
        payload: str | None = None,
    ) -> str:
        """
        Generate (or regenerate) a QR code for a product.

        The QR payload is intentionally domain-agnostic.
        It encodes a relative resource identifier, not a full URL.

        Args:
            product_id (int): Product ID
            payload (str | None): Custom QR payload.
                                   Defaults to `/products/{id}/scan`.

        Returns:
            str: Public QR image URL (relative, frontend-safe)
        """

        # Default payload (NO domain)
        if not payload:
            payload = f"/products/{product_id}/scan"

        # Ensure QR directory exists
        os.makedirs(config.QR_CODE_DIR, exist_ok=True)

        filename = f"product_{product_id}.png"
        file_path = os.path.join(config.QR_CODE_DIR, filename)

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(payload)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            img.save(file_path)

            logger.info(
                "QR code generated",
                extra={
                    "product_id": product_id,
                    "payload": payload,
                    "path": file_path,
                },
            )

        except Exception:
            logger.exception(
                "Failed to generate QR code",
                extra={"product_id": product_id, "path": file_path},
            )
            raise

        # Public path (NO domain)
        return urljoin(
            config.QR_CODE_URL.rstrip("/") + "/",
            filename,
        )