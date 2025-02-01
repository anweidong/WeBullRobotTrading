import logging
import sys
from logging.handlers import TimedRotatingFileHandler

def get_logger(name):
    """Get a logger instance with both file and stdout handlers.
    
    Args:
        name: Name of the logger (usually __name__ from the calling module)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only add handlers if they haven't been added yet
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # File handler with daily rotation
        file_handler = TimedRotatingFileHandler(
            'log/app.log',
            when='midnight',
            interval=1,
            backupCount=30  # Keep logs for 30 days
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Stream handler for stdout
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger
