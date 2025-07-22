import os
import sys
import subprocess
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Start the backend server with mock devices enabled"""
    try:
        # Set environment variables
        os.environ["USE_MOCK_DEVICES"] = "true"
        
        # Check if virtual environment exists
        venv_python = os.path.join(".venv", "Scripts", "python") if sys.platform == "win32" else os.path.join(".venv", "bin", "python")
        
        if not os.path.exists(venv_python):
            logger.info("Virtual environment not found, creating one...")
            
            # Create virtual environment
            subprocess.run(
                [sys.executable, "-m", "venv", ".venv"],
                check=True
            )
            
            # Install dependencies
            pip_cmd = [venv_python, "-m", "pip", "install", "-r", "requirements.txt"]
            logger.info(f"Installing dependencies: {' '.join(pip_cmd)}")
            subprocess.run(pip_cmd, check=True)
        
        # Start the server
        logger.info("Starting backend server with mock devices...")
        
        # Use uvicorn to start the server
        uvicorn_cmd = [venv_python, "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
        logger.info(f"Running command: {' '.join(uvicorn_cmd)}")
        
        # Start the server
        server_process = subprocess.Popen(
            uvicorn_cmd,
            env=os.environ.copy()
        )
        
        logger.info("Server started! Press Ctrl+C to stop.")
        
        # Wait for the server to exit
        server_process.wait()
        
    except KeyboardInterrupt:
        logger.info("Stopping server...")
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())