"""
Custom events for the application
"""

import wx
from typing import Optional

# Define custom event types
EVT_DOWNLOAD_PROGRESS_ID = wx.NewEventType()
EVT_DOWNLOAD_PROGRESS = wx.PyEventBinder(EVT_DOWNLOAD_PROGRESS_ID, 1)

EVT_DOWNLOAD_COMPLETE_ID = wx.NewEventType()
EVT_DOWNLOAD_COMPLETE = wx.PyEventBinder(EVT_DOWNLOAD_COMPLETE_ID, 1)

EVT_METADATA_FETCHED_ID = wx.NewEventType()
EVT_METADATA_FETCHED = wx.PyEventBinder(EVT_METADATA_FETCHED_ID, 1)

class DownloadProgressEvent(wx.PyCommandEvent):
    """Event to notify about download progress"""
    def __init__(self, index: int, progress: str):
        super(DownloadProgressEvent, self).__init__(EVT_DOWNLOAD_PROGRESS_ID)
        self.index = index
        self.progress = progress

class DownloadCompleteEvent(wx.PyCommandEvent):
    """Event to notify that a download is complete"""
    def __init__(self, index: int, success: bool = True):
        super(DownloadCompleteEvent, self).__init__(EVT_DOWNLOAD_COMPLETE_ID)
        self.index = index
        self.success = success

class MetadataFetchedEvent(wx.PyCommandEvent):
    """Event to notify that metadata has been fetched"""
    def __init__(self, index: int, success: bool = True, title: str = "", 
        duration: str = "", thumbnail_path: Optional[str] = None):
        super(MetadataFetchedEvent, self).__init__(EVT_METADATA_FETCHED_ID)
        self.index = index
        self.success = success
        self.title = title
        self.duration = duration
        self.thumbnail_path = thumbnail_path