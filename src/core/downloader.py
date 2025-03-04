"""
Video download functionality
"""

import os
import re
import json
import logging
import subprocess
import urllib.request
from typing import List, Dict, Tuple, Optional, Any

from src.config.settings import YTDLP_EXE, YTDLP_URL
from src.core.video import VideoInfo

logger = logging.getLogger('VideoDownloader.Downloader')

def check_ytdlp_exists() -> bool:
    """Check if yt-dlp exists"""
    return os.path.exists(YTDLP_EXE)

def get_ytdlp_version() -> Optional[str]:
    """Get the current version of yt-dlp"""
    try:
        if not check_ytdlp_exists():
            return None
            
        result = subprocess.run(f'"{YTDLP_EXE}" --version', shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Error checking yt-dlp version: {e}")
        return None

def get_latest_ytdlp_version() -> Optional[str]:
    """Get the latest version of yt-dlp available"""
    try:
        with urllib.request.urlopen("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest") as response:
            release_info = json.loads(response.read().decode())
            return release_info["tag_name"]
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return None

def update_ytdlp() -> bool:
    """Download or update yt-dlp executable"""
    try:
        # Ensure the bin directory exists
        bin_dir = os.path.dirname(YTDLP_EXE)
        if not os.path.exists(bin_dir):
            os.makedirs(bin_dir)
            
        # Download the latest version
        urllib.request.urlretrieve(YTDLP_URL, YTDLP_EXE)
        
        # Set execute permission on Linux/macOS
        if os.name != 'nt':
            os.chmod(YTDLP_EXE, 0o755)
            
        return True
    except Exception as e:
        logger.error(f"Failed to update yt-dlp: {e}")
        return False

def fetch_video_metadata(video_url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Fetch video metadata using yt-dlp"""
    try:
        command = f'"{YTDLP_EXE}" --dump-json {video_url}'
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            return json.loads(result.stdout), None
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return None, error_msg
    except Exception as e:
        logger.error(f"Error fetching metadata: {e}")
        return None, str(e)

def fetch_playlist_videos(playlist_url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch list of videos in a playlist"""
    try:
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
            return videos, None
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return [], error_msg
    except Exception as e:
        logger.error(f"Error fetching playlist: {e}")
        return [], str(e)

def build_download_command(video_link: str, output_path: str, 
                          audio_only: bool = False, quality: str = "Best") -> str:
    """Build the yt-dlp command based on selected options"""
    if audio_only:
        return (f'"{YTDLP_EXE}" -x --audio-format mp3 --audio-quality 0 '
                f'--progress-template "%(progress._percent_str)s" '
                f'--output "{output_path}" {video_link}')
    else:
        # Set format based on quality
        if quality == "Best":
            format_spec = "bestvideo+bestaudio[ext=m4a]/best"
        elif quality == "1080p":
            format_spec = "bestvideo[height<=1080]+bestaudio[ext=m4a]/best[height<=1080]"
        elif quality == "720p":
            format_spec = "bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]"
        elif quality == "480p":
            format_spec = "bestvideo[height<=480]+bestaudio[ext=m4a]/best[height<=480]"
        elif quality == "360p":
            format_spec = "bestvideo[height<=360]+bestaudio[ext=m4a]/best[height<=360]"
        else:
            format_spec = "bestvideo+bestaudio[ext=m4a]/best"
        
        return (f'"{YTDLP_EXE}" -f {format_spec} --merge-output-format mp4 '
                f'--progress-template "%(progress._percent_str)s" '
                f'--output "{output_path}" {video_link}')