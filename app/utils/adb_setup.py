import os
import platform
import subprocess
import sys
import logging
import zipfile
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

def download_platform_tools():
    """Download Android Platform Tools based on the operating system"""
    system = platform.system().lower()
    base_url = "https://dl.google.com/android/repository/"
    
    if system == "windows":
        url = f"{base_url}platform-tools-latest-windows.zip"
        filename = "platform-tools-windows.zip"
    elif system == "darwin":  # macOS
        url = f"{base_url}platform-tools-latest-darwin.zip"
        filename = "platform-tools-mac.zip"
    elif system == "linux":
        url = f"{base_url}platform-tools-latest-linux.zip"
        filename = "platform-tools-linux.zip"
    else:
        logger.error(f"Unsupported operating system: {system}")
        return None
    
    # Create tools directory if it doesn't exist
    tools_dir = Path(__file__).parent.parent.parent / "tools"
    tools_dir.mkdir(exist_ok=True)
    
    # Download the file
    download_path = tools_dir / filename
    logger.info(f"Downloading platform tools from {url} to {download_path}")
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(download_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Extract the zip file
        extract_dir = tools_dir / "platform-tools"
        with zipfile.ZipFile(download_path, 'r') as zip_ref:
            zip_ref.extractall(tools_dir)
        
        # Return the path to the platform-tools directory
        platform_tools_dir = tools_dir / "platform-tools"
        return platform_tools_dir
    
    except Exception as e:
        logger.error(f"Error downloading platform tools: {str(e)}")
        return None

def setup_adb():
    """Setup ADB by downloading platform-tools if needed and starting the server"""
    try:
        # First, try to use system ADB
        try:
            result = subprocess.run(
                ["adb", "version"], 
                capture_output=True, 
                text=True, 
                check=False
            )
            if result.returncode == 0:
                logger.info("System ADB found and working")
                return True
        except FileNotFoundError:
            logger.info("System ADB not found, will download platform-tools")
        
        # Download platform-tools if needed
        platform_tools_dir = download_platform_tools()
        if not platform_tools_dir:
            logger.error("Failed to download platform-tools")
            return False
        
        # Add platform-tools to PATH for this session
        os.environ["PATH"] = f"{platform_tools_dir}{os.pathsep}{os.environ['PATH']}"
        
        # Start ADB server
        system = platform.system().lower()
        adb_path = platform_tools_dir / ("adb.exe" if system == "windows" else "adb")
        
        # Kill any existing ADB server
        subprocess.run(
            [str(adb_path), "kill-server"],
            capture_output=True,
            check=False
        )
        
        # Start ADB server
        result = subprocess.run(
            [str(adb_path), "start-server"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            logger.info("ADB server started successfully")
            return True
        else:
            logger.error(f"Failed to start ADB server: {result.stderr}")
            return False
    
    except Exception as e:
        logger.error(f"Error setting up ADB: {str(e)}")
        return False

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup ADB
    success = setup_adb()
    if success:
        print("ADB setup completed successfully")
    else:
        print("ADB setup failed")
        sys.exit(1)