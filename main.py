#!/usr/bin/env python
# version="1.0"

"""
Video Downloader application entry point
"""

import wx
import os
import logging
from src.app import VideoDownloaderApp

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='video_downloader.log'
)
logger = logging.getLogger('VideoDownloader')

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