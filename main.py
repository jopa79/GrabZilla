#!/usr/bin/env python
# version="1.0"

"""
Video Downloader application entry point
"""

import wx
import os
import logging
from src.app import VideoDownloaderApp
from src.config.settings import APP_ROOT, DISABLE_LOGGING

# Set up logging
logger = logging.getLogger('VideoDownloader')
logger.setLevel(logging.INFO)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Add file handler only if logging is not disabled
if not DISABLE_LOGGING:
    log_file = os.path.join(APP_ROOT, 'video_downloader.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

def main():
    """Main application entry point"""
    try:
        # Create and run the application
        app = VideoDownloaderApp()
        app.MainLoop()
    except Exception as e:
        logger.error(f"Application error: {e}")
        if wx.App.Get() is not None:
            wx.MessageBox(f"An error occurred: {e}", "Error", wx.ICON_ERROR)

if __name__ == '__main__':
    main()