"""
Application settings and constants
"""

import os

# Base paths
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESOURCES_DIR = os.path.join(APP_ROOT, "resources")

# Binary files
BIN_DIR = os.path.join(RESOURCES_DIR, "bin")
YTDLP_EXE = os.path.join(BIN_DIR, "yt-dlp.exe")
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

# Icons and images
ICONS_DIR = os.path.join(RESOURCES_DIR, "icons")
BANNER_IMG = os.path.join(ICONS_DIR, "banner.png")
ICON_IMG = os.path.join(ICONS_DIR, "app_icon.ico")
DELETE_ICON = os.path.join(ICONS_DIR, "delete.png")

# Temporary directory for thumbnails
THUMBNAIL_DIR = os.path.join(APP_ROOT, "tmp")

# Ensure directories exist
os.makedirs(THUMBNAIL_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

# Default options
DEFAULT_QUALITY = "Best"
DEFAULT_PLAYLIST_OPTION = "Download All"

# URL patterns for supported platforms
URL_PATTERNS = {
    'youtube': r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})',
    'vimeo': r'vimeo\.com\/(\d+)',
    'facebook': r'facebook\.com\/.*\/videos\/(\d+)',
    'twitter': r'twitter\.com\/.*\/status\/(\d+)',
    'instagram': r'instagram\.com\/p\/([a-zA-Z0-9_-]+)'
}

# Quality options
QUALITY_CHOICES = ["Best", "1080p", "720p", "480p", "360p"]