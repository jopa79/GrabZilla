# version="1.1"

import wx
import wx.adv
import os
import subprocess
import threading
import json
import re
import urllib.request
import uuid
import time
import shutil
import ssl
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from PIL import Image
from io import BytesIO

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='video_downloader.log'
)
logger = logging.getLogger('VideoDownloader')

# Constants
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
YTDLP_EXE = os.path.join("src", "bin", "yt-dlp.exe")
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
BANNER_IMG = os.path.join("src", "icons", "banner.png")
ICON_IMG = os.path.join("src", "icons", "app_icon.ico")
DELETE_ICON = os.path.join("src", "icons", "delete.png")
THUMBNAIL_DIR = "tmp"
DEFAULT_QUALITY = "Best"
URL_PATTERNS = {
    'youtube': r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})',
    'vimeo': r'vimeo\.com\/(\d+)',
    'facebook': r'facebook\.com\/.*\/videos\/(\d+)',
    'twitter': r'twitter\.com\/.*\/status\/(\d+)',
    'instagram': r'instagram\.com\/p\/([a-zA-Z0-9_-]+)'
}

# Ensure directories exist
os.makedirs(THUMBNAIL_DIR, exist_ok=True)
os.makedirs(os.path.dirname(YTDLP_EXE), exist_ok=True)

class VideoInfo:
    """Class to store video information"""
    def __init__(self, url: str, title: str = "", duration: int = 0, 
                 thumbnail_url: str = "", thumbnail_path: str = "", 
                 status: str = "Pending"):
        self.url = url
        self.title = title
        self.duration = duration
        self.thumbnail_url = thumbnail_url
        self.thumbnail_path = thumbnail_path
        self.status = status

class VideoDownloader(wx.Frame):
    def __init__(self, parent, title):
        super(VideoDownloader, self).__init__(parent, title=title, size=(720, 600))

        self.videos: List[VideoInfo] = []
        self.downloading: bool = False
        self.download_threads: List[threading.Thread] = []

        if os.name == 'nt':  # Windows
            self.default_folder = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        else:  # macOS/Linux
            self.default_folder = os.path.join(os.environ['HOME'], 'Desktop')
                
        self.save_path = os.path.join(self.default_folder, 'VideoDownloader')

        # Create status bar
        self.CreateStatusBar()
        self.SetStatusText("Ready")

        # Set up the UI
        self._init_ui()
        
        # Set application icon
        try:
            self.SetIcon(wx.Icon(ICON_IMG))
        except Exception as e:
            logger.error(f"Error loading application icon: {e}")

        # Bind the close event
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
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
            banner = wx.Image(BANNER_IMG, wx.BITMAP_TYPE_PNG).ConvertToBitmap()
            banner_bitmap = wx.StaticBitmap(panel, -1, banner)
            vbox.Add(banner_bitmap, 0, wx.EXPAND | wx.ALL, 10)
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
        self.add_button.Bind(wx.EVT_BUTTON, self.add_video)
        input_buttons_sizer.Add(self.add_button, 0, wx.EXPAND | wx.BOTTOM, 5)
        
        self.add_file_button = wx.Button(panel, label='Import URLs')
        self.add_file_button.Bind(wx.EVT_BUTTON, self.import_urls_from_file)
        input_buttons_sizer.Add(self.add_file_button, 0, wx.EXPAND)
        
        hbox_link.Add(input_buttons_sizer, 0, wx.EXPAND)
        vbox.Add(hbox_link, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Save path button and text field
        hbox_save = wx.BoxSizer(wx.HORIZONTAL)
        self.save_path_button = wx.Button(panel, label='Set Save Path...')
        self.save_path_button.Bind(wx.EVT_BUTTON, self.set_save_path)
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
        
        self.quality_choices = ["Best", "1080p", "720p", "480p", "360p"]
        self.quality_dropdown = wx.Choice(options_box, choices=self.quality_choices)
        self.quality_dropdown.SetSelection(0)  # Default to Best
        options_sizer.Add(self.quality_dropdown, 0, wx.ALL, 5)
        
        # Add playlist options
        playlist_label = wx.StaticText(options_box, label="Playlist:")
        options_sizer.Add(playlist_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        self.playlist_choices = ["Download All", "First Video Only"]
        self.playlist_dropdown = wx.Choice(options_box, choices=self.playlist_choices)
        self.playlist_dropdown.SetSelection(0)  # Default to Download All
        options_sizer.Add(self.playlist_dropdown, 0, wx.ALL, 5)
        
        vbox.Add(options_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Create image list for thumbnails
        self.image_list = wx.ImageList(90, 50)
        self.default_thumbnail_idx = self.image_list.Add(wx.ArtProvider.GetBitmap(wx.ART_MISSING_IMAGE, size=(90, 50)))
        
        # Create icons for the action column
        try:
            # Use custom delete icon if available
            if os.path.exists(DELETE_ICON):
                self.delete_icon = wx.Bitmap(DELETE_ICON)
            else:
                self.delete_icon = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_MENU, (16, 16))
        except Exception as e:
            logger.error(f"Error loading delete icon: {e}")
            self.delete_icon = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_MENU, (16, 16))
            
        self.delete_icon_idx = self.image_list.Add(self.delete_icon)
        
        # Move up/down icons
        self.move_up_icon = wx.ArtProvider.GetBitmap(wx.ART_GO_UP, wx.ART_MENU, (16, 16))
        self.move_up_idx = self.image_list.Add(self.move_up_icon)
        
        self.move_down_icon = wx.ArtProvider.GetBitmap(wx.ART_GO_DOWN, wx.ART_MENU, (16, 16))
        self.move_down_idx = self.image_list.Add(self.move_down_icon)
        
        # Video list view
        self.list_view = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list_view.SetImageList(self.image_list, wx.IMAGE_LIST_SMALL)
        self.list_view.InsertColumn(0, 'Thumbnail', width=100)
        self.list_view.InsertColumn(1, 'Title', width=250)
        self.list_view.InsertColumn(2, 'Duration', width=70)
        self.list_view.InsertColumn(3, 'Status', width=130)
        self.list_view.InsertColumn(4, '', width=30)  # Delete icon
        self.list_view.InsertColumn(5, '', width=30)  # Move up icon
        self.list_view.InsertColumn(6, '', width=30)  # Move down icon
        vbox.Add(self.list_view, 1, wx.EXPAND | wx.ALL, 10)
        
        # Queue management buttons
        hbox_queue = wx.BoxSizer(wx.HORIZONTAL)
        
        self.move_up_button = wx.Button(panel, label='Move Up')
        self.move_up_button.Bind(wx.EVT_BUTTON, self.move_item_up)
        hbox_queue.Add(self.move_up_button, 0, wx.RIGHT, 5)
        
        self.move_down_button = wx.Button(panel, label='Move Down')
        self.move_down_button.Bind(wx.EVT_BUTTON, self.move_item_down)
        hbox_queue.Add(self.move_down_button, 0, wx.RIGHT, 5)
        
        vbox.Add(hbox_queue, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Bind list item events
        self.list_view.Bind(wx.EVT_LEFT_DOWN, self.on_list_click)
        self.list_view.Bind(wx.EVT_RIGHT_DOWN, self.on_right_click)

        # Download and clear list buttons
        hbox_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.clear_button = wx.Button(panel, label='Clear List')
        self.clear_button.Bind(wx.EVT_BUTTON, self.clear_list)
        hbox_buttons.Add(self.clear_button, 0, wx.EXPAND | wx.RIGHT, 10)

        # Update YT-DLP button
        self.update_button = wx.Button(panel, label='Update yt-dlp')
        self.update_button.Bind(wx.EVT_BUTTON, self.update_yt_dlp)
        hbox_buttons.Add(self.update_button, 0, wx.EXPAND)

        hbox_buttons.AddStretchSpacer(1)

        self.download_button = wx.Button(panel, label='Download Videos', size=(200, 50))
        self.download_button.Bind(wx.EVT_BUTTON, self.download_videos)
        font = wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        self.download_button.SetFont(font)
        hbox_buttons.Add(self.download_button, 0, wx.EXPAND)
        vbox.Add(hbox_buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(vbox)
        self.Centre()
        self.Show()

    def check_ytdlp(self):
        """Check if yt-dlp exists and check for updates"""
        # Start a thread to check version to avoid freezing the UI
        threading.Thread(target=self.check_ytdlp_version, daemon=True).start()

    def check_ytdlp_version(self):
        """Check if an update is available for yt-dlp"""
        if not os.path.exists(YTDLP_EXE):
            logger.warning("yt-dlp not found")
            wx.CallAfter(self.update_button.Enable)
            wx.CallAfter(self.SetStatusText, "yt-dlp not found. Click 'Update yt-dlp' to download it.")
            return
            
        try:
            # Get current version
            result = subprocess.run(f'"{YTDLP_EXE}" --version', shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("Could not determine yt-dlp version")
                wx.CallAfter(self.update_button.Enable)
                wx.CallAfter(self.SetStatusText, "Cannot determine yt-dlp version. Update recommended.")
                return
                
            current_version = result.stdout.strip()
            
            # Check latest version from GitHub API
            try:
                with urllib.request.urlopen("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest") as response:
                    release_info = json.loads(response.read().decode())
                    latest_version = release_info["tag_name"]
                    
                    if latest_version.strip() != current_version.strip():
                        logger.info(f"yt-dlp update available: {current_version} → {latest_version}")
                        wx.CallAfter(self.update_button.Enable)
                        wx.CallAfter(self.SetStatusText, f"yt-dlp update available: {current_version} → {latest_version}")
                    else:
                        logger.info(f"yt-dlp is up to date (version {current_version})")
                        wx.CallAfter(self.update_button.Disable)
                        wx.CallAfter(self.SetStatusText, f"yt-dlp is up to date (version {current_version})")
            except Exception as e:
                logger.error(f"Error checking for updates: {e}")
                # Still enable button as a fallback
                wx.CallAfter(self.update_button.Enable)
                wx.CallAfter(self.SetStatusText, "Could not check for updates. Update button enabled as precaution.")
                
        except Exception as e:
            logger.error(f"Error checking yt-dlp version: {e}")
            wx.CallAfter(self.update_button.Enable)
            wx.CallAfter(self.SetStatusText, "Error checking yt-dlp version. Update recommended.")

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
            
            # Check which action column was clicked
            if total_width <= x_pos < total_width + col_widths[4]:
                # Delete icon clicked
                self.remove_selected_item(item)
            elif total_width + col_widths[4] <= x_pos < total_width + col_widths[4] + col_widths[5]:
                # Move up icon clicked
                self.move_item_up(item=item)
            elif total_width + col_widths[4] + col_widths[5] <= x_pos:
                # Move down icon clicked
                self.move_item_down(item=item)
        
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
            move_up_item = menu.Append(-1, "Move Up")
            move_down_item = menu.Append(-1, "Move Down")
            
            # Bind events
            self.Bind(wx.EVT_MENU, lambda evt: self.remove_selected_item(item), remove_item)
            self.Bind(wx.EVT_MENU, lambda evt: self.move_item_up(item=item), move_up_item)
            self.Bind(wx.EVT_MENU, lambda evt: self.move_item_down(item=item), move_down_item)
            
            # Show popup menu
            self.PopupMenu(menu, event.GetPosition())
            menu.Destroy()
        
        event.Skip()

    def move_item_up(self, event=None, item=None):
        """Move selected item up in the queue"""
        if item is None:
            item = self.list_view.GetFirstSelected()
            
        if item > 0:
            # Swap items in video list
            self.videos[item], self.videos[item-1] = self.videos[item-1], self.videos[item]
            
            # Get all data from both rows
            data = []
            for row in [item-1, item]:
                row_data = {
                    'title': self.list_view.GetItemText(row, 1),
                    'duration': self.list_view.GetItemText(row, 2),
                    'status': self.list_view.GetItemText(row, 3),
                    'bgcolor': self.list_view.GetItemBackgroundColour(row)
                }
                data.append(row_data)
            
            # Swap data between rows
            for col in range(1, 4):  # Title, Duration, Status
                self.list_view.SetItem(item-1, col, data[1]['title'] if col == 1 else 
                                                   data[1]['duration'] if col == 2 else 
                                                   data[1]['status'])
                self.list_view.SetItem(item, col, data[0]['title'] if col == 1 else 
                                               data[0]['duration'] if col == 2 else 
                                               data[0]['status'])
            
            # Set the images for action columns (they remain the same)
            self.list_view.SetItem(item-1, 4, "", imageId=self.delete_icon_idx)
            self.list_view.SetItem(item-1, 5, "", imageId=self.move_up_idx)
            self.list_view.SetItem(item-1, 6, "", imageId=self.move_down_idx)
            
            self.list_view.SetItem(item, 4, "", imageId=self.delete_icon_idx)
            self.list_view.SetItem(item, 5, "", imageId=self.move_up_idx)
            self.list_view.SetItem(item, 6, "", imageId=self.move_down_idx)
            
            # Swap colors
            self.list_view.SetItemBackgroundColour(item-1, data[1]['bgcolor'])
            self.list_view.SetItemBackgroundColour(item, data[0]['bgcolor'])
            
            # Select the moved item
            self.list_view.Select(item-1)

    def move_item_down(self, event=None, item=None):
        """Move selected item down in the queue"""
        if item is None:
            item = self.list_view.GetFirstSelected()
            
        if item < self.list_view.GetItemCount() - 1:
            # Swap items in video list
            self.videos[item], self.videos[item+1] = self.videos[item+1], self.videos[item]
            
            # Get all data from both rows
            data = []
            for row in [item, item+1]:
                row_data = {
                    'title': self.list_view.GetItemText(row, 1),
                    'duration': self.list_view.GetItemText(row, 2),
                    'status': self.list_view.GetItemText(row, 3),
                    'bgcolor': self.list_view.GetItemBackgroundColour(row)
                }
                data.append(row_data)
            
            # Swap data between rows
            for col in range(1, 4):  # Title, Duration, Status
                self.list_view.SetItem(item, col, data[1]['title'] if col == 1 else 
                                             data[1]['duration'] if col == 2 else 
                                             data[1]['status'])
                self.list_view.SetItem(item+1, col, data[0]['title'] if col == 1 else 
                                               data[0]['duration'] if col == 2 else 
                                               data[0]['status'])
            
            # Set the images for action columns (they remain the same)
            self.list_view.SetItem(item, 4, "", imageId=self.delete_icon_idx)
            self.list_view.SetItem(item, 5, "", imageId=self.move_up_idx)
            self.list_view.SetItem(item, 6, "", imageId=self.move_down_idx)
            
            self.list_view.SetItem(item+1, 4, "", imageId=self.delete_icon_idx)
            self.list_view.SetItem(item+1, 5, "", imageId=self.move_up_idx)
            self.list_view.SetItem(item+1, 6, "", imageId=self.move_down_idx)
            
            # Swap colors
            self.list_view.SetItemBackgroundColour(item, data[1]['bgcolor'])
            self.list_view.SetItemBackgroundColour(item+1, data[0]['bgcolor'])
            
            # Select the moved item
            self.list_view.Select(item+1)

    def remove_selected_item(self, index):
        """Remove item at the specified index"""
        if index != -1:
            # Remove from video_list
            self.videos.pop(index)
            # Remove from list_view
            self.list_view.DeleteItem(index)
            self.SetStatusText(f"Removed item at position {index+1}")

    def add_video(self, event):
        """Add video URLs to the download queue"""
        links = self.link_entry.GetValue().split('\n')
        added_count = 0
        
        for link in links:
            link = link.strip()
            if link and not self._is_url_in_queue(link):
                if self.is_valid_link(link):
                    # Process possible playlist
                    if self.is_playlist(link) and self.playlist_dropdown.GetSelection() == 0:
                        threading.Thread(target=self.process_playlist, args=(link,)).start()
                        added_count += 1
                    else:
                        # Add single video
                        video_info = VideoInfo(url=link)
                        self.videos.append(video_info)
                        index = self.list_view.InsertItem(self.list_view.GetItemCount(), "", self.default_thumbnail_idx)
                        self.list_view.SetItem(index, 1, "Fetching metadata...")
                        
                        # Set action icons
                        self.list_view.SetItem(index, 4, "", imageId=self.delete_icon_idx)
                        self.list_view.SetItem(index, 5, "", imageId=self.move_up_idx)
                        self.list_view.SetItem(index, 6, "", imageId=self.move_down_idx)
                        
                        threading.Thread(target=self.fetch_metadata, args=(index, link)).start()
                        added_count += 1
                else:
                    wx.MessageBox(f"Invalid video link: {link}", "Error", wx.ICON_ERROR)
        
        if added_count > 0:
            self.SetStatusText(f"Added {added_count} video(s) to queue")
        
        self.link_entry.SetValue("")

    def _is_url_in_queue(self, url: str) -> bool:
        """Check if URL is already in the queue"""
        return any(video.url == url for video in self.videos)
        
    def is_playlist(self, url: str) -> bool:
        """Check if URL is a playlist"""
        return "playlist" in url or "list=" in url
        
    def process_playlist(self, playlist_url: str):
        """Process a playlist URL and add all videos"""
        wx.CallAfter(self.SetStatusText, "Fetching playlist videos...")
        
        try:
            # Get playlist videos
            command = f'"{YTDLP_EXE}" --flat-playlist --dump-json {playlist_url}'
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                videos = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        try:
                            video_info = json.loads(line)
                            videos.append(video_info)
                        except json.JSONDecodeError:
                            continue
                
                wx.CallAfter(self.SetStatusText, f"Found {len(videos)} videos in playlist")
                
                # Add each video to the queue
                for video in videos:
                    video_url = f"https://www.youtube.com/watch?v={video.get('id')}"
                    if not self._is_url_in_queue(video_url):
                        video_info = VideoInfo(url=video_url)
                        wx.CallAfter(self._add_video_to_list, video_info)
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"Failed to process playlist: {error_msg}")
                wx.CallAfter(wx.MessageBox, f"Failed to process playlist. Error: {error_msg}", "Error", wx.ICON_ERROR)
                
        except Exception as e:
            logger.error(f"Error processing playlist: {e}")
            wx.CallAfter(wx.MessageBox, f"Error processing playlist: {e}", "Error", wx.ICON_ERROR)
    
    def _add_video_to_list(self, video_info: VideoInfo):
        """Add a video to the list view and start metadata fetching"""
        self.videos.append(video_info)
        index = self.list_view.InsertItem(self.list_view.GetItemCount(), "", self.default_thumbnail_idx)
        self.list_view.SetItem(index, 1, "Fetching metadata...")
        
        # Set action icons
        self.list_view.SetItemImage(index, self.delete_icon_idx, column=4)
        self.list_view.SetItemImage(index, self.move_up_idx, column=5)
        self.list_view.SetItemImage(index, self.move_down_idx, column=6)
        
        threading.Thread(target=self.fetch_metadata, args=(index, video_info.url)).start()
    
    def import_urls_from_file(self, event):
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
                    if url and self.is_valid_link(url) and not self._is_url_in_queue(url):
                        valid_urls.append(url)
                
                if valid_urls:
                    for url in valid_urls:
                        video_info = VideoInfo(url=url)
                        self.videos.append(video_info)
                        index = self.list_view.InsertItem(self.list_view.GetItemCount(), "", self.default_thumbnail_idx)
                        self.list_view.SetItem(index, 1, "Fetching metadata...")
                        
                        # Set action icons
                        self.list_view.SetItem(index, 4, "", imageId=self.delete_icon_idx)
                        self.list_view.SetItem(index, 5, "", imageId=self.move_up_idx)
                        self.list_view.SetItem(index, 6, "", imageId=self.move_down_idx)
                        
                        threading.Thread(target=self.fetch_metadata, args=(index, url)).start()
                    
                    self.SetStatusText(f"Imported {len(valid_urls)} valid URLs from file")
                else:
                    wx.MessageBox("No valid URLs found in the file", "Import URLs", wx.ICON_INFORMATION)
                    
            except Exception as e:
                logger.error(f"Error importing URLs: {e}")
                wx.MessageBox(f"Error opening file: {e}", "Error", wx.ICON_ERROR)

    def is_valid_link(self, link: str) -> bool:
        """Check if a URL is valid"""
        # Improved URL validation to support more platforms
        return re.match(r'^https?://(www\.)?(youtube|youtu\.be|vimeo|dailymotion|facebook|twitter|instagram).*', link) is not None

    def extract_video_id(self, link: str) -> str:
        """Extract video ID from URL"""
        for platform, pattern in URL_PATTERNS.items():
            match = re.search(pattern, link)
            if match:
                return match.group(1)
                
        # Default to full link
        return link

    def download_thumbnail(self, thumbnail_url: str, video_id: str) -> Optional[str]:
        """Download and resize video thumbnail"""
        try:
            # Generate a unique filename for the thumbnail
            thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{video_id}.jpg")
            
            # Download the thumbnail
            context = ssl._create_unverified_context()
            req = urllib.request.Request(
                thumbnail_url,
                data=None,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            )
            with urllib.request.urlopen(req, context=context) as response:
                with open(thumbnail_path, 'wb') as out_file:
                    out_file.write(response.read())
            
            # Resize the thumbnail to fit in the list view
            img = Image.open(thumbnail_path)
            img = img.resize((90, 50), Image.LANCZOS)
            img.save(thumbnail_path)
            
            return thumbnail_path
        except Exception as e:
            logger.error(f"Error downloading thumbnail: {e}")
            return None

    def fetch_metadata(self, index: int, link: str):
        """Fetch video metadata using yt-dlp"""
        try:
            wx.CallAfter(self.SetStatusText, f"Fetching metadata for video {index+1}...")
            command = f'"{YTDLP_EXE}" --dump-json {link}'
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                info_dict = json.loads(result.stdout)
                title = info_dict.get('title', 'Unknown')
                duration = info_dict.get('duration', 0)
                
                # Format duration nicely
                if duration:
                    if duration > 3600:  # More than an hour
                        duration_str = f"{duration // 3600}:{(duration % 3600) // 60:02d}:{duration % 60:02d}"
                    else:
                        duration_str = f"{duration // 60}:{duration % 60:02d}"
                else:
                    duration_str = "Unknown"
                
                # Get thumbnail URL
                thumbnail_url = info_dict.get('thumbnail')
                video_id = info_dict.get('id', self.extract_video_id(link))
                
                # Update video info
                self.videos[index].title = title
                self.videos[index].duration = duration
                self.videos[index].thumbnail_url = thumbnail_url
                
                if thumbnail_url:
                    # Download and process thumbnail
                    thumbnail_path = self.download_thumbnail(thumbnail_url, video_id)
                    if thumbnail_path:
                        self.videos[index].thumbnail_path = thumbnail_path
                        # Add thumbnail to image list
                        wx.CallAfter(self.update_thumbnail, index, thumbnail_path)
                
                wx.CallAfter(self.list_view.SetItem, index, 1, title)
                wx.CallAfter(self.list_view.SetItem, index, 2, duration_str)
                wx.CallAfter(self.list_view.SetItem, index, 3, "Ready")
                wx.CallAfter(self.SetStatusText, f"Metadata fetched for {title}")
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"Failed to get metadata: {error_msg}")
                wx.CallAfter(self.list_view.SetItem, index, 1, "Error: Metadata fetch failed")
                wx.CallAfter(self.list_view.SetItem, index, 3, "Error")
                wx.CallAfter(self.SetStatusText, f"Failed to get metadata: {error_msg}")
                wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
        except Exception as e:
            logger.error(f"Error fetching metadata: {e}")
            wx.CallAfter(self.list_view.SetItem, index, 1, f"Error: {str(e)[:30]}...")
            wx.CallAfter(self.list_view.SetItem, index, 3, "Error")
            wx.CallAfter(self.SetStatusText, f"Error fetching metadata: {str(e)}")
            wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red

    def update_thumbnail(self, index: int, thumbnail_path: str):
        """Update the thumbnail image in the list view"""
        try:
            # Load the thumbnail image
            img = wx.Image(thumbnail_path, wx.BITMAP_TYPE_ANY)
            # Convert to bitmap and add to image list
            bitmap = img.ConvertToBitmap()
            img_idx = self.image_list.Add(bitmap)
            # Update the list item with the new image
            self.list_view.SetItemImage(index, img_idx)
            
            # Make sure action icons are preserved
            self.list_view.SetItem(index, 4, "", imageId=self.delete_icon_idx)
            self.list_view.SetItem(index, 5, "", imageId=self.move_up_idx)
            self.list_view.SetItem(index, 6, "", imageId=self.move_down_idx)
        except Exception as e:
            logger.error(f"Error updating thumbnail: {e}")

    def clear_list(self, event):
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
                self.image_list.RemoveAll()
                # Re-add icons
                self.default_thumbnail_idx = self.image_list.Add(wx.ArtProvider.GetBitmap(wx.ART_MISSING_IMAGE, size=(90, 50)))
                self.delete_icon_idx = self.image_list.Add(self.delete_icon)
                self.move_up_idx = self.image_list.Add(self.move_up_icon)
                self.move_down_idx = self.image_list.Add(self.move_down_icon)
                self.SetStatusText("Download queue cleared")
            dialog.Destroy()

    def download_videos(self, event):
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
            thread = threading.Thread(target=self.download_video, args=(index, video_info.url))
            thread.daemon = True
            thread.start()
            self.download_threads.append(thread)
            
        # Start a thread to monitor download completion
        threading.Thread(target=self.monitor_downloads, daemon=True).start()

    def monitor_downloads(self):
        """Monitor download threads and re-enable buttons when all complete"""
        for thread in self.download_threads:
            thread.join()
            
        wx.CallAfter(self.on_downloads_complete)

    def on_downloads_complete(self):
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

    def update_progress(self, index: int, progress: str):
        """Update the progress display in the list view"""
        self.list_view.SetItem(index, 3, f"Downloading {progress}")
    
    def set_row_color(self, index: int, color: wx.Colour):
        """Set the background color for a row in the list view"""
        for col in range(self.list_view.GetColumnCount()):
            self.list_view.SetItemBackgroundColour(index, color)
    
    def set_save_path(self, event):
        """Set the download save path using directory dialog"""
        save_path_dialog = wx.DirDialog(self, "Select Save Path", self.save_path, wx.DD_DEFAULT_STYLE)
        if save_path_dialog.ShowModal() == wx.ID_OK:
            self.save_path = save_path_dialog.GetPath()
            self.save_path_text.SetValue(self.save_path)
            self.SetStatusText(f"Save path set to {self.save_path}")
        save_path_dialog.Destroy()

    def update_yt_dlp(self, event):
        """Download or update yt-dlp executable"""
        try:
            self.SetStatusText("Updating yt-dlp...")
            wx.MessageBox("Updating yt-dlp. Please wait...", "Update", wx.ICON_INFORMATION)
            
            # Ensure the bin directory exists
            bin_dir = os.path.dirname(YTDLP_EXE)
            if not os.path.exists(bin_dir):
                os.makedirs(bin_dir)
                
            # Download the latest version
            urllib.request.urlretrieve(YTDLP_URL, YTDLP_EXE)
            
            # Set execute permission on Linux/macOS
            if os.name != 'nt':
                os.chmod(YTDLP_EXE, 0o755)
                
            wx.MessageBox("yt-dlp has been updated successfully!", "Update", wx.ICON_INFORMATION)
            self.SetStatusText("yt-dlp updated successfully")
            
            # Check version after update
            self.check_ytdlp()
        except Exception as e:
            logger.error(f"Failed to update yt-dlp: {e}")
            wx.MessageBox(f"Failed to update yt-dlp. Error: {e}", "Update Error", wx.ICON_ERROR)
            self.SetStatusText(f"Update failed: {str(e)}")
    
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
        
    def build_download_command(self, video_link: str, output_path: str) -> str:
        """Build the yt-dlp command based on selected options"""
        if self.audio_only.GetValue():
            return f'"{YTDLP_EXE}" -x --audio-format mp3 --audio-quality 0 ' \
                   f'--progress-template "%(progress._percent_str)s" --output "{output_path}" {video_link}'
        else:
            # Get selected quality
            quality_selection = self.quality_choices[self.quality_dropdown.GetSelection()]
            
            if quality_selection == "Best":
                format_spec = "bestvideo+bestaudio[ext=m4a]/best"
            elif quality_selection == "1080p":
                format_spec = "bestvideo[height<=1080]+bestaudio[ext=m4a]/best[height<=1080]"
            elif quality_selection == "720p":
                format_spec = "bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]"
            elif quality_selection == "480p":
                format_spec = "bestvideo[height<=480]+bestaudio[ext=m4a]/best[height<=480]"
            elif quality_selection == "360p":
                format_spec = "bestvideo[height<=360]+bestaudio[ext=m4a]/best[height<=360]"
            else:
                format_spec = "bestvideo+bestaudio[ext=m4a]/best"
            
            return f'"{YTDLP_EXE}" -f {format_spec} --merge-output-format mp4 ' \
                   f'--progress-template "%(progress._percent_str)s" --output "{output_path}" {video_link}'
        
    def download_video(self, index: int, video_link: str):
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
                command = f'"{YTDLP_EXE}" --get-title {video_link}'
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    video_title = result.stdout.strip()
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    logger.error(f"Failed to get title: {error_msg}")
                    wx.CallAfter(self.list_view.SetItem, index, 3, "Failed")
                    wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
                    return
            
            # Replace invalid filename characters
            video_title = re.sub(r'[\\/*?:"<>|]', '_', video_title)
            
            # Determine file extension based on download mode
            extension = ".mp3" if self.audio_only.GetValue() else ".mp4"
            output_path = os.path.join(self.save_path, f"{video_title}{extension}")
            
            # Check if file already exists
            if os.path.exists(output_path):
                wx.CallAfter(self.list_view.SetItem, index, 3, "Already Downloaded")
                wx.CallAfter(self.set_row_color, index, wx.Colour(200, 255, 200))  # Light green
                return
                
            # Build command based on options
            command = self.build_download_command(video_link, output_path)
            
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
                    wx.CallAfter(self.update_progress, index, line)
                elif "download" in line.lower() and "%" in line:
                    # Try to extract percentage from other progress formats
                    match = re.search(r'(\d{1,3}\.\d)%', line)
                    if match:
                        wx.CallAfter(self.update_progress, index, f"{match.group(1)}%")
            
            # Wait for process to complete
            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0:
                wx.CallAfter(self.list_view.SetItem, index, 3, "Downloaded")
                wx.CallAfter(self.set_row_color, index, wx.Colour(200, 255, 200))  # Light green
                wx.CallAfter(self.SetStatusText, f"Successfully downloaded: {video_title}")
            else:
                error_output = process.stderr.read() if process.stderr else "Unknown error"
                logger.error(f"Download failed: {error_output}")
                wx.CallAfter(self.list_view.SetItem, index, 3, "Failed")
                wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
                wx.CallAfter(self.SetStatusText, f"Download failed: {video_title}")
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            wx.CallAfter(self.list_view.SetItem, index, 3, "Error")
            wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
            wx.CallAfter(self.SetStatusText, f"Error: {str(e)}")


def main():
    """Main application entry point"""
    app = wx.App()
    VideoDownloader(None, title='Video Downloader')
    app.MainLoop()


if __name__ == '__main__':
    main()