"""
Application initialization and setup
"""

import wx
import os
import logging
from src.ui.main_window import VideoDownloaderFrame

logger = logging.getLogger('VideoDownloader.App')

class VideoDownloaderApp(wx.App):
    """Video Downloader Application Class"""
    
    def OnInit(self):
        """Initialize the application"""
        try:
            # Create the main window
            self.frame = VideoDownloaderFrame(None, "Video Downloader")
            self.frame.Show()
            self.SetTopWindow(self.frame)
            return True
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            wx.MessageBox(f"Failed to initialize application: {e}", "Initialization Error", wx.ICON_ERROR)
            return False