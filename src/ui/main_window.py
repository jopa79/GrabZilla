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
    BANNER_IMG, ICON_IMG, THUMBNAIL_DIR,
    QUALITY_CHOICES
)
from src.core.video import VideoInfo, is_valid_link, extract_video_id, download_thumbnail, format_duration
from src.core.downloader import (
    check_ytdlp_exists, get_ytdlp_version, get_latest_ytdlp_version, 
    update_ytdlp, fetch_video_metadata, build_download_command
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
        self.metadata_threads: List[threading.Thread] = []  # Track metadata threads
        self.cancel_requested: bool = False  # Track cancellation state
        # Set default folder to Desktop on Windows
        self.default_folder = os.path.join(os.environ['USERPROFILE'], 'Desktop')
                
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
        self.quality_dropdown.SetSelection(3)  # Default to 1080
        options_sizer.Add(self.quality_dropdown, 0, wx.ALL, 5)
        

        
        vbox.Add(options_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        # Create image list for thumbnails with sufficient error handling
        try:
            self.image_list = wx.ImageList(90, 50)
            
            # Create a simple default thumbnail
            default_bitmap = wx.Bitmap(90, 50)
            self.default_thumbnail_idx = self.image_list.Add(default_bitmap)
            
        except Exception as e:
            logger.error(f"Error initializing image list: {e}")
            # Try to continue without images
            wx.MessageBox(f"Could not initialize images. The application will continue but some icons may be missing.\nError: {e}", 
                         "Warning", wx.ICON_WARNING)
            
        # Video list view
        self.list_view = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)
        
        # Set the image list if it was created successfully
        if hasattr(self, 'image_list'):
            self.list_view.SetImageList(self.image_list, wx.IMAGE_LIST_SMALL)
            
        # Set columns with better widths to fit the table
        self.list_view.InsertColumn(0, 'Thumbnail', width=120)
        self.list_view.InsertColumn(1, 'Title', width=300)
        self.list_view.InsertColumn(2, 'Duration', width=80)
        self.list_view.InsertColumn(3, 'Status', width=150)
        vbox.Add(self.list_view, 1, wx.EXPAND | wx.ALL, 10)
        
        # Bind list item events
        self.list_view.Bind(wx.EVT_LEFT_DOWN, self.on_list_click)

        # Download and clear list buttons
        hbox_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.clear_button = wx.Button(panel, label='Clear List')
        self.clear_button.Bind(wx.EVT_BUTTON, self.on_clear_list)
        hbox_buttons.Add(self.clear_button, 0, wx.EXPAND | wx.RIGHT, 10)

        # Update YT-DLP button
        self.update_button = wx.Button(panel, label='Update yt-dlp')
        self.update_button.Bind(wx.EVT_BUTTON, self.on_update_ytdlp)
        hbox_buttons.Add(self.update_button, 0, wx.EXPAND | wx.RIGHT, 10)
        
        # Add cancel button
        self.cancel_button = wx.Button(panel, label='Cancel Downloads')
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel_downloads)
        self.cancel_button.Disable()  # Disabled by default
        hbox_buttons.Add(self.cancel_button, 0, wx.EXPAND)

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
            # Clear the videos list first
            self.videos.clear()
            # Clear the list view items
            self.list_view.DeleteAllItems()
            # Reset the image list except for icons
            if hasattr(self, 'image_list'):
                # Create a new image list
                new_image_list = wx.ImageList(90, 50)
                # Add default images
                default_bitmap = wx.Bitmap(90, 50)
                self.default_thumbnail_idx = new_image_list.Add(default_bitmap)
                
                # Set the new image list
                self.list_view.SetImageList(new_image_list, wx.IMAGE_LIST_SMALL)
                self.image_list = new_image_list
            self.SetStatusText("Download queue cleared")

    def on_list_click(self, event):
        """Handle clicks on the list items"""
        event.Skip()  # Allow default processing
        # Get mouse position
        point = event.GetPosition()
        item, flags = self.list_view.HitTest(point)
        
        if item != -1:  # If an item was clicked
            # Get the column width to determine which column was clicked
            col_widths = [self.list_view.GetColumnWidth(i) for i in range(self.list_view.GetColumnCount())]
            total_width = sum(col_widths[:4])  # Width up to Status column
            
            x_pos = point.x
        
        event.Skip()  # Allow default processing



    def on_update_ytdlp(self, event):
        """Download or update yt-dlp executable"""
        try:
            self.SetStatusText("Updating yt-dlp...")
            wx.MessageBox("Updating yt-dlp. Press OK and wait...", "Update", wx.ICON_INFORMATION)
            
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
        self.cancel_button.Enable()  # Enable cancel button when downloading
        self.download_threads = []
        self.cancel_requested = False  # Flag to track if cancel was requested
        
        for index, video_info in enumerate(self.videos):
            thread = threading.Thread(target=self._download_video, args=(index, video_info.url), daemon=True)
            thread.start()
            self.download_threads.append(thread)
            
        # Start a thread to monitor download completion
        threading.Thread(target=self._monitor_downloads, daemon=True).start()

    def on_download_progress(self, event):
        """Handle download progress event"""
        # Create or update progress gauge
        if not hasattr(self.list_view, f'gauge_{event.index}'):
            # Calculate position for the gauge
            item_rect = self.list_view.GetItemRect(event.index)
            
            # Calculate the x position by getting the sum of column widths before the Status column
            x_pos = 0
            for col in range(3):  # Sum widths of columns 0, 1, and 2
                x_pos += self.list_view.GetColumnWidth(col)
            
            # Create and position the gauge - make it narrower to leave room for text
            gauge = wx.Gauge(self.list_view, -1, 100, size=(80, 15))
            # Position gauge higher in the cell to leave room for text below
            gauge.SetPosition((x_pos + 2, item_rect.y + 1))
            setattr(self.list_view, f'gauge_{event.index}', gauge)
        
        # Update progress
        gauge = getattr(self.list_view, f'gauge_{event.index}')
        try:
            # Extract numeric value from progress string
            progress_str = event.progress.strip()
            if progress_str.endswith('%'):
                progress_str = progress_str[:-1]  # Remove % symbol
            progress_value = float(progress_str)  # Convert to float first
            gauge.SetValue(int(progress_value))  # Convert to int for gauge
            # Set the percentage text to appear below the gauge with proper spacing
            self.list_view.SetItem(event.index, 3, f"\n   {event.progress}")
        except (ValueError, AttributeError):
            # Handle any parsing errors gracefully
            pass
        self.list_view.SetItem(event.index, 3, event.progress)
    
    def on_download_complete(self, event):
        """Handle download complete event"""
        if event.success:
            # Remove gauge when download is complete
            if hasattr(self.list_view, f'gauge_{event.index}'):
                gauge = getattr(self.list_view, f'gauge_{event.index}')
                gauge.Destroy()
                delattr(self.list_view, f'gauge_{event.index}')
            self.list_view.SetItem(event.index, 3, "Downloaded")
            self._set_row_color(event.index, wx.Colour(200, 255, 200))  # Light green
        else:
            # Remove gauge on failure
            if hasattr(self.list_view, f'gauge_{event.index}'):
                gauge = getattr(self.list_view, f'gauge_{event.index}')
                gauge.Destroy()
                delattr(self.list_view, f'gauge_{event.index}')
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
            
    def _update_thumbnail(self, index: int, thumbnail_path: str):
        """Update the thumbnail for a list item"""
        try:
            # Load and resize the thumbnail image
            img = wx.Image(thumbnail_path)
            if img.IsOk():
                # Add the thumbnail to the image list
                bitmap = img.Scale(90, 50, wx.IMAGE_QUALITY_HIGH).ConvertToBitmap()
                img_idx = self.image_list.Add(bitmap)
                # Update the list item's image
                self.list_view.SetItemImage(index, img_idx)
        except Exception as e:
            logger.error(f"Error updating thumbnail: {e}")
            
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

    def _add_video_to_list(self, video_info):
        """Add a video to the list view and start metadata fetching"""
        self.videos.append(video_info)
        index = self.list_view.InsertItem(self.list_view.GetItemCount(), "", self.default_thumbnail_idx)
        self.list_view.SetItem(index, 1, "Fetching metadata...")
    
        thread = threading.Thread(target=self._fetch_metadata, args=(index, video_info.url), daemon=True)
        thread.start()
        self.metadata_threads.append(thread)

    def on_cancel_downloads(self, event):
        """Cancel all active downloads"""
        if not self.downloading:
            return
            
        self.cancel_requested = True
        self.SetStatusText("Cancelling downloads...")
        
        # Terminate all active processes
        for video in self.videos:
            if hasattr(video, 'process') and video.process:
                try:
                    video.process.terminate()
                except:
                    pass
                    
        # Wait for all download threads to complete
        for thread in self.download_threads:
            thread.join()

        # Wait for metadata threads to complete
        for thread in self.metadata_threads:
            thread.join(timeout=1.0)  # Wait with timeout to prevent hanging
        self.metadata_threads.clear()
            
        self.downloading = False
        self.download_button.Enable()
        self.clear_button.Enable()
        self.cancel_button.Disable()
        self.cancel_requested = False  # Reset cancel flag
        self.SetStatusText("Downloads cancelled")

    def _fetch_metadata(self, index: int, link: str):
        """Fetch video metadata using yt-dlp"""
        try:
            if self.cancel_requested:
                return

            wx.CallAfter(self.SetStatusText, f"Fetching metadata for video {index+1}...")
            info_dict, error = fetch_video_metadata(link)
            
            if error or self.cancel_requested:
                logger.error(f"Failed to get metadata: {error if error else 'Cancelled'}")
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
            
            # Store process reference for cancellation
            self.videos[index].process = process
            
            # Monitor stdout for progress updates
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                
                # Check if cancellation was requested
                if self.cancel_requested:
                    process.terminate()
                    wx.PostEvent(self, DownloadCompleteEvent(index=index, success=False))
                    wx.CallAfter(self.list_view.SetItem, index, 3, "Cancelled")
                    return
                    
                line = line.strip()
                # Look for percentage in the output
                if '%' in line:
                    # Try to extract percentage value
                    match = re.search(r'([0-9.]+)%', line)
                    if match:
                        progress = match.group(1) + '%'
                        wx.PostEvent(self, DownloadProgressEvent(index=index, progress=progress))
            
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

    def on_cancel_downloads(self, event):
        """Cancel all active downloads"""
        if not self.downloading:
            return
            
        self.cancel_requested = True
        self.SetStatusText("Cancelling downloads...")
        
        # Terminate all active processes
        for video in self.videos:
            if hasattr(video, 'process') and video.process:
                try:
                    video.process.terminate()
                except:
                    pass
                    
        # Wait for all threads to complete
        for thread in self.download_threads:
            thread.join()
            
        self.downloading = False
        self.download_button.Enable()
        self.clear_button.Enable()
        self.cancel_button.Disable()
        self.SetStatusText("Downloads cancelled")
        
    def _monitor_downloads(self):
        """Monitor download threads and re-enable buttons when all complete"""
        for thread in self.download_threads:
            thread.join()
            
        wx.CallAfter(self._on_downloads_complete)
        
    def _set_row_color(self, index: int, color: wx.Colour):
        """Set the background color for a row in the list view"""
        try:
            item = self.list_view.GetItem(index)
            item.SetBackgroundColour(color)
            self.list_view.SetItem(item)
        except Exception as e:
            logger.error(f"Error setting row color: {e}")
            
    def check_ytdlp(self):
        """Check if yt-dlp exists and is up to date"""
        try:
            if not check_ytdlp_exists():
                self.SetStatusText("yt-dlp not found. Downloading...")
                if update_ytdlp():
                    self.SetStatusText("yt-dlp downloaded successfully")
                else:
                    self.SetStatusText("Failed to download yt-dlp")
                    return
            
            current_version = get_ytdlp_version()
            latest_version = get_latest_ytdlp_version()
            
            if current_version and latest_version:
                if current_version == latest_version:
                    self.SetStatusText(f"yt-dlp is up to date (version {current_version})")
                    self.update_button.Disable()
                    logger.info(f"yt-dlp is up to date (version {current_version})")
                else:
                    self.SetStatusText(f"yt-dlp update available: {current_version} → {latest_version}")
                    self.update_button.Enable()
                    logger.info(f"yt-dlp update available: {current_version} → {latest_version}")
            else:
                self.SetStatusText("Failed to get yt-dlp version")
                self.update_button.Enable()  # Enable button to allow retry
                
        except Exception as e:
            logger.error(f"Error checking yt-dlp: {e}")
            self.SetStatusText(f"Error checking yt-dlp: {e}")
            self.update_button.Enable()  # Enable button to allow retry
    def _on_downloads_complete(self):
        """Handle completion of all downloads"""
        self.downloading = False
        self.download_button.Enable()
        self.clear_button.Enable()
        self.cancel_button.Disable()  # Disable cancel button when done
        self.cancel_requested = False  # Reset cancel flag
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
        
        self.SetStatusText(message)
        wx.MessageBox(message, "Downloads Complete", wx.ICON_INFORMATION)