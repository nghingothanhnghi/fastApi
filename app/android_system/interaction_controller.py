# app/android_system/interaction_controller.py
# Touch simulation and device interaction logic

import logging
import threading
from typing import List, Dict, Any, Optional
from app.android_system.device_manager import device_manager
from app.android_system.config import TOUCH_CONFIG

logger = logging.getLogger(__name__)

class InteractionController:
    """Handles touch simulation and device interactions"""
    
    def __init__(self):
        self.device_manager = device_manager
    
    def tap_device(self, serial: str, x: int = None, y: int = None) -> Dict[str, Any]:
        """Tap on a specific device"""
        try:
            device = self.device_manager.get_device_by_serial(serial)
            if not device:
                return {
                    "success": False,
                    "error": f"Device {serial} not found",
                    "device": serial
                }
            
            # Use default coordinates if not provided
            tap_x = x if x is not None else TOUCH_CONFIG["default_x"]
            tap_y = y if y is not None else TOUCH_CONFIG["default_y"]
            
            # Execute tap
            try:
                if hasattr(device, 'tap') and callable(device.tap):
                    # For mock devices that have a direct tap method
                    device.tap(tap_x, tap_y)
                else:
                    # For real devices using shell command
                    device.shell(f"input tap {tap_x} {tap_y}")
                
                logger.info(f"Tapped device {serial} at ({tap_x}, {tap_y})")
                
                return {
                    "success": True,
                    "message": "Tap executed successfully",
                    "device": serial,
                    "coordinates": {"x": tap_x, "y": tap_y},
                    "using_mock": self.device_manager.adb_client.is_mock
                }
                
            except Exception as e:
                logger.error(f"Error tapping device {serial}: {str(e)}")
                return {
                    "success": False,
                    "error": f"Error tapping device: {str(e)}",
                    "device": serial
                }
                
        except Exception as e:
            logger.error(f"Error in tap_device: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "device": serial
            }
    
    def tap_all_devices(self, x: int = None, y: int = None) -> Dict[str, Any]:
        """Tap on all connected devices"""
        try:
            devices = self.device_manager.adb_client.get_devices()
            
            if not devices:
                return {
                    "success": True,
                    "message": "No devices found",
                    "coordinates": {"x": x, "y": y},
                    "devices": [],
                    "results": [],
                    "using_mock": self.device_manager.adb_client.is_mock
                }
            
            # Use default coordinates if not provided
            tap_x = x if x is not None else TOUCH_CONFIG["default_x"]
            tap_y = y if y is not None else TOUCH_CONFIG["default_y"]
            
            results = []
            device_serials = []
            
            def tap_single_device(device):
                try:
                    if hasattr(device, 'tap') and callable(device.tap):
                        device.tap(tap_x, tap_y)
                    else:
                        device.shell(f"input tap {tap_x} {tap_y}")
                    
                    results.append({
                        "device": device.serial,
                        "success": True,
                        "message": "Tap executed successfully"
                    })
                    logger.info(f"Tapped device {device.serial} at ({tap_x}, {tap_y})")
                    
                except Exception as e:
                    results.append({
                        "device": device.serial,
                        "success": False,
                        "error": str(e)
                    })
                    logger.error(f"Error tapping device {device.serial}: {str(e)}")
            
            # Execute taps in parallel
            threads = [threading.Thread(target=tap_single_device, args=(device,)) for device in devices]
            device_serials = [device.serial for device in devices]
            
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            
            return {
                "success": True,
                "message": f"Tap executed on {len(devices)} devices",
                "coordinates": {"x": tap_x, "y": tap_y},
                "devices": device_serials,
                "results": results,
                "using_mock": self.device_manager.adb_client.is_mock
            }
            
        except Exception as e:
            logger.error(f"Error in tap_all_devices: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "coordinates": {"x": x, "y": y},
                "devices": [],
                "results": []
            }
    
    def swipe_device(self, serial: str, start_x: int = None, start_y: int = None, 
                    end_x: int = None, end_y: int = None, duration: int = None) -> Dict[str, Any]:
        """Swipe on a specific device"""
        try:
            device = self.device_manager.get_device_by_serial(serial)
            if not device:
                return {
                    "success": False,
                    "error": f"Device {serial} not found",
                    "device": serial
                }
            
            # Use default values if not provided
            swipe_start_x = start_x if start_x is not None else TOUCH_CONFIG["default_x"]
            swipe_start_y = start_y if start_y is not None else TOUCH_CONFIG["default_y"]
            swipe_end_x = end_x if end_x is not None else TOUCH_CONFIG["default_x"] + 200
            swipe_end_y = end_y if end_y is not None else TOUCH_CONFIG["default_y"]
            swipe_duration = duration if duration is not None else TOUCH_CONFIG["swipe_duration"]
            
            # Execute swipe
            try:
                if hasattr(device, 'swipe') and callable(device.swipe):
                    # For mock devices that have a direct swipe method
                    device.swipe(swipe_start_x, swipe_start_y, swipe_end_x, swipe_end_y, swipe_duration)
                else:
                    # For real devices using shell command
                    device.shell(f"input swipe {swipe_start_x} {swipe_start_y} {swipe_end_x} {swipe_end_y} {swipe_duration}")
                
                logger.info(f"Swiped device {serial} from ({swipe_start_x}, {swipe_start_y}) to ({swipe_end_x}, {swipe_end_y})")
                
                return {
                    "success": True,
                    "message": "Swipe executed successfully",
                    "device": serial,
                    "start": {"x": swipe_start_x, "y": swipe_start_y},
                    "end": {"x": swipe_end_x, "y": swipe_end_y},
                    "duration_ms": swipe_duration,
                    "using_mock": self.device_manager.adb_client.is_mock
                }
                
            except Exception as e:
                logger.error(f"Error swiping device {serial}: {str(e)}")
                return {
                    "success": False,
                    "error": f"Error swiping device: {str(e)}",
                    "device": serial
                }
                
        except Exception as e:
            logger.error(f"Error in swipe_device: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "device": serial
            }
    
    def swipe_all_devices(self, start_x: int = None, start_y: int = None,
                         end_x: int = None, end_y: int = None, duration: int = None) -> Dict[str, Any]:
        """Swipe on all connected devices"""
        try:
            devices = self.device_manager.adb_client.get_devices()
            
            if not devices:
                return {
                    "success": True,
                    "message": "No devices found",
                    "start": {"x": start_x, "y": start_y},
                    "end": {"x": end_x, "y": end_y},
                    "duration_ms": duration,
                    "devices": [],
                    "results": [],
                    "using_mock": self.device_manager.adb_client.is_mock
                }
            
            # Use default values if not provided
            swipe_start_x = start_x if start_x is not None else TOUCH_CONFIG["default_x"]
            swipe_start_y = start_y if start_y is not None else TOUCH_CONFIG["default_y"]
            swipe_end_x = end_x if end_x is not None else TOUCH_CONFIG["default_x"] + 200
            swipe_end_y = end_y if end_y is not None else TOUCH_CONFIG["default_y"]
            swipe_duration = duration if duration is not None else TOUCH_CONFIG["swipe_duration"]
            
            results = []
            device_serials = []
            
            def swipe_single_device(device):
                try:
                    if hasattr(device, 'swipe') and callable(device.swipe):
                        device.swipe(swipe_start_x, swipe_start_y, swipe_end_x, swipe_end_y, swipe_duration)
                    else:
                        device.shell(f"input swipe {swipe_start_x} {swipe_start_y} {swipe_end_x} {swipe_end_y} {swipe_duration}")
                    
                    results.append({
                        "device": device.serial,
                        "success": True,
                        "message": "Swipe executed successfully"
                    })
                    logger.info(f"Swiped device {device.serial} from ({swipe_start_x}, {swipe_start_y}) to ({swipe_end_x}, {swipe_end_y})")
                    
                except Exception as e:
                    results.append({
                        "device": device.serial,
                        "success": False,
                        "error": str(e)
                    })
                    logger.error(f"Error swiping device {device.serial}: {str(e)}")
            
            # Execute swipes in parallel
            threads = [threading.Thread(target=swipe_single_device, args=(device,)) for device in devices]
            device_serials = [device.serial for device in devices]
            
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            
            return {
                "success": True,
                "message": f"Swipe executed on {len(devices)} devices",
                "start": {"x": swipe_start_x, "y": swipe_start_y},
                "end": {"x": swipe_end_x, "y": swipe_end_y},
                "duration_ms": swipe_duration,
                "devices": device_serials,
                "results": results,
                "using_mock": self.device_manager.adb_client.is_mock
            }
            
        except Exception as e:
            logger.error(f"Error in swipe_all_devices: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "start": {"x": start_x, "y": start_y},
                "end": {"x": end_x, "y": end_y},
                "duration_ms": duration,
                "devices": [],
                "results": []
            }
    
    def execute_shell_command(self, serial: str, command: str) -> Dict[str, Any]:
        """Execute shell command on specific device"""
        try:
            device = self.device_manager.get_device_by_serial(serial)
            if not device:
                return {
                    "success": False,
                    "error": f"Device {serial} not found",
                    "device": serial
                }
            
            result = device.shell(command)
            logger.info(f"Executed command '{command}' on device {serial}")
            
            return {
                "success": True,
                "message": "Command executed successfully",
                "device": serial,
                "command": command,
                "result": result,
                "using_mock": self.device_manager.adb_client.is_mock
            }
            
        except Exception as e:
            logger.error(f"Error executing command on device {serial}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "device": serial,
                "command": command
            }

# Create singleton instance
interaction_controller = InteractionController()