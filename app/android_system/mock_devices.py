# app/android_system/mock_devices.py
# Mock Android devices for testing and development

import logging
import time
import random
from typing import List, Dict, Any
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from app.android_system.config import MOCK_DEVICE_SERIALS, DEFAULT_DEVICE_PROPERTIES

logger = logging.getLogger(__name__)

class MockDevice:
    """Mock Android device for testing"""
    
    def __init__(self, serial: str):
        self.serial = serial
        self.state = "device"
        self.prop = MockDeviceProperties(serial)
        self._screen_size = (1080, 1920)
        self._last_tap = None
        self._last_swipe = None
    
    def shell(self, command: str) -> str:
        """Execute shell command (mocked)"""
        logger.info(f"Mock device {self.serial} executing: {command}")
        
        if command.startswith("input tap"):
            parts = command.split()
            if len(parts) >= 4:
                x, y = int(parts[2]), int(parts[3])
                self._last_tap = (x, y, time.time())
                return f"Tapped at ({x}, {y})"
        
        elif command.startswith("input swipe"):
            parts = command.split()
            if len(parts) >= 6:
                x1, y1, x2, y2 = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
                duration = int(parts[6]) if len(parts) > 6 else 300
                self._last_swipe = (x1, y1, x2, y2, duration, time.time())
                return f"Swiped from ({x1}, {y1}) to ({x2}, {y2})"
        
        return f"Mock command executed: {command}"
    
    def tap(self, x: int, y: int):
        """Direct tap method for mock device"""
        self._last_tap = (x, y, time.time())
        logger.info(f"Mock device {self.serial} tapped at ({x}, {y})")
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        """Direct swipe method for mock device"""
        self._last_swipe = (x1, y1, x2, y2, duration, time.time())
        logger.info(f"Mock device {self.serial} swiped from ({x1}, {y1}) to ({x2}, {y2})")
    
    def screenshot(self) -> Image.Image:
        """Generate mock screenshot"""
        # Create a mock screenshot with device info
        img = Image.new('RGB', self._screen_size, color='lightblue')
        draw = ImageDraw.Draw(img)
        
        # Try to use a default font, fallback to basic if not available
        try:
            font = ImageFont.truetype("arial.ttf", 40)
            small_font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Draw device info
        draw.text((50, 100), f"Mock Device", fill='black', font=font)
        draw.text((50, 150), f"Serial: {self.serial}", fill='black', font=small_font)
        draw.text((50, 180), f"Time: {time.strftime('%H:%M:%S')}", fill='black', font=small_font)
        
        # Draw last interaction info
        if self._last_tap:
            x, y, tap_time = self._last_tap
            draw.text((50, 220), f"Last Tap: ({x}, {y})", fill='red', font=small_font)
            draw.text((50, 250), f"Tap Time: {time.strftime('%H:%M:%S', time.localtime(tap_time))}", fill='red', font=small_font)
            
            # Draw tap indicator
            draw.ellipse([x-20, y-20, x+20, y+20], outline='red', width=3)
        
        if self._last_swipe:
            x1, y1, x2, y2, duration, swipe_time = self._last_swipe
            draw.text((50, 290), f"Last Swipe: ({x1}, {y1}) -> ({x2}, {y2})", fill='blue', font=small_font)
            draw.text((50, 320), f"Swipe Time: {time.strftime('%H:%M:%S', time.localtime(swipe_time))}", fill='blue', font=small_font)
            
            # Draw swipe indicator
            draw.line([x1, y1, x2, y2], fill='blue', width=5)
            draw.ellipse([x1-10, y1-10, x1+10, y1+10], fill='blue')
            draw.ellipse([x2-10, y2-10, x2+10, y2+10], fill='green')
        
        # Add some random elements to make it look more realistic
        for i in range(5):
            x = random.randint(100, self._screen_size[0] - 100)
            y = random.randint(400, self._screen_size[1] - 100)
            color = random.choice(['red', 'green', 'blue', 'yellow', 'purple'])
            draw.rectangle([x, y, x+50, y+30], fill=color)
            draw.text((x+5, y+5), f"App {i+1}", fill='white', font=small_font)
        
        return img

class MockDeviceProperties:
    """Mock device properties"""
    
    def __init__(self, serial: str):
        self.serial = serial
        self._properties = DEFAULT_DEVICE_PROPERTIES.copy()
        
        # Customize properties based on serial
        if "001" in serial:
            self._properties.update({
                "model": "Mock Phone X",
                "device": "mock_phone_x",
                "android_version": "12",
                "manufacturer": "MockCorp",
                "brand": "MockBrand",
                "sdk_version": "31"
            })
        elif "002" in serial:
            self._properties.update({
                "model": "Mock Tablet Pro",
                "device": "mock_tablet_pro", 
                "android_version": "13",
                "manufacturer": "MockTech",
                "brand": "MockTab",
                "sdk_version": "33"
            })
        else:
            self._properties.update({
                "model": f"Mock Device {serial[-3:]}",
                "device": f"mock_device_{serial[-3:]}",
                "android_version": "11",
                "manufacturer": "MockInc",
                "brand": "MockDevice",
                "sdk_version": "30"
            })
    
    @property
    def model(self):
        return self._properties["model"]
    
    @property
    def device(self):
        return self._properties["device"]
    
    def get(self, key: str, default: str = "Unknown"):
        return self._properties.get(key, default)

class MockADBClient:
    """Mock ADB client for testing"""
    
    def __init__(self):
        self._devices = [MockDevice(serial) for serial in MOCK_DEVICE_SERIALS]
        logger.info(f"Mock ADB client initialized with {len(self._devices)} devices")
    
    def device_list(self) -> List[MockDevice]:
        """Return list of mock devices"""
        return self._devices
    
    def device(self, serial: str) -> MockDevice:
        """Get specific mock device by serial"""
        for device in self._devices:
            if device.serial == serial:
                return device
        raise Exception(f"Mock device {serial} not found")

# Create singleton mock ADB client
mock_adb = MockADBClient()