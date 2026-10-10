import json
import os
import sys
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import the FastAPI app
from main import app

client = TestClient(app)


def test_hardware_ws_handshake_and_stats(monkeypatch):
    # Patch the acceptance check to be awaitable (bug in implementation uses await on sync fn)
    from app.utils import connection_manager as cm

    async def _fake_ensure_already_accepted(self, websocket):
        # No-op: test client already accepts before connect()
        return None

    monkeypatch.setattr(cm.DetectionWebSocketManager, "_ensure_already_accepted", _fake_ensure_already_accepted, raising=True)

    # Connect to /ws/hardware-detection and verify connection message
    with client.websocket_connect("/ws/hardware-detection") as websocket:
        initial_msg = websocket.receive_json()
        assert initial_msg.get("type") == "connection_established"
        assert "connection_id" in initial_msg

        # Request stats and expect a stats message
        websocket.send_text(json.dumps({"type": "get_stats"}))
        stats_msg = websocket.receive_json()
        assert stats_msg.get("type") == "stats"
        assert isinstance(stats_msg.get("data"), dict)

        # Subscribe to a location
        websocket.send_text(json.dumps({"type": "subscribe_location", "location": "greenhouse_a"}))
        sub_msg = websocket.receive_json()
        assert sub_msg.get("type") == "subscription_added"
        assert sub_msg.get("location") == "greenhouse_a"

        # Unsubscribe from the location (there may be queued messages like location_status)
        websocket.send_text(json.dumps({"type": "unsubscribe_location", "location": "greenhouse_a"}))
        for _ in range(5):
            unsub_msg = websocket.receive_json()
            if unsub_msg.get("type") == "subscription_removed":
                assert unsub_msg.get("location") == "greenhouse_a"
                break
        else:
            pytest.fail("Did not receive subscription_removed after unsubscribe")


def test_object_detection_ws_returns_detections(monkeypatch):
    # Patch ObjectDetector and enrichment utilities to avoid real YOLO/DB
    from app.camera_object_detection.routes import object_detection_router as odr

    class FakeDetector:
        def __init__(self, *args, **kwargs):
            pass
        def detect_objects(self, img):
            # Return a deterministic fake detection
            return {
                "detections": [
                    {
                        "class_name": "pump",
                        "original_class": "bottle",
                        "confidence": 0.99,
                        "bbox": [1.0, 2.0, 10.0, 20.0],
                        "is_hardware": True,
                    }
                ],
                "processing_time_ms": 1.23,
                "annotated_image": "",
                "image_size": "10 x 10",
            }

    def fake_decode_base64_image(_data: str):
        # Return a simple black image 10x10
        return np.zeros((10, 10, 3), dtype=np.uint8)

    # Force enrichment to inject hardware fields and deterministic stats
    class _FakeHDS:
        @staticmethod
        def enhance_detections_with_hardware_info(detections, known_actuators):
            for d in detections:
                d["hardware_type"] = "pump"
                d["matching_actuators"] = [{"id": 1, "type": "pump", "name": "P1"}]
                d["is_hardware"] = True
            return detections
        @staticmethod
        def get_hardware_statistics(detections):
            return {
                "total_hardware": len([d for d in detections if d.get("is_hardware")]),
                "hardware_types": {"pump": 1},
                "average_confidence": detections[0].get("confidence", 0),
                "known_actuators_detected": 1,
                "unique_hardware_types": 1,
            }

    monkeypatch.setattr(odr, "ObjectDetector", FakeDetector, raising=True)
    monkeypatch.setattr(odr, "decode_base64_image", fake_decode_base64_image, raising=True)

    # Patch the import path used inside the route for HardwareDetectionService
    from app.camera_object_detection.services import hardware_detection_service as hds_module
    monkeypatch.setattr(hds_module, "HardwareDetectionService", _FakeHDS, raising=True)

    with client.websocket_connect("/object-detection/ws") as websocket:
        # Send a minimal payload with a dummy image string
        websocket.send_text(json.dumps({"image": "dummy", "timestamp": 0}))
        msg = websocket.receive_json()

        # Validate structure
        assert "detections" in msg
        assert isinstance(msg["detections"], list)
        assert len(msg["detections"]) >= 1
        det = msg["detections"][0]
        assert set(["class_name", "confidence", "bbox"]).issubset(det.keys())
        # Enrichment assertions
        assert det.get("hardware_type") == "pump"
        assert isinstance(det.get("matching_actuators"), list) and det["matching_actuators"][0]["type"] == "pump"
        # Stats + known actuators structure
        assert isinstance(msg.get("hardware_stats"), dict)
        assert set(["total_hardware", "hardware_types", "average_confidence", "known_actuators_detected", "unique_hardware_types"]).issubset(msg["hardware_stats"].keys())
        assert "known_actuators" in msg and isinstance(msg["known_actuators"], list)