import asyncio
import os
import re
import json
from typing import Union
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch
from AviaxMusic.utils.database import is_on_off
from AviaxMusic.utils.formatters import time_to_seconds
import random
import aiohttp
import concurrent.futures
from functools import lru_cache, partial
import tempfile
import shutil

# Global thread pool for CPU-bound operations
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

@lru_cache(maxsize=32)
def cookie_txt_file():
    cookie_dir = f"{os.getcwd()}/cookies"
    if not os.path.exists(cookie_dir):
        return None
    cookies_files = [f for f in os.listdir(cookie_dir) if f.endswith(".txt")]
    if not cookies_files:
        return None
    cookie_file = os.path.join(cookie_dir, random.choice(cookies_files))
    return cookie_file

async def download_song(link: str):
    video_id = link.split('v=')[-1].split('&')[0]
    download_folder = "downloads"
    file_path = f"{download_folder}/{video_id}.mp3"
    
    # Fast file existence check
    if os.path.exists(file_path):
        return file_path
    
    cookie_file = cookie_txt_file()
    if not cookie_file:
        return None
        
    # Use temp file for faster writing
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, f"{video_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': temp_file,
        'quiet': True,
        'cookiefile': cookie_file,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    try:
        # Run in thread pool for non-blocking execution
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(thread_pool, partial(yt_dlp.YoutubeDL(ydl_opts).download, [link]))
        
        # Move to final location
        for ext in ["mp3", "m4a", "webm"]:
            temp_file_path = os.path.join(temp_dir, f"{video_id}.{ext}")
            if os.path.exists(temp_file_path):
                os.makedirs(download_folder, exist_ok=True)
                final_path = os.path.join(download_folder, f"{video_id}.{ext}")
                shutil.move(temp_file_path, final_path)
                shutil.rmtree(temp_dir)
                return final_path
        return None
    except Exception as e:
        print(f"Error downloading song: {e}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return None

async def download_video(link: str):
    video_id = link.split('v=')[-1].split('&')[0]
    download_folder = "downloads"
    
    # Fast file existence check with most common format first
    for ext in ["mp4", "webm", "mkv"]:
        file_path = f"{download_folder}/{video_id}.{ext}"
        if os.path.exists(file_path):
            return file_path
    
    cookie_file = cookie_txt_file()
    if not cookie_file:
        return None
        
    # Use temp directory for faster operations
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, f"{video_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'best[height<=720][ext=mp4]/best[height<=480][ext=mp4]',
        'outtmpl': temp_file,
        'quiet': True,
        'cookiefile': cookie_file,
        'no_warnings': True,
    }
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(thread_pool, partial(yt_dlp.YoutubeDL(ydl_opts).download, [link]))
        
        # Find and move the downloaded file
        for ext in ["mp4", "webm", "mkv"]:
            temp_file_path = os.path.join(temp_dir, f"{video_id}.{ext}")
            if os.path.exists(temp_file_path):
                os.makedirs(download_folder, exist_ok=True)
                final_path = os.path.join(download_folder, f"{video_id}.{ext}")
                shutil.move(temp_file_path, final_path)
                shutil.rmtree(temp_dir)
                return final_path
        return None
    except Exception as e:
        print(f"Error downloading video: {e}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return None

async def check_file_size(link):
    cookie_file = cookie_txt_file()
    if not cookie_file:
        return None
        
    # Fast JSON extraction using yt-dlp directly
    try:
        ydl_opts = {
            'quiet': True,
            'cookiefile': cookie_file,
            'no_warnings': True,
        }
        
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            thread_pool, 
            partial(yt_dlp.YoutubeDL(ydl_opts).extract_info, link, download=False)
        )
        
        if not info or 'formats' not in info:
            return None
            
        total_size = 0
        for fmt in info['formats']:
            if fmt.get('filesize'):
                total_size += fmt['filesize']
            elif fmt.get('tbr'):  # Estimate from bitrate if filesize not available
                duration = info.get('duration', 300)  # Default 5 minutes
                total_size += (fmt['tbr'] * 1000 * duration) / 8  # Convert kbps to bytes
        
        return total_size if total_size > 0 else None
    except Exception as e:
        print(f"Error checking file size: {e}")
        return None

async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    return out.decode("utf-8") if out else errorz.decode("utf-8")

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self._search_cache = {}
        self._cache_time = {}

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset:entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    @lru_cache(maxsize=100)
    async def _cached_search(self, link: str):
        results = VideosSearch(link, limit=1)
        return await results.next()

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        result = (await self._cached_search(link))["result"][0]
        title = result["title"]
        duration_min = result["duration"]
        thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        vidid = result["id"]
        duration_sec = 0 if str(duration_min) == "None" else int(time_to_seconds(duration_min))
        
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = (await self._cached_search(link))["result"][0]
        return result["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = (await self._cached_search(link))["result"][0]
        return result["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = (await self._cached_search(link))["result"][0]
        return result["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = cookie_txt_file()
        if not cookie_file:
            return 0, "No cookies found."
            
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies", cookie_file,
            "-g",
            "-f", "best[height<=?720][width<=?1280]",
            link,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = cookie_txt_file()
        if not cookie_file:
            return []
            
        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --cookies {cookie_file} --playlist-end {limit} --skip-download {link}"
        )
        return [line for line in playlist.split("\n") if line]

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        result = (await self._cached_search(link))["result"][0]
        return {
            "title": result["title"],
            "link": result["link"],
            "vidid": result["id"],
            "duration_min": result["duration"],
            "thumb": result["thumbnails"][0]["url"].split("?")[0],
        }, result["id"]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = cookie_txt_file()
        if not cookie_file:
            return [], link
            
        ytdl_opts = {"quiet": True, "cookiefile": cookie_file}
        
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                thread_pool, 
                partial(yt_dlp.YoutubeDL(ytdl_opts).extract_info, link, download=False)
            )
            
            formats_available = []
            for format in r["formats"]:
                if "dash" not in str(format.get("format", "")).lower():
                    try:
                        formats_available.append({
                            "format": format.get("format", ""),
                            "filesize": format.get("filesize", 0),
                            "format_id": format.get("format_id", ""),
                            "ext": format.get("ext", ""),
                            "format_note": format.get("format_note", ""),
                            "yturl": link,
                        })
                    except:
                        continue
            return formats_available, link
        except Exception:
            return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        result = (await VideosSearch(link, limit=10).next())["result"][query_type]
        return (
            result["title"],
            result["duration"],
            result["thumbnails"][0]["url"].split("?")[0],
            result["id"]
        )

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        
        loop = asyncio.get_event_loop()
        
        def _audio_dl():
            cookie_file = cookie_txt_file()
            if not cookie_file:
                raise Exception("No cookies found.")
                
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "quiet": True,
                "cookiefile": cookie_file,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                file_path = f"downloads/{info['id']}.{info['ext']}"
                if not os.path.exists(file_path):
                    ydl.download([link])
                return file_path

        def _video_dl():
            cookie_file = cookie_txt_file()
            if not cookie_file:
                raise Exception("No cookies found.")
                
            ydl_opts = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "quiet": True,
                "cookiefile": cookie_file,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                file_path = f"downloads/{info['id']}.{info['ext']}"
                if not os.path.exists(file_path):
                    ydl.download([link])
                return file_path

        if songvideo or songaudio:
            # Use the optimized download functions
            if songvideo:
                downloaded_file = await download_video(link)
            else:
                downloaded_file = await download_song(link)
            return downloaded_file, True
        elif video:
            cookie_file = cookie_txt_file()
            if not cookie_file:
                return None, None
                
            if await is_on_off(1):
                downloaded_file = await loop.run_in_executor(thread_pool, _video_dl)
                return downloaded_file, True
            else:
                proc = await asyncio.create_subprocess_exec(
                    "yt-dlp",
                    "--cookies", cookie_file,
                    "-g",
                    "-f", "best[height<=?720][width<=?1280]",
                    link,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    return stdout.decode().split("\n")[0], False
                else:
                    file_size = await check_file_size(link)
                    if not file_size or (file_size / (1024 * 1024)) > 250:
                        return None, None
                    downloaded_file = await loop.run_in_executor(thread_pool, _video_dl)
                    return downloaded_file, True
        else:
            downloaded_file = await loop.run_in_executor(thread_pool, _audio_dl)
            return downloaded_file, True
