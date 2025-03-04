# version="1.0"

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
from datetime import datetime
from PIL import Image
from io import BytesIO

# yt-dlp executable path
CURRENT_DIR = os.path.abspath(__file__)
YTDLP_EXE = os.path.join("src", "bin", "yt-dlp.exe")  # Correct path
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
BANNER_IMG = os.path.join("src", "icons", "banner.png")  # Correct path
ICON_IMG = os.path.join("src", "icons", "app_icon.ico")  # Correct path
THUMBNAIL_DIR = "tmp"

# Create thumbnails directory if it doesn't exist
if not os.path.exists(THUMBNAIL_DIR):
    os.makedirs(THUMBNAIL_DIR)

class VideoDownloader(wx.Frame):
    def __init__(self, parent, title):
        super(VideoDownloader, self).__init__(parent, title=title, size=(720, 600))

        self.video_list = []
        self.thumbnail_list = {}
        self.downloading = False
        self.download_threads = []

        if os.name == 'nt':  # Windows
            self.default_folder = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        else:  # macOS/Linux
            self.default_folder = os.path.join(os.environ['HOME'], 'Desktop')
                
        self.save_path = os.path.join(self.default_folder, 'VideoDownloader')

        # Create status bar
        self.CreateStatusBar()
        self.SetStatusText("Ready")

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Add header banner
        try:
            banner = wx.Image(BANNER_IMG, wx.BITMAP_TYPE_PNG).ConvertToBitmap()
            banner_bitmap = wx.StaticBitmap(panel, -1, banner)
            vbox.Add(banner_bitmap, 0, wx.EXPAND | wx.ALL, 10)
        except Exception as e:
            print(f"Error loading banner: {e}")
            # Create placeholder if banner cannot be loaded
            banner_text = wx.StaticText(panel, -1, "Video Downloader")
            font = wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.BOLD)
            banner_text.SetFont(font)
            vbox.Add(banner_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Input field for video link and add button
        hbox_link = wx.BoxSizer(wx.HORIZONTAL)
        self.link_entry = wx.TextCtrl(panel, style=wx.TE_MULTILINE)
        hbox_link.Add(self.link_entry, 1, wx.EXPAND | wx.RIGHT, 10)

        self.add_button = wx.Button(panel, label='Add Video')
        self.add_button.Bind(wx.EVT_BUTTON, self.add_video)
        hbox_link.Add(self.add_button, 0, wx.EXPAND)
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
        
        vbox.Add(options_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Create image list for thumbnails
        self.image_list = wx.ImageList(90, 50)
        self.default_thumbnail_idx = self.image_list.Add(wx.ArtProvider.GetBitmap(wx.ART_MISSING_IMAGE, size=(90, 50)))
        
        # Create delete icon for the action column
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
        self.list_view.InsertColumn(1, 'Title', width=310)
        self.list_view.InsertColumn(2, 'Duration', width=70)
        self.list_view.InsertColumn(3, 'Status', width=100)
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

        # Set application icon
        try:
            self.SetIcon(wx.Icon(ICON_IMG))
        except Exception as e:
            print(f"Error loading application icon: {e}")

        # Bind the close event
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        # Check for yt-dlp and its updates
        self.check_ytdlp()
        
        # Schedule periodic update checks (every 24 hours)
        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda evt: self.check_ytdlp(), self.update_timer)
        self.update_timer.Start(1000 * 60 * 60 * 24)  # 24 hours in milliseconds

    def check_ytdlp(self):
        """Check if yt-dlp exists and check for updates"""
        # Start a thread to check version to avoid freezing the UI
        threading.Thread(target=self.check_ytdlp_version, daemon=True).start()

    def check_ytdlp_version(self):
        """Check if an update is available for yt-dlp"""
        if not os.path.exists(YTDLP_EXE):
            self.update_button.Enable()
            self.SetStatusText("yt-dlp not found. Click 'Update yt-dlp' to download it.")
            return
            
        try:
            # Get current version
            result = subprocess.run(f'"{YTDLP_EXE}" --version', shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                self.update_button.Enable()
                self.SetStatusText("Cannot determine yt-dlp version. Update recommended.")
                return
                
            current_version = result.stdout.strip()
            
            # Check latest version from GitHub API
            try:
                with urllib.request.urlopen("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest") as response:
                    release_info = json.loads(response.read().decode())
                    latest_version = release_info["tag_name"]
                    
                    if latest_version.strip() != current_version.strip():
                        self.update_button.Enable()
                        self.SetStatusText(f"yt-dlp update available: {current_version} → {latest_version}")
                    else:
                        self.update_button.Disable()
                        self.SetStatusText(f"yt-dlp is up to date (version {current_version})")
            except Exception as e:
                print(f"Error checking for updates: {e}")
                # Still enable button as a fallback
                self.update_button.Enable()
                self.SetStatusText("Could not check for updates. Update button enabled as precaution.")
                
        except Exception as e:
            print(f"Error checking yt-dlp version: {e}")
            self.update_button.Enable()
            self.SetStatusText("Error checking yt-dlp version. Update recommended.")

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
            # Swap items in video_list
            self.video_list[item], self.video_list[item-1] = self.video_list[item-1], self.video_list[item]
            
            # Get all data from both rows
            data = []
            for row in [item-1, item]:
                row_data = {
                    'thumbnail_idx': self.list_view.GetItemImage(row),
                    'title': self.list_view.GetItemText(row, 1),
                    'duration': self.list_view.GetItemText(row, 2),
                    'status': self.list_view.GetItemText(row, 3),
                    'bgcolor': self.list_view.GetItemBackgroundColour(row)
                }
                data.append(row_data)
            
            # Swap data between rows
            for col in range(1, 4):  # Title, Duration, Status
                self.list_view.SetItem(item-1, col, data[1]['title'] if col == 1 else data[1]['duration'] if col == 2 else data[1]['status'])
                self.list_view.SetItem(item, col, data[0]['title'] if col == 1 else data[0]['duration'] if col == 2 else data[0]['status'])
            
            # Swap images
            self.list_view.SetItemImage(item-1, data[1]['thumbnail_idx'])
            self.list_view.SetItemImage(item, data[0]['thumbnail_idx'])
            
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
            # Swap items in video_list
            self.video_list[item], self.video_list[item+1] = self.video_list[item+1], self.video_list[item]
            
            # Get all data from both rows
            data = []
            for row in [item, item+1]:
                row_data = {
                    'thumbnail_idx': self.list_view.GetItemImage(row),
                    'title': self.list_view.GetItemText(row, 1),
                    'duration': self.list_view.GetItemText(row, 2),
                    'status': self.list_view.GetItemText(row, 3),
                    'bgcolor': self.list_view.GetItemBackgroundColour(row)
                }
                data.append(row_data)
            
            # Swap data between rows
            for col in range(1, 4):  # Title, Duration, Status
                self.list_view.SetItem(item, col, data[1]['title'] if col == 1 else data[1]['duration'] if col == 2 else data[1]['status'])
                self.list_view.SetItem(item+1, col, data[0]['title'] if col == 1 else data[0]['duration'] if col == 2 else data[0]['status'])
            
            # Swap images
            self.list_view.SetItemImage(item, data[1]['thumbnail_idx'])
            self.list_view.SetItemImage(item+1, data[0]['thumbnail_idx'])
            
            # Swap colors
            self.list_view.SetItemBackgroundColour(item, data[1]['bgcolor'])
            self.list_view.SetItemBackgroundColour(item+1, data[0]['bgcolor'])
            
            # Select the moved item
            self.list_view.Select(item+1)

    def remove_selected_item(self, index):
        """Remove item at the specified index"""
        if index != -1:
            # Remove from video_list
            self.video_list.pop(index)
            # Remove from list_view
            self.list_view.DeleteItem(index)
            self.SetStatusText(f"Removed item at position {index+1}")

    def add_video(self, event):
        """Add video URLs to the download queue"""
        links = self.link_entry.GetValue().split('\n')
        added_count = 0
        
        for link in links:
            link = link.strip()
            if link and link not in self.video_list:
                if self.is_valid_link(link):
                    video_id = self.extract_video_id(link)
                    self.video_list.append(link)
                    index = self.list_view.InsertItem(self.list_view.GetItemCount(), video_id, self.default_thumbnail_idx)
                    self.list_view.SetItem(index, 1, "Fetching metadata...")
                    
                    # Set action icons
                    self.list_view.SetItemImage(index, self.delete_icon_idx, column=4)
                    self.list_view.SetItemImage(index, self.move_up_idx, column=5)
                    self.list_view.SetItemImage(index, self.move_down_idx, column=6)
                    
                    threading.Thread(target=self.fetch_metadata, args=(index, link)).start()
                    added_count += 1
                else:
                    wx.MessageBox(f"Invalid video link: {link}", "Error", wx.ICON_ERROR)
        
        if added_count > 0:
            self.SetStatusText(f"Added {added_count} video(s) to queue")
        
        self.link_entry.SetValue("")

    def is_valid_link(self, link):
        """Check if a URL is valid"""
        # Improved URL validation to support more platforms
        return re.match(r'^https?://(www\.)?(youtube|youtu\.be|vimeo|dailymotion|facebook|twitter|instagram).*', link) is not None

    def extract_video_id(self, link):
        """Extract video ID from URL"""
        # YouTube
        youtube_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', link)
        if youtube_match:
            return youtube_match.group(1)
            
        # Vimeo
        vimeo_match = re.search(r'vimeo\.com\/(\d+)', link)
        if vimeo_match:
            return vimeo_match.group(1)
            
        # Default to full link
        return link

    def download_thumbnail(self, thumbnail_url, video_id):
        """Download and resize video thumbnail"""
        try:
            # Generate a unique filename for the thumbnail
            thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{video_id}.jpg")
            
            # Download the thumbnail
            urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
            
            # Resize the thumbnail to fit in the list view
            img = Image.open(thumbnail_path)
            img = img.resize((90, 50), Image.LANCZOS)
            img.save(thumbnail_path)
            
            return thumbnail_path
        except Exception as e:
            print(f"Error downloading thumbnail: {e}")
            return None

    def fetch_metadata(self, index, link):
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
                if duration > 3600:  # More than an hour
                    duration_str = f"{duration // 3600}:{(duration % 3600) // 60:02d}:{duration % 60:02d}"
                else:
                    duration_str = f"{duration // 60}:{duration % 60:02d}"
                
                # Get thumbnail URL
                thumbnail_url = info_dict.get('thumbnail')
                video_id = self.extract_video_id(link)
                
                if thumbnail_url:
                    # Download and process thumbnail
                    thumbnail_path = self.download_thumbnail(thumbnail_url, video_id)
                    if thumbnail_path:
                        # Add thumbnail to image list
                        wx.CallAfter(self.update_thumbnail, index, thumbnail_path)
                
                wx.CallAfter(self.list_view.SetItem, index, 1, title)
                wx.CallAfter(self.list_view.SetItem, index, 2, duration_str)
                wx.CallAfter(self.SetStatusText, f"Metadata fetched for {title}")
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                wx.CallAfter(self.list_view.SetItem, index, 3, "Title Error")
                wx.CallAfter(self.SetStatusText, f"Failed to get title: {error_msg}")
                wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
                return

            # Update status
            wx.CallAfter(self.list_view.SetItem, index, 3, "Starting...")
            
            # Build command based on options
            if self.audio_only.GetValue():
                command = f'"{YTDLP_EXE}" -x --audio-format mp3 --audio-quality 0 --progress-template "%(progress._percent_str)s" --output "{output_path}" {video_link}'
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
                
                command = f'"{YTDLP_EXE}" -f {format_spec} --merge-output-format mp4 --progress-template "%(progress._percent_str)s" --output "{output_path}" {video_link}'
                
            # Start download process
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            
            # Monitor stdout for progress updates
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if re.match(r'^\d{1,3}\.\d% index, 1, "Failed to fetch metadata")
                wx.CallAfter(self.SetStatusText, f"Failed to fetch metadata: {error_msg}")
                wx.CallAfter(wx.MessageBox, f"Failed to fetch metadata for {link}. Error: {error_msg}", "Error", wx.ICON_ERROR)
                wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
        except Exception as e:
            wx.CallAfter(self.list_view.SetItem, index, 1, f"Error: {str(e)[:30]}...")
            wx.CallAfter(self.SetStatusText, f"Error fetching metadata: {str(e)}")
            wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red

    def update_thumbnail(self, index, thumbnail_path):
        """Update the thumbnail image in the list view"""
        try:
            # Load the thumbnail image
            img = wx.Image(thumbnail_path, wx.BITMAP_TYPE_ANY)
            # Convert to bitmap and add to image list
            bitmap = img.ConvertToBitmap()
            img_idx = self.image_list.Add(bitmap)
            # Update the list item with the new image
            self.list_view.SetItemImage(index, img_idx)
        except Exception as e:
            print(f"Error updating thumbnail: {e}")

    def clear_list(self, event):
        """Clear the download queue"""
        if self.downloading:
            wx.MessageBox("Cannot clear list while downloads are in progress", "Warning", wx.ICON_WARNING)
            return
            
        if self.list_view.GetItemCount() > 0:
            dialog = wx.MessageDialog(self, "Are you sure you want to clear the download queue?", 
                                    "Confirm Clear", wx.YES_NO | wx.ICON_QUESTION)
            if dialog.ShowModal() == wx.ID_YES:
                self.video_list.clear()
                self.list_view.DeleteAllItems()
                # Reset the image list except for icons
                old_icons = [self.default_thumbnail_idx, self.delete_icon_idx, self.move_up_idx, self.move_down_idx]
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
            
        if len(self.video_list) == 0:
            wx.MessageBox("No videos in queue to download", "Information", wx.ICON_INFORMATION)
            return
            
        # Create the VideoDownloader folder if it doesn't exist
        if not os.path.exists(self.save_path):
            try:
                os.makedirs(self.save_path)
            except Exception as e:
                wx.MessageBox(f"Failed to create download directory: {e}", "Error", wx.ICON_ERROR)
                return

        self.downloading = True
        self.download_button.Disable()
        self.clear_button.Disable()
        self.download_threads = []
        
        for index, video_link in enumerate(self.video_list):
            thread = threading.Thread(target=self.download_video, args=(index, video_link))
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
        wx.MessageBox("All downloads have completed", "Downloads Complete", wx.ICON_INFORMATION)

    def update_progress(self, index, progress):
        """Update the progress display in the list view"""
        self.list_view.SetItem(index, 3, f"Downloading {progress}")
    
    def set_row_color(self, index, color):
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
        except Exception as e:
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
                print(f"Error cleaning up thumbnails: {e}")
                
        event.Skip()
        
    def download_video(self, index, video_link):
        """Download a single video"""
        try:
            self.list_view.SetItem(index, 3, "Checking...")
            wx.CallAfter(self.SetStatusText, f"Downloading video {index+1}...")
            
            # Get video info to extract the title
            command = f'"{YTDLP_EXE}" --get-title {video_link}'
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                video_title = result.stdout.strip()
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
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                wx.CallAfter(self.list_view.SetItem,, line):
                    wx.CallAfter(self.update_progress, index, line)
            
            # Wait for process to complete
            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0:
                wx.CallAfter(self.list_view.SetItem, index, 3, "Downloaded")
                wx.CallAfter(self.set_row_color, index, wx.Colour(200, 255, 200))  # Light green
                wx.CallAfter(self.SetStatusText, f"Successfully downloaded: {video_title}")
            else:
                error_output = process.stderr.read() if process.stderr else "Unknown error"
                wx.CallAfter(self.list_view.SetItem, index, 3, "Failed")
                wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
                wx.CallAfter(self.SetStatusText, f"Download failed: {video_title}")
                wx.CallAfter(wx.MessageBox, f"Failed to download {video_title}. Error: {error_output}", "Download Error", wx.ICON_ERROR)
        except Exception as e:
            wx.CallAfter(self.list_view.SetItem, index, 3, "Error")
            wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
            wx.CallAfter(self.SetStatusText, f"Error: {str(e)}")
            wx.CallAfter(wx.MessageBox, f"An error occurred: {e}", "Error", wx.ICON_ERROR) index, 1, "Failed to fetch metadata")
                wx.CallAfter(self.SetStatusText, f"Failed to fetch metadata: {error_msg}")
                wx.CallAfter(wx.MessageBox, f"Failed to fetch metadata for {link}. Error: {error_msg}", "Error", wx.ICON_ERROR)
                wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red
        except Exception as e:
            wx.CallAfter(self.list_view.SetItem, index, 1, f"Error: {str(e)[:30]}...")
            wx.CallAfter(self.SetStatusText, f"Error fetching metadata: {str(e)}")
            wx.CallAfter(self.set_row_color, index, wx.Colour(255, 200, 200))  # Light red

    def update_thumbnail(self, index, thumbnail_path):
        """Update the thumbnail image in the list view"""
        try:
            # Load the thumbnail image
            img = wx.Image(thumbnail_path, wx.BITMAP_TYPE_ANY)
            # Convert to bitmap and add to image list
            bitmap = img.ConvertToBitmap()
            img_idx = self.image_list.Add(bitmap)
            # Update the list item with the new image
            self.list_view.SetItemImage(index, img_idx)
        except Exception as e:
            print(f"Error updating thumbnail: {e}")

    def clear_list(self, event):
        """Clear the download queue"""
        if self.downloading:
            wx.MessageBox("Cannot clear list while downloads are in progress", "Warning", wx.ICON_WARNING)
            return
            
        if self.list_view.GetItemCount() > 0:
            dialog = wx.MessageDialog(self, "Are you sure you want to clear the download queue?", 
                                    "Confirm Clear", wx.YES_NO | wx.ICON_QUESTION)
            if dialog.ShowModal() == wx.ID_YES:
                self.video_list.clear()
                self.list_view.DeleteAllItems()
                # Reset the image list except for icons
                old_icons = [self.default_thumbnail_idx, self.delete_icon_idx, self.move_up_idx, self.move_down_idx]
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
            
        if len(self.video_list) == 0:
            wx.MessageBox("No videos in queue to download", "Information", wx.ICON_INFORMATION)
            return
            
        # Create the VideoDownloader folder if it doesn't exist
        if not os.path.exists(self.save_path):
            try:
                os.makedirs(self.save_path)
            except Exception as e:
                wx.MessageBox(f"Failed to create download directory: {e}", "Error", wx.ICON_ERROR)
                return

        self.downloading = True
        self.download_button.Disable()
        self.clear_button.Disable()
        self.download_threads = []
        
        for index, video_link in enumerate(self.video_list):
            thread = threading.Thread(target=self.download_video, args=(index, video_link))
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
        wx.MessageBox("All downloads have completed", "Downloads Complete", wx.ICON_INFORMATION)

    def download_video(self, index, video_link):
        """Download a single video"""
        try:
            self.list_view.SetItem(index, 3, "Checking...")
            wx.CallAfter(self.SetStatusText, f"Downloading video {index+1}...")
            
            # Get video info to extract the title
            command = f'"{YTDLP_EXE}" --get-title {video_link}'
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                video_title = result.stdout.strip()
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
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                wx.CallAfter(self.list_view.SetItem,