# backend/app/init_db.py
from .database import engine, Base
from .android_system.models.device import Device
from .hydro_system.models.device import HydroDevice
from .hydro_system.models.actuator import HydroActuator
from .hydro_system.models.sensor_data import SensorData
from .hydro_system.models.plant import Plant
from .hydro_system.models.plant_batch import PlantBatch
from .hydro_system.models.growth_stage import GrowthStage
from .hydro_system.models.growth_recipe import GrowthRecipe
from .hydro_system.models.schedule import HydroSchedule

from .user.models.user import User
from .user.models.password_reset import PasswordResetCode
from .user.models.role import Role
from .user.models.user_role import UserRole
from .camera_object_detection.models.detection import DetectionResult, DetectionObject
from .camera_object_detection.models.hardware_detection import HardwareDetection, LocationHardwareInventory, HardwareDetectionSummary
from .migration.models.base_data import RawData
from .transform_data.models.template import Template
from .payments.models.payment import PaymentTransaction
from .jackpot.models.draw import Draw, Ticket, PrizeResult
from .product.models.product import Product, ProductVariant
def init_db():
# ✅ This registers all imported models and creates the tables
    Base.metadata.create_all(bind=engine)
