"""
Video information class and related operations
"""

import re
import os
import logging
import urllib.request
import ssl
from PIL import Image
from typing import Optional

from src.config.settings import URL_PATTERNS, THUMBNAIL_DIR

logger = logging.getLogger('VideoDownloader.Video')

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

def is_valid_link(link: str) -> bool:
    """Check if a URL is valid"""
    # Improved URL validation to support more platforms
    return re.match(r'^https?://(www\.)?(youtube|youtu\.be|vimeo|dailymotion|facebook|twitter|instagram).*', link) is not None

def is_playlist(url: str) -> bool:
    """Check if URL is a playlist"""
    return "playlist" in url or "list=" in url

def extract_video_id(link: str) -> str:
    """Extract video ID from URL"""
    for platform, pattern in URL_PATTERNS.items():
        match = re.search(pattern, link)
        if match:
            return match.group(1)
            
    # Default to full link
    return link

def format_duration(seconds: int) -> str:
    """Format duration in seconds to a readable string"""
    if not seconds:
        return "Unknown"
        
    if seconds > 3600:  # More than an hour
        return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
    else:
        return f"{seconds // 60}:{seconds % 60:02d}"

def download_thumbnail(thumbnail_url: str, video_id: str) -> Optional[str]:
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