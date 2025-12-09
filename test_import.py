#!/usr/bin/env python
try:
    from app.hydro_system.routes.device_router import device_router
    from app.hydro_system.controllers.device_controller import control_devices_by_location
    from app.hydro_system.services.device_service import hydro_device_service
    print("[OK] All imports successful!")
    print(f"device_router routes: {[r.path for r in device_router.routes]}")
except Exception as e:
    print(f"[ERROR] Import error: {e}")
    import traceback
    traceback.print_exc()
