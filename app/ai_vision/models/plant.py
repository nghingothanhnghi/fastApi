# app/ai_vision/models/plant.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, func
from sqlalchemy.orm import relationship
from app.database import Base


class VisionCamera(Base):
    __tablename__ = "ai_vision_cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    camera_type = Column(String(30), nullable=False, default="ip_camera")  # ip_camera | esp32_cam | upload
    stream_url = Column(String(500), nullable=True)
    location = Column(String(150), nullable=True)  # matches HydroDevice.location for correlation
    hydro_device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    # ✅ NEW — tenant scoping, same convention as HydroDevice.client_id
    client_id = Column(String, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    plants = relationship("VisionPlant", back_populates="camera")


class VisionPlant(Base):
    __tablename__ = "ai_vision_plants"

    id = Column(Integer, primary_key=True, index=True)
    species = Column(String(100), nullable=False)
    variety = Column(String(100), nullable=True)
    location = Column(String(150), nullable=True)
    growing_system = Column(String(50), nullable=True)  # nft, dwc, ebb_flow, aeroponic...
    planted_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, default="growing")  # growing|harvested|removed

    # ✅ NEW — tenant scoping
    client_id = Column(String, nullable=True, index=True)

    # Optional link into the existing hydro batch/plant metadata, so vision
    # data can be correlated with GrowthStage/GrowthRecipe without duplicating them.
    hydro_plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True, index=True)
    hydro_batch_id = Column(Integer, ForeignKey("plant_batches.id"), nullable=True, index=True)

    camera_id = Column(Integer, ForeignKey("ai_vision_cameras.id"), nullable=True)
    camera = relationship("VisionCamera", back_populates="plants")

    expected_growth_profile = Column(JSON, nullable=True)  # e.g. {"canopy_growth_pct_per_day": 3.8}

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<VisionPlant(id={self.id}, species={self.species!r}, status={self.status})>"
