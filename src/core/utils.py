"""
Utility functions
"""

import os
import re
import logging
import subprocess
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger('VideoDownloader.Utils')

def clean_filename(filename: str) -> str:
    """Remove invalid characters from a filename"""
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

def ensure_directory_exists(directory: str) -> bool:
    """Create a directory if it doesn't exist"""
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {directory}: {e}")
        return False

def get_file_size(file_path: str) -> Optional[int]:
    """Get file size in bytes"""
    try:
        return os.path.getsize(file_path)
    except Exception as e:
        logger.error(f"Failed to get file size for {file_path}: {e}")
        return None

def format_file_size(size_bytes: int) -> str:
    """Format file size in bytes to a human-readable string"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def run_command(command: str) -> Tuple[int, str, str]:
    """Run a shell command and return return code, stdout, and stderr"""
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        stdout, stderr = process.communicate()
        return process.returncode, stdout, stderr
    except Exception as e:
        logger.error(f"Failed to run command: {e}")
        return -1, "", str(e)

def is_internet_connected() -> bool:
    """Check if there's an internet connection"""
    try:
        # Try to connect to a reliable host
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        return False