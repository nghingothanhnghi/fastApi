# File: backend/app/core/logging_config.py
## This module configures logging for the application.
# It sets up a basic logging configuration and provides a function to get a logger instance.
import logging

def configure_logging():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    return logger

def get_logger(name):
    """
    Get a logger with the specified name.
    
    Args:
        name: The name for the logger
        
    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)
