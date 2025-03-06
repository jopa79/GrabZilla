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

def build_download_command(video_link: str, output_path: str, 
    audio_only: bool = False, quality: str = "Best") -> str:
    """Build the yt-dlp command based on selected options"""
    # Add quality suffix to output path
    base, ext = os.path.splitext(output_path)
    if audio_only:
        # Use .mp3 extension for audio files without adding suffix
        output_path = f"{base}.mp3"
        return (f'"{YTDLP_EXE}" -x --audio-format mp3 --audio-quality 0 '
                f'--progress-template "%(progress._percent_str)s" '
                f'--rm-cache-dir --keep-video false --remux-video mp3 --postprocessor-args "-y" '
                f'--output "{output_path}" {video_link}')
    else:
        # Set format based on quality and include actual resolution in filename
        output_template = f"{base}_%(height)sp{ext}"
        if quality == "Best":
            return (f'"{YTDLP_EXE}" -f "bv*+ba/b" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')
        elif quality == "2160p":
            return (f'"{YTDLP_EXE}" -f "bv*+ba/b" -S "res:2160" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')
        elif quality == "1440p":
            return (f'"{YTDLP_EXE}" -f "bv*+ba/b" -S "res:1440" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')
        elif quality == "1080p":
            return (f'"{YTDLP_EXE}" -f "bv*+ba/b" -S "res:1080" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')
        elif quality == "720p":
            return (f'"{YTDLP_EXE}" -f "bv*+ba/b" -S "res:720" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')
        elif quality == "480p":
            return (f'"{YTDLP_EXE}" -f "bv*+ba/b" -S "res:480" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')
        elif quality == "360p":
            return (f'"{YTDLP_EXE}" -f "bv*+ba/b" -S "res:360" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')
        else:
            return (f'"{YTDLP_EXE}" -f "bestvideo+bestaudio[ext=m4a]/best" --merge-output-format mp4 '
                    f'--progress-template "%(progress._percent_str)s" '
                    f'--output "{output_template}" {video_link}')