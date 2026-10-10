# examples/hardware_detection_demo.py
# Demo script showing how to use camera object detection for hydro system hardware monitoring

import requests
import json
from typing import Dict, Any

# Configuration
API_BASE_URL = "http://localhost:8000"
OBJECT_DETECTION_URL = f"{API_BASE_URL}/object-detection"
HARDWARE_DETECTION_URL = f"{API_BASE_URL}/object-detection/hardware-detection"


class HardwareDetectionDemo:
    """Demo class for hardware detection integration"""
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.object_detection_url = f"{base_url}/object-detection"
        self.hardware_detection_url = f"{base_url}/object-detection/hardware-detection"
    
    def setup_location_inventory(self, location: str) -> Dict[str, Any]:
        """Set up expected hardware inventory for a location"""
        print(f"\n=== Setting up inventory for location: {location} ===")
        
        # Auto-sync with hydro devices
        response = requests.post(f"{self.hardware_detection_url}/inventory/sync/{location}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Created {len(result)} inventory items")
            for item in result:
                print(f"  - {item['hardware_type']}: {item['hardware_name']}")
            return result
        else:
            print(f"❌ Failed to setup inventory: {response.text}")
            return {}
    
    def process_image_for_hardware_detection(
        self, 
        image_path: str, 
        location: str,
        camera_source: str = "demo_camera"
    ) -> Dict[str, Any]:
        """Process an image and detect hardware components"""
        print(f"\n=== Processing image for hardware detection ===")
        print(f"Image: {image_path}")
        print(f"Location: {location}")
        
        # Step 1: Upload image for object detection
        with open(image_path, 'rb') as f:
            files = {'file': f}
            params = {
                'model_name': 'default',
                'save_to_db': True
            }
            
            response = requests.post(
                f"{self.object_detection_url}/detect",
                files=files,
                params=params
            )
        
        if response.status_code != 200:
            print(f"❌ Object detection failed: {response.text}")
            return {}
        
        detection_result = response.json()
        detection_result_id = detection_result['id']
        print(f"✅ Object detection completed. Result ID: {detection_result_id}")
        print(f"   Detected {detection_result['detection_count']} objects")
        
        # Step 2: Process detection result for hardware
        params = {
            'location': location,
            'camera_source': camera_source,
            'confidence_threshold': 0.5
        }
        
        response = requests.post(
            f"{self.hardware_detection_url}/process-detection/{detection_result_id}",
            params=params
        )
        
        if response.status_code == 200:
            hardware_detections = response.json()
            print(f"✅ Hardware detection completed. Found {len(hardware_detections)} hardware items:")
            
            for detection in hardware_detections:
                print(f"  - {detection['hardware_type']}: {detection['detected_class']} "
                      f"(confidence: {detection['confidence']:.2f})")
            
            return {
                'detection_result': detection_result,
                'hardware_detections': hardware_detections
            }
        else:
            print(f"❌ Hardware detection failed: {response.text}")
            return {'detection_result': detection_result}
    
    def validate_hardware_detection(self, detection_id: int, is_valid: bool, notes: str = "") -> Dict[str, Any]:
        """Validate a hardware detection"""
        print(f"\n=== Validating hardware detection {detection_id} ===")
        
        validation_data = {
            "is_validated": is_valid,
            "validation_notes": notes,
            "condition_status": "good" if is_valid else "unknown"
        }
        
        response = requests.put(
            f"{self.hardware_detection_url}/{detection_id}/validate",
            json=validation_data
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Validation completed: {'Valid' if is_valid else 'Invalid'}")
            if notes:
                print(f"   Notes: {notes}")
            return result
        else:
            print(f"❌ Validation failed: {response.text}")
            return {}
    
    def get_location_status(self, location: str) -> Dict[str, Any]:
        """Get comprehensive status for a location"""
        print(f"\n=== Location Status Report: {location} ===")
        
        response = requests.get(f"{self.hardware_detection_url}/location/{location}/status")
        
        if response.status_code == 200:
            status = response.json()
            
            print(f"Expected hardware: {status['total_expected']}")
            print(f"Detected hardware: {status['total_detected']}")
            print(f"Validated detections: {status['validated_count']}")
            
            if status['missing_hardware']:
                print(f"⚠️  Missing hardware: {', '.join(status['missing_hardware'])}")
            
            if status['unexpected_hardware']:
                print(f"❓ Unexpected hardware: {', '.join(status['unexpected_hardware'])}")
            
            if status['last_detection']:
                print(f"Last detection: {status['last_detection']}")
            
            return status
        else:
            print(f"❌ Failed to get location status: {response.text}")
            return {}
    
    def get_health_report(self, location: str) -> Dict[str, Any]:
        """Get comprehensive health report for a location"""
        print(f"\n=== Health Report: {location} ===")
        
        response = requests.get(f"{self.hardware_detection_url}/hydro-integration/location/{location}/health")
        
        if response.status_code == 200:
            report = response.json()
            
            # Hydro system info
            hydro = report['hydro_system']
            print(f"Hydro System:")
            print(f"  - Devices: {hydro['device_count']} ({hydro['active_devices']} active)")
            print(f"  - Actuators: {hydro['total_actuators']} ({hydro['active_actuators']} active)")
            
            # Detection system info
            detection = report['detection_system']
            print(f"Detection System:")
            print(f"  - Recent detections: {detection['recent_detections']}")
            print(f"  - Validated: {detection['validated_detections']}")
            print(f"  - Average confidence: {detection['average_confidence']:.2f}")
            print(f"  - Hardware types: {', '.join(detection['hardware_types_detected'])}")
            
            # Overall health
            health = report['overall_health']
            print(f"Overall Health:")
            print(f"  - Score: {health['score']:.2f}")
            print(f"  - Status: {health['status']}")
            print(f"  - Issues: {health['issues']}")
            
            if health['recommendations']:
                print(f"  - Recommendations:")
                for rec in health['recommendations']:
                    print(f"    • {rec}")
            
            return report
        else:
            print(f"❌ Failed to get health report: {response.text}")
            return {}
    
    def run_demo(self, location: str = "Greenhouse A", image_path: str = None):
        """Run a complete demo of the hardware detection system"""
        print("🚀 Starting Hardware Detection Demo")
        print("=" * 50)
        
        # Step 1: Setup location inventory
        self.setup_location_inventory(location)
        
        # Step 2: Process image (if provided)
        if image_path:
            result = self.process_image_for_hardware_detection(image_path, location)
            
            # Step 3: Validate some detections
            if 'hardware_detections' in result:
                for i, detection in enumerate(result['hardware_detections'][:2]):  # Validate first 2
                    self.validate_hardware_detection(
                        detection['id'], 
                        True, 
                        f"Demo validation {i+1}"
                    )
        
        # Step 4: Get location status
        self.get_location_status(location)
        
        # Step 5: Get health report
        self.get_health_report(location)
        
        print("\n✅ Demo completed!")


def main():
    """Main demo function"""
    demo = HardwareDetectionDemo()
    
    # Example usage
    location = "Greenhouse A"
    
    # You can provide an image path here
    # image_path = "path/to/your/hardware/image.jpg"
    image_path = None
    
    demo.run_demo(location, image_path)
    
    # Additional examples
    print("\n" + "=" * 50)
    print("📊 Additional API Examples")
    print("=" * 50)
    
    # Get all hydro locations
    response = requests.get(f"{demo.hardware_detection_url}/hydro-integration/locations")
    if response.status_code == 200:
        locations = response.json()
        print(f"Available hydro locations: {', '.join(locations)}")
    
    # Get camera placement suggestions
    response = requests.get(f"{demo.hardware_detection_url}/hydro-integration/camera-placement-suggestions")
    if response.status_code == 200:
        suggestions = response.json()
        print(f"\n📹 Camera Placement Suggestions:")
        for suggestion in suggestions:
            print(f"  - {suggestion['location']}: {suggestion['recommendation']} "
                  f"(Priority: {suggestion['priority']})")
    
    # Get hardware detection statistics
    response = requests.get(f"{demo.hardware_detection_url}/stats")
    if response.status_code == 200:
        stats = response.json()
        print(f"\n📈 Detection Statistics:")
        print(f"  - Total locations: {stats['total_locations']}")
        print(f"  - Total detections: {stats['total_detections']}")
        print(f"  - Validated detections: {stats['total_validated']}")
        print(f"  - Hardware types: {', '.join(stats['hardware_types_count'].keys())}")


if __name__ == "__main__":
    main()