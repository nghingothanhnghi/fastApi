import qrcode
import os
from app.core import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class QRService:
    @staticmethod
    def generate_product_qr(product_id: int, data: str = None) -> str:
        """
        Generate a QR code for a product.
        If data is not provided, it defaults to a URL pointing to the product info.
        """
        if not data:
            # Default to a mock URL or just the product ID
            # In a real scenario, this would be a frontend URL
            data = f"https://your-frontend-domain.com/product/{product_id}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        
        # Ensure directory exists
        os.makedirs(config.QR_CODE_DIR, exist_ok=True)
        
        filename = f"product_{product_id}.png"
        file_path = os.path.join(config.QR_CODE_DIR, filename)
        
        try:
            img.save(file_path)
            logger.info("QR code generated", extra={"product_id": product_id, "path": file_path})
            return f"{config.QR_CODE_URL}/{filename}"
        except Exception:
            logger.exception("Failed to save QR code", extra={"product_id": product_id, "path": file_path})
            raise
