"""
Main window implementation
"""

import wx
import os
import logging
import threading
import subprocess
import shutil
import re
from typing import List, Dict, Optional

from src.config.settings import (
    BANNER_IMG, ICON_IMG, DELETE_ICON, THUMBNAIL_DIR,
    QUALITY_CHOICES, PLAYLIST_CHOICES
)
from src.core.video import VideoInfo, is_valid_link, is_playlist, extract_video_id, download_thumbnail, format_duration
from src.core.downloader import (
    check_ytdlp_exists, get_ytdlp_version, get_latest_ytdlp_version, 
    update_ytdlp, fetch_video_metadata, fetch_playlist_videos,
    build_download_command
)
from src.ui.events import (
    EVT_DOWNLOAD_PROGRESS, DownloadProgressEvent,
    EVT_DOWNLOAD_COMPLETE, DownloadCompleteEvent,
    EVT_METADATA_FETCHED, MetadataFetchedEvent
)

logger = logging.getLogger('VideoDownloader.UI')

class VideoDownloaderFrame(wx.Frame):
    """Main application window"""
    
    def __init__(self, parent, title):
        super(VideoDownloaderFrame, self).__init__(parent, title=title, size=(720, 600))

        self.videos: List[VideoInfo] = []
        self.downloading: bool = False
        self.download_threads: List[threading.Thread] = []

        if os.name == 'nt':  # Windows
            self.default_folder = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        else:  # macOS/Linux
            self.default_folder = os.path.join(os.environ['HOME'], 'Desktop')
                
        self.save_path = os.path.join(self.default_folder, 'VideoDownloader')
        os.makedirs(self.save_path, exist_ok=True)

        # Create status bar
        self.CreateStatusBar()
        self.SetStatusText("Ready")

        # Set up the UI
        self._init_ui()
        
        # Set application icon
        try:
            if os.path.exists(ICON_IMG):
                self.SetIcon(wx.Icon(ICON_IMG))
        except Exception as e:
            logger.error(f"Error loading application icon: {e}")

        # Bind the close event
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        # Bind custom events
        self.Bind(EVT_DOWNLOAD_PROGRESS, self.on_download_progress)
        self.Bind(EVT_DOWNLOAD_COMPLETE, self.on_download_complete)
        self.Bind(EVT_METADATA_FETCHED, self.on_metadata_fetched)
        
        # Check for yt-dlp and its updates
        self.check_ytdlp()
        
        # Schedule periodic update checks (every 24 hours)
        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda evt: self.check_ytdlp(), self.update_timer)
        self.update_timer.Start(1000 * 60 * 60 * 24)  # 24 hours in milliseconds

    def _init_ui(self):
        """Initialize the user interface"""
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Add header banner
        try:
            if os.path.exists(BANNER_IMG):
                banner = wx.Image(BANNER_IMG, wx.BITMAP_TYPE_PNG).ConvertToBitmap()
                banner_bitmap = wx.StaticBitmap(panel, -1, banner)
                vbox.Add(banner_bitmap, 0, wx.EXPAND | wx.ALL, 10)
            else:
                # Create placeholder if banner cannot be loaded
                banner_text = wx.StaticText(panel, -1, "Video Downloader")
                font = wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.BOLD)
                banner_text.SetFont(font)
                vbox.Add(banner_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        except Exception as e:
            logger.error(f"Error loading banner: {e}")
            # Create placeholder if banner cannot be loaded
            banner_text = wx.StaticText(panel, -1, "Video Downloader")
            font = wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.BOLD)
            banner_text.SetFont(font)
            vbox.Add(banner_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Input field for video link and add button
        hbox_link = wx.BoxSizer(wx.HORIZONTAL)
        self.link_entry = wx.TextCtrl(panel, style=wx.TE_MULTILINE)
        hbox_link.Add(self.link_entry, 1, wx.EXPAND | wx.RIGHT, 10)

        # Add buttons panel
        input_buttons_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.add_button = wx.Button(panel, label='Add Video')
        self.add_button.Bind(wx.EVT_BUTTON, self.on_add_video)
        input_buttons_sizer.Add(self.add_button, 0, wx.EXPAND | wx.BOTTOM, 5)
        
        self.add_file_button = wx.Button(panel, label='Import URLs')
        self.add_file_button.Bind(wx.EVT_BUTTON, self.on_import_urls)
        input_buttons_sizer.Add(self.add_file_button, 0, wx.EXPAND)
        
        hbox_link.Add(input_buttons_sizer, 0, wx.EXPAND)
        vbox.Add(hbox_link, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Save path button and text field
        hbox_save = wx.BoxSizer(wx.HORIZONTAL)
        self.save_path_button = wx.Button(panel, label='Set Save Path...')
        self.save_path_button.Bind(wx.EVT_BUTTON, self.on_set_save_path)
        hbox_save.Add(self.save_path_button, 0, wx.EXPAND | wx.RIGHT, 10)

        self.save_path_text = wx.TextCtrl(panel, value=self.save_path, style=wx.TE_READONLY)
        hbox_save.Add(self.save_path_text, 1, wx.EXPAND)
        vbox.Add(hbox_save, 0, wx.EXPAND | wx.ALL, 10)
        
        # Options panel
        options_box = wx.StaticBox(panel, label="Download Options")
        options_sizer = wx.StaticBoxSizer(options_box, wx.HORIZONTAL)
        
        # Audio-only option
        self.audio_only = wx.CheckBox(options_box, label='Audio Only (MP3)')
        options_sizer.Add(self.audio_only, 0, wx.ALL, 5)
        
        # Add a quality dropdown
        quality_label = wx.StaticText(options_box, label="Video Quality:")
        options_sizer.Add(quality_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        self.quality_dropdown = wx.Choice(options_box, choices=QUALITY_CHOICES)
        self.quality_dropdown.SetSelection(0)  # Default to Best
        options_sizer.Add(self.quality_dropdown, 0, wx.ALL, 5)
        
        # Add playlist options
        playlist_label = wx.StaticText(options_box, label="Playlist:")
        options_sizer.Add(playlist_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        self.playlist_dropdown = wx.Choice(options_box, choices=PLAYLIST_CHOICES)
        self.playlist_dropdown.SetSelection(0)  # Default to Download All
        options_sizer.Add(self.playlist_dropdown, 0, wx.ALL, 5)
        
        vbox.Add(options_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Create image list for thumbnails with sufficient error handling
        try:
            self.image_list = wx.ImageList(90, 50)
            
            # Create a simple default thumbnail
            default_bitmap = wx.Bitmap(90, 50)
            self.default_thumbnail_idx = self.image_list.Add(default_bitmap)
            
            # Create a simple delete icon
            if os.path.exists(DELETE_ICON):
                self.delete_icon = wx.Bitmap(DELETE_ICON)
                logger.info(f"Loading delete icon from {DELETE_ICON}")
            else:
                delete_bitmap = wx.Bitmap(16, 16)
                self.delete_icon = delete_bitmap
            self.delete_icon_idx = self.image_list.Add(self.delete_icon)
        except Exception as e:
            logger.error(f"Error initializing image list: {e}")
            # Try to continue without images
            wx.MessageBox(f"Could not initialize images. The application will continue but some icons may be missing.\nError: {e}", 
                         "Warning", wx.ICON_WARNING)
            
        # Video list view
        self.list_view = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        
        # Set the image list if it was created successfully
        if hasattr(self, 'image_list'):
            self.list_view.SetImageList(self.image_list, wx.IMAGE_LIST_SMALL)
            
        self.list_view.InsertColumn(0, 'Thumbnail', width=100)
        self.list_view.InsertColumn(1, 'Title', width=250)
        self.list_view.InsertColumn(2, 'Duration', width=70)
        self.list_view.InsertColumn(3, 'Status', width=130)
        # self.list_view.InsertColumn(4, '', width=30)  # Delete icon
        vbox.Add(self.list_view, 1, wx.EXPAND | wx.ALL, 10)
        
        # Bind list item events
        self.list_view.Bind(wx.EVT_LEFT_DOWN, self.on_list_click)
        self.list_view.Bind(wx.EVT_RIGHT_DOWN, self.on_right_click)

        # Download and clear list buttons
        hbox_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.clear_button = wx.Button(panel, label='Clear List')
        self.clear_button.Bind(wx.EVT_BUTTON, self.on_clear_list)
        hbox_buttons.Add(self.clear_button, 0, wx.EXPAND | wx.RIGHT, 10)

        # Update YT-DLP button
        self.update_button = wx.Button(panel, label='Update yt-dlp')
        self.update_button.Bind(wx.EVT_BUTTON, self.on_update_ytdlp)
        hbox_buttons.Add(self.update_button, 0, wx.EXPAND)

        hbox_buttons.AddStretchSpacer(1)

        self.download_button = wx.Button(panel, label='Download Videos', size=(200, 50))
        self.download_button.Bind(wx.EVT_BUTTON, self.on_download_videos)
        font = wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        self.download_button.SetFont(font)
        hbox_buttons.Add(self.download_button, 0, wx.EXPAND)
        vbox.Add(hbox_buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(vbox)
        self.Centre()
        self.Show()

    # ------------- Event Handlers -------------

    def on_add_video(self, event):
        """Add a video URL to the download queue"""
        links = self.link_entry.GetValue().split('\n')
        added_count = 0
        
        for link in links:
            link = link.strip()
            if link and not self._is_url_in_queue(link):
                if is_valid_link(link):
                    # Process possible playlist
                    if is_playlist(link) and self.playlist_dropdown.GetSelection() == 0:
                        threading.Thread(target=self._process_playlist, args=(link,), daemon=True).start()
                        added_count += 1
                    else:
                        # Add single video
                        video_info = VideoInfo(url=link)
                        self._add_video_to_list(video_info)
                        added_count += 1
                else:
                    wx.MessageBox(f"Invalid video link: {link}", "Error", wx.ICON_ERROR)
        
        if added_count > 0:
            self.SetStatusText(f"Added {added_count} video(s) to queue")
        
        self.link_entry.SetValue("")

    def on_import_urls(self, event):
        """Import URLs from a text file"""
        with wx.FileDialog(self, "Open URL file", wildcard="Text files (*.txt)|*.txt",
                        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
                
            pathname = fileDialog.GetPath()
            try:
                with open(pathname, 'r') as file:
                    urls = file.readlines()
                
                valid_urls = []
                for url in urls:
                    url = url.strip()
                    if url and is_valid_link(url) and not self._is_url_in_queue(url):
                        valid_urls.append(url)
                
                if valid_urls:
                    for url in valid_urls:
                        video_info = VideoInfo(url=url)
                        self._add_video_to_list(video_info)
                    
                    self.SetStatusText(f"Imported {len(valid_urls)} valid URLs from file")
                else:
                    wx.MessageBox("No valid URLs found in the file", "Import URLs", wx.ICON_INFORMATION)
                    
            except Exception as e:
                logger.error(f"Error importing URLs: {e}")
                wx.MessageBox(f"Error opening file: {e}", "Error", wx.ICON_ERROR)

    def on_set_save_path(self, event):
        """Set the download save path using directory dialog"""
        save_path_dialog = wx.DirDialog(self, "Select Save Path", self.save_path, wx.DD_DEFAULT_STYLE)
        if save_path_dialog.ShowModal() == wx.ID_OK:
            self.save_path = save_path_dialog.GetPath()
            self.save_path_text.SetValue(self.save_path)
            self.SetStatusText(f"Save path set to {self.save_path}")
        save_path_dialog.Destroy()

    def on_clear_list(self, event):
        """Clear the download queue"""
        if self.downloading:
            wx.MessageBox("Cannot clear list while downloads are in progress", "Warning", wx.ICON_WARNING)
            return
            
        if self.list_view.GetItemCount() > 0:
            dialog = wx.MessageDialog(self, "Are you sure you want to clear the download queue?", 
                                    "Confirm Clear", wx.YES_NO | wx.ICON_QUESTION)
            if dialog.ShowModal() == wx.ID_YES:
                self.videos.clear()
                self.list_view.DeleteAllItems()
                # Reset the image list except for icons
                if hasattr(self, 'image_list'):
                    self.image_list.RemoveAll()
                    # Re-add default images
                    default_bitmap = wx.Bitmap(90, 50)
                    self.default_thumbnail_idx = self.image_list.Add(default_bitmap)
                    self.delete_icon_idx = self.image_list.Add(self.delete_icon)
                self.SetStatusText("Download queue cleared")
            dialog.Destroy()

    def on_list_click(self, event):
        """Handle clicks on the list items, particularly for action icons"""
        # Get mouse position
        point = event.GetPosition()
        item, flags = self.list_view.HitTest(point)
        
        if item != -1:  # If an item was clicked
            # Get the column width to determine which column was clicked
            col_widths = [self.list_view.GetColumnWidth(i) for i in range(self.list_view.GetColumnCount())]
            total_width = sum(col_widths[:4])  # Width up to Status column
            
            x_pos = point.x
            
            # Check if delete column was clicked
            if total_width <= x_pos < total_width + col_widths[4]:
                # Delete icon clicked
                self._remove_selected_item(item)
        
        event.Skip()  # Allow default processing

    def on_right_click(self, event):
        """Handle right-click for context menu"""
        point = event.GetPosition()
        item, flags = self.list_view.HitTest(point)
        
        if item != -1:  # If an item was right-clicked
            # Create popup menu
            menu = wx.Menu()
            
            # Add menu items
            remove_item = menu.Append(-1, "Remove from Queue")
            
            # Bind events
            self.Bind(wx.EVT_MENU, lambda evt: self._remove_selected_item(item), remove_item)
            
            # Show popup menu
            self.PopupMenu(menu, event.GetPosition())
            menu.Destroy()
        
        event.Skip()

    def on_update_ytdlp(self, event):
        """Download or update yt-dlp executable"""
        try:
            self.SetStatusText("Updating yt-dlp...")
            wx.MessageBox("Updating yt-dlp. Please wait...", "Update", wx.ICON_INFORMATION)
            
            if update_ytdlp():
                wx.MessageBox("yt-dlp has been updated successfully!", "Update", wx.ICON_INFORMATION)
                self.SetStatusText("yt-dlp updated successfully")
                # Check version after update
                self.check_ytdlp()
            else:
                wx.MessageBox("Failed to update yt-dlp. See log for details.", "Update Error", wx.ICON_ERROR)
                self.SetStatusText("Update failed")
        except Exception as e:
            logger.error(f"Failed to update yt-dlp: {e}")
            wx.MessageBox(f"Failed to update yt-dlp. Error: {e}", "Update Error", wx.ICON_ERROR)
            self.SetStatusText(f"Update failed: {str(e)}")

    def on_download_videos(self, event):
        """Start downloading all videos in the queue"""
        if self.downloading:
            wx.MessageBox("Downloads are already in progress", "Information", wx.ICON_INFORMATION)
            return
            
        if len(self.videos) == 0:
            wx.MessageBox("No videos in queue to download", "Information", wx.ICON_INFORMATION)
            return
            
        # Create the VideoDownloader folder if it doesn't exist
        if not os.path.exists(self.save_path):
            try:
                os.makedirs(self.save_path)
            except Exception as e:
                logger.error(f"Failed to create download directory: {e}")
                wx.MessageBox(f"Failed to create download directory: {e}", "Error", wx.ICON_ERROR)
                return

        self.downloading = True
        self.download_button.Disable()
        self.clear_button.Disable()
        self.download_threads = []
        
        for index, video_info in enumerate(self.videos):
            thread = threading.Thread(target=self._download_video, args=(index, video_info.url), daemon=True)
            thread.start()
            self.download_threads.append(thread)
            
        # Start a thread to monitor download completion
        threading.Thread(target=self._monitor_downloads, daemon=True).start()

    def on_download_progress(self, event):
        """Handle download progress event"""
        self.list_view.SetItem(event.index, 3, f"Downloading {event.progress}")
    
    def on_download_complete(self, event):
        """Handle download complete event"""
        if event.success:
            self.list_view.SetItem(event.index, 3, "Downloaded")
            self._set_row_color(event.index, wx.Colour(200, 255, 200))  # Light green
        else:
            self.list_view.SetItem(event.index, 3, "Failed")
            self._set_row_color(event.index, wx.Colour(255, 200, 200))  # Light red
            
    def on_metadata_fetched(self, event):
        """Handle metadata fetched event"""
        index = event.index
        if event.success:
            self.list_view.SetItem(index, 1, event.title)
            self.list_view.SetItem(index, 2, event.duration)
            self.list_view.SetItem(index, 3, "Ready")
            # Update thumbnail if available
            if event.thumbnail_path and os.path.exists(event.thumbnail_path):
                self._update_thumbnail(index, event.thumbnail_path)
        else:
            self.list_view.SetItem(index, 1, "Error: Metadata fetch failed")
            self.list_view.SetItem(index, 3, "Error")
            self._set_row_color(index, wx.Colour(255, 200, 200))  # Light red
            
    def on_close(self, event):
        """Handle closing the application safely"""
        if self.downloading:
            dialog = wx.MessageDialog(self, "Downloads are in progress. Are you sure you want to exit?", 
                                    "Confirm Exit", wx.YES_NO | wx.ICON_QUESTION)
            if dialog.ShowModal() != wx.ID_YES:
                return
        
        # Stop the update timer
        if hasattr(self, 'update_timer'):
            self.update_timer.Stop()
            
        # Clean up temp files
        if os.path.exists(THUMBNAIL_DIR):
            try:
                shutil.rmtree(THUMBNAIL_DIR)
            except Exception as e:
                logger.error(f"Error cleaning up thumbnails: {e}")
                
        event.Skip()

    # ------------- Helper Methods -------------

    def _is_url_in_queue(self, url: str) -> bool:
        """Check if URL is already in the queue"""
        return any(video.url == url for video in self.videos)

    def _add_video_to_list(self, video_info: VideoInfo):
        """Add a video to the list view and start metadata fetching"""
        self.videos.append(video_info)
        index = self.list_view.InsertItem(self.list_view.GetItemCount(), "", self.default_thumbnail_idx)
        self.list_view.SetItem(index, 1, "Fetching metadata...")
        
        # Only set the delete icon if we have a valid index and the image_list was created successfully
        if index != -1 and hasattr(self, 'image_list') and hasattr(self, 'delete_icon_idx'):
            self.list_view.SetItem(index, 4, "", imageId=self.delete_icon_idx)
        
        threading.Thread(target=self._fetch_metadata, args=(index, video_info.url), daemon=True).start()

    def _process_playlist(self, playlist_url: str):
        """Process a playlist URL and add all videos"""
        wx.CallAfter(self.SetStatusText, "Fetching playlist videos...")
        
        videos, error = fetch_playlist_videos(playlist_url)
        
        if error:
            logger.error(f"Failed to process playlist: {error}")
            wx.CallAfter(wx.MessageBox, f"Failed to process playlist. Error: {error}", "Error", wx.ICON_ERROR)
            return
            
        if videos:
            wx.CallAfter(self.SetStatusText, f"Found {len(videos)} videos in playlist")
            
            # Add each video to the queue
            for video in videos:
                video_url = f"https://www.youtube.com/watch?v={video.get('id')}"
                if not self._is_url_in_queue(video_url):
                    video_info = VideoInfo(url=video_url)
                    wx.CallAfter(self._add_video_to_list, video_info)
        else:
            wx.CallAfter(self.SetStatusText, "No videos found in playlist")
            wx.CallAfter(wx.MessageBox, "No videos found in playlist", "Information", wx.ICON_INFORMATION)

    def _remove_selected_item(self, index):
        """Remove item at the specified index"""
        if index != -1:
            # Remove from video_list
            self.videos.pop(index)
            # Remove from list_view
            self.list_view.DeleteItem(index)
            self.SetStatusText(f"Removed item at position {index+1}")


    def _update_thumbnail(self, index: int, thumbnail_path: str):
        """Update the thumbnail image in the list view"""
        try:
            # Load the thumbnail image
            img = wx.Image(thumbnail_path, wx.BITMAP_TYPE_ANY)
            # Convert to bitmap and add to image list
            bitmap = img.ConvertToBitmap()
            img_idx = self.image_list.Add(bitmap)
            # Update the list item with the new image
            self.list_view.SetItemImage(index, img_idx)
            
            # Make sure delete icon is preserved - only if we have a valid index and delete_icon_idx exists
            if index != -1 and hasattr(self, 'delete_icon_idx'):
                self.list_view.SetItem(index, 4, "", imageId=self.delete_icon_idx)
        except Exception as e:
            logger.error(f"Error updating thumbnail: {e}")

    def _set_row_color(self, index: int, color: wx.Colour):
        """Set the background color for a row in the list view"""
        for col in range(self.list_view.GetColumnCount()):
            self.list_view.SetItemBackgroundColour(index, color)

    def check_ytdlp(self):
        """Check if yt-dlp exists and check for updates"""
        # Start a thread to check version to avoid freezing the UI
        threading.Thread(target=self._check_ytdlp_version, daemon=True).start()

    def _check_ytdlp_version(self):
        """Check if an update is available for yt-dlp"""
        if not check_ytdlp_exists():
            logger.warning("yt-dlp not found")
            wx.CallAfter(self.update_button.Enable)
            wx.CallAfter(self.SetStatusText, "yt-dlp not found. Click 'Update yt-dlp' to download it.")
            return
            
        current_version = get_ytdlp_version()
        if not current_version:
            logger.warning("Could not determine yt-dlp version")
            wx.CallAfter(self.update_button.Enable)
            wx.CallAfter(self.SetStatusText, "Cannot determine yt-dlp version. Update recommended.")
            return
            
        latest_version = get_latest_ytdlp_version()
        if not latest_version:
            logger.warning("Could not check for yt-dlp updates")
            wx.CallAfter(self.update_button.Enable)
            wx.CallAfter(self.SetStatusText, "Could not check for updates. Update button enabled as precaution.")
            return
            
        if latest_version.strip() != current_version.strip():
            logger.info(f"yt-dlp update available: {current_version} → {latest_version}")
            wx.CallAfter(self.update_button.Enable)
            wx.CallAfter(self.SetStatusText, f"yt-dlp update available: {current_version} → {latest_version}")
        else:
            logger.info(f"yt-dlp is up to date (version {current_version})")
            wx.CallAfter(self.update_button.Disable)
            wx.CallAfter(self.SetStatusText, f"yt-dlp is up to date (version {current_version})")

    def _fetch_metadata(self, index: int, link: str):
        """Fetch video metadata using yt-dlp"""
        try:
            wx.CallAfter(self.SetStatusText, f"Fetching metadata for video {index+1}...")
            info_dict, error = fetch_video_metadata(link)
            
            if error:
                logger.error(f"Failed to get metadata: {error}")
                event = MetadataFetchedEvent(index=index, success=False)
                wx.PostEvent(self, event)
                return
                
            title = info_dict.get('title', 'Unknown')
            duration = info_dict.get('duration', 0)
            duration_str = format_duration(duration)
            
            # Get thumbnail URL
            thumbnail_url = info_dict.get('thumbnail')
            video_id = info_dict.get('id', extract_video_id(link))
            
            # Update video info
            self.videos[index].title = title
            self.videos[index].duration = duration
            self.videos[index].thumbnail_url = thumbnail_url
            
            thumbnail_path = None
            if thumbnail_url:
                # Download and process thumbnail
                thumbnail_path = download_thumbnail(thumbnail_url, video_id)
                if thumbnail_path:
                    self.videos[index].thumbnail_path = thumbnail_path
            
            # Post event to update UI
            event = MetadataFetchedEvent(
                index=index, 
                success=True,
                title=title,
                duration=duration_str,
                thumbnail_path=thumbnail_path
            )
            wx.PostEvent(self, event)
                
            wx.CallAfter(self.SetStatusText, f"Metadata fetched for {title}")
        except Exception as e:
            logger.error(f"Error fetching metadata: {e}")
            event = MetadataFetchedEvent(index=index, success=False)
            wx.PostEvent(self, event)

    def _download_video(self, index: int, video_link: str):
        """Download a single video"""
        try:
            wx.CallAfter(self.list_view.SetItem, index, 3, "Preparing...")
            wx.CallAfter(self.SetStatusText, f"Downloading video {index+1}...")
            
            # Get video title from our data if available
            video_info = self.videos[index]
            if video_info.title:
                video_title = video_info.title
            else:
                # Fallback: Get video info to extract the title
                info_dict, error = fetch_video_metadata(video_link)
                if error:
                    logger.error(f"Failed to get title: {error}")
                    wx.PostEvent(self, DownloadCompleteEvent(index=index, success=False))
                    return
                    
                video_title = info_dict.get('title', 'Unknown')
            
            # Replace invalid filename characters
            video_title = re.sub(r'[\\/*?:"<>|]', '_', video_title)
            
            # Determine file extension based on download mode
            extension = ".mp3" if self.audio_only.GetValue() else ".mp4"
            output_path = os.path.join(self.save_path, f"{video_title}{extension}")
            
                # Check if file already exists
            if os.path.exists(output_path):
                wx.CallAfter(self.list_view.SetItem, index, 3, "Already Downloaded")
                wx.CallAfter(self._set_row_color, index, wx.Colour(200, 255, 200))  # Light green
                return
                
            # Build command based on options
            quality = QUALITY_CHOICES[self.quality_dropdown.GetSelection()]
            command = build_download_command(
                video_link, 
                output_path, 
                audio_only=self.audio_only.GetValue(),
                quality=quality
            )
            
            # Start download process with improved progress monitoring
            process = subprocess.Popen(
                command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            
            # Monitor stdout for progress updates
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                    
                line = line.strip()
                if re.match(r'^\d{1,3}\.\d%', line):
                    wx.PostEvent(self, DownloadProgressEvent(index=index, progress=line))
                elif "download" in line.lower() and "%" in line:
                    # Try to extract percentage from other progress formats
                    match = re.search(r'(\d{1,3}\.\d)%', line)
                    if match:
                        wx.PostEvent(self, DownloadProgressEvent(index=index, progress=f"{match.group(1)}%"))
            
            # Wait for process to complete
            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0:
                # Post success event
                wx.PostEvent(self, DownloadCompleteEvent(index=index, success=True))
                wx.CallAfter(self.SetStatusText, f"Successfully downloaded: {video_title}")
            else:
                error_output = process.stderr.read() if process.stderr else "Unknown error"
                logger.error(f"Download failed: {error_output}")
                # Post failure event
                wx.PostEvent(self, DownloadCompleteEvent(index=index, success=False))
                wx.CallAfter(self.SetStatusText, f"Download failed: {video_title}")
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            # Post failure event
            wx.PostEvent(self, DownloadCompleteEvent(index=index, success=False))
            wx.CallAfter(self.SetStatusText, f"Error: {str(e)}")

    def _monitor_downloads(self):
        """Monitor download threads and re-enable buttons when all complete"""
        for thread in self.download_threads:
            thread.join()
            
        wx.CallAfter(self._on_downloads_complete)

    def _on_downloads_complete(self):
        """Handle completion of all downloads"""
        self.downloading = False
        self.download_button.Enable()
        self.clear_button.Enable()
        self.SetStatusText("All downloads complete")
        
        # Count successful and failed downloads
        success_count = 0
        failed_count = 0
        for index in range(self.list_view.GetItemCount()):
            status = self.list_view.GetItemText(index, 3)
            if status == "Downloaded":
                success_count += 1
            elif status == "Failed" or status == "Error":
                failed_count += 1
        
        message = f"Downloads complete: {success_count} successful"
        if failed_count > 0:
            message += f", {failed_count} failed"
        
        wx.MessageBox(message, "Downloads Complete", wx.ICON_INFORMATION)