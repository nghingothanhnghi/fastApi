# app/android_system/adb_client.py
# Core ADB client management and device communication

import adbutils
import logging
import subprocess
from typing import List, Tuple, Optional, Dict, Any
from app.android_system.config import ADB_HOST, ADB_PORT, USE_MOCK_DEVICES, DEVICE_CONFIG
from app.android_system.mock_devices import MockADBClient

logger = logging.getLogger(__name__)

class ADBClientManager:
    """Manages ADB client connection and device operations"""
    
    def __init__(self):
        self.client = None
        self.is_mock = USE_MOCK_DEVICES
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize ADB client (real or mock)"""
        if self.is_mock:
            logger.info("Initializing mock ADB client")
            self.client = MockADBClient()
            return
        
        try:
            # Setup real ADB client
            self._setup_adb_server()
            self.client = adbutils.AdbClient(host=ADB_HOST, port=ADB_PORT)
            
            # Test connection
            devices = self.client.device_list()
            logger.info(f"ADB client initialized successfully. Found {len(devices)} devices")
            
            # Log device information
            for device in devices:
                try:
                    device_info = self._get_device_properties(device)
                    logger.info(f"Device found: {device_info}")
                except Exception as e:
                    logger.error(f"Error getting device info for {device.serial}: {str(e)}")
            
            # Fallback to mock if no real devices found
            if not devices and USE_MOCK_DEVICES:
                logger.info("No real devices found, falling back to mock devices")
                self.client = MockADBClient()
                self.is_mock = True
                
        except Exception as e:
            logger.error(f"Failed to initialize ADB client: {str(e)}")
            if USE_MOCK_DEVICES:
                logger.info("Falling back to mock ADB client")
                self.client = MockADBClient()
                self.is_mock = True
            else:
                self.client = None
    
    def _setup_adb_server(self):
        """Setup and start ADB server if needed"""
        try:
            subprocess.run(
                ["adb", "start-server"],
                capture_output=True,
                check=False,
                timeout=DEVICE_CONFIG["discovery_timeout"]
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Could not start ADB server: {str(e)}")
    
    def get_devices(self) -> List[Any]:
        """Get list of connected devices"""
        if not self.client:
            return []
        
        try:
            return self.client.device_list()
        except Exception as e:
            logger.error(f"Error getting device list: {str(e)}")
            return []
    
    def get_device(self, serial: str) -> Optional[Any]:
        """Get specific device by serial"""
        if not self.client:
            return None
        
        try:
            return self.client.device(serial)
        except Exception as e:
            logger.error(f"Error getting device {serial}: {str(e)}")
            return None
    
    def check_connection(self) -> Tuple[bool, str, List[str]]:
        """Check ADB connection status"""
        if not self.client:
            return False, "ADB client not initialized", []
        
        try:
            devices = self.get_devices()
            device_serials = [d.serial for d in devices]
            
            if not devices:
                return True, "No devices connected", []
            
            return True, f"Found {len(devices)} devices", device_serials
        except Exception as e:
            logger.error(f"Error checking ADB connection: {str(e)}")
            return False, str(e), []
    
    def _get_device_properties(self, device) -> Dict[str, Any]:
        """Get detailed device properties"""
        try:
            return {
                "serial": device.serial,
                "state": device.state,
                "properties": {
                    "model": getattr(device.prop, 'model', 'Unknown'),
                    "device": getattr(device.prop, 'device', 'Unknown'),
                    "android_version": device.prop.get("ro.build.version.release", "Unknown"),
                    "manufacturer": device.prop.get("ro.product.manufacturer", "Unknown"),
                    "brand": device.prop.get("ro.product.brand", "Unknown"),
                    "sdk_version": device.prop.get("ro.build.version.sdk", "Unknown")
                }
            }
        except Exception as e:
            logger.error(f"Error getting device properties: {str(e)}")
            return {
                "serial": device.serial,
                "state": "unknown",
                "properties": {
                    "error": str(e)
                }
            }
    
    def get_device_info(self, device) -> Dict[str, Any]:
        """Get device information with error handling"""
        return self._get_device_properties(device)
    
    def restart_server(self) -> Dict[str, Any]:
        """Restart ADB server"""
        if self.is_mock:
            success, message, device_list = self.check_connection()
            return {
                "success": True,
                "using_mock": True,
                "kill_server_output": "Mock ADB server killed",
                "start_server_output": "Mock ADB server started",
                "adb_client_connected": success,
                "adb_client_message": message,
                "devices": device_list
            }
        
        try:
            # Kill ADB server
            kill_result = subprocess.run(
                ["adb", "kill-server"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10
            )
            
            # Start ADB server
            start_result = subprocess.run(
                ["adb", "start-server"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10
            )
            
            # Reinitialize client
            self._initialize_client()
            
            # Check connection
            success, message, device_list = self.check_connection()
            
            return {
                "success": True,
                "using_mock": False,
                "kill_server_output": kill_result.stdout.strip() if kill_result.returncode == 0 else kill_result.stderr.strip(),
                "start_server_output": start_result.stdout.strip() if start_result.returncode == 0 else start_result.stderr.strip(),
                "adb_client_connected": success,
                "adb_client_message": message,
                "devices": device_list
            }
        except Exception as e:
            logger.error(f"Error restarting ADB server: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_server_status(self) -> Dict[str, Any]:
        """Get detailed ADB server status"""
        if self.is_mock:
            success, message, device_list = self.check_connection()
            return {
                "using_mock": True,
                "adb_installed": True,
                "adb_version": "Mock ADB 1.0.0",
                "adb_server_running": True,
                "adb_server_output": "Mock ADB server running",
                "adb_client_connected": success,
                "adb_client_message": message,
                "devices": device_list
            }
        
        # Check if ADB is installed
        try:
            adb_version_result = subprocess.run(
                ["adb", "version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
            adb_installed = adb_version_result.returncode == 0
            adb_version = adb_version_result.stdout.strip() if adb_installed else "Not installed"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            adb_installed = False
            adb_version = "Not installed or not in PATH"
        
        # Check ADB server status
        try:
            adb_server_result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
            adb_server_running = adb_server_result.returncode == 0
            adb_server_output = adb_server_result.stdout.strip() if adb_server_running else "Not running"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            adb_server_running = False
            adb_server_output = "Not running or not accessible"
        
        # Check ADB connection
        success, message, device_list = self.check_connection()
        
        return {
            "using_mock": False,
            "adb_installed": adb_installed,
            "adb_version": adb_version,
            "adb_server_running": adb_server_running,
            "adb_server_output": adb_server_output,
            "adb_client_connected": success,
            "adb_client_message": message,
            "devices": device_list
        }

# Create singleton instance
adb_manager = ADBClientManager()