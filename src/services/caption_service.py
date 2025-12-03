# src/services/caption_service.py
"""
Caption Service
Business logic for caption/subtitle operations including fetching, parsing, and search
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import re
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.base_service import BaseService
from src.services.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ValidationError,
    ExternalServiceError,
    ProcessingError,
)

from src.infrastructure.repositories.caption_repository import (
    CaptionRepository,
    CaptionSegmentRepository,
)
from src.infrastructure.repositories.video_repository import VideoRepository
from src.app.models import Caption, CaptionSegment, CaptionType, Video

logger = logging.getLogger(__name__)


class CaptionService(BaseService):
    """
    Caption operations service

    Handles:
    - Caption fetching from YouTube (API or yt-dlp)
    - Caption parsing and storage
    - Caption search functionality
    - Segment-based navigation
    """

    def __init__(
        self,
        caption_repo: CaptionRepository,
        segment_repo: CaptionSegmentRepository,
        video_repo: VideoRepository,
        youtube_client=None,
        cache=None,
        config=None,
    ):
        super().__init__(cache=cache, config=config)
        self.caption_repo = caption_repo
        self.segment_repo = segment_repo
        self.video_repo = video_repo
        self.youtube = youtube_client

    def get_service_name(self) -> str:
        return "caption"

    # ========================================================================
    # Caption CRUD Operations
    # ========================================================================

    async def get_caption(
        self,
        db: AsyncSession,
        video_id: str,
        language_code: str,
    ) -> Dict[str, Any]:
        """
        Get caption for a video in specific language

        Args:
            db: Database session
            video_id: YouTube video ID
            language_code: Language code (e.g., 'en', 'zh-TW')

        Returns:
            Caption data with content

        Raises:
            ResourceNotFoundError: Caption not found
        """
        self.validate_required(video_id, "video_id")
        self.validate_required(language_code, "language_code")

        # Check cache
        cache_key = self.get_cache_key("caption", video_id, language_code)
        cached = self.get_from_cache(cache_key)
        if cached:
            return cached

        caption = await self.caption_repo.get_by_video_and_language(
            video_id, language_code
        )

        if not caption:
            raise ResourceNotFoundError(
                "Caption", f"{video_id}:{language_code}"
            )

        result = self._caption_to_dict(caption)

        # Cache for 1 hour
        self.set_in_cache(cache_key, result, ttl_seconds=3600)

        return result

    async def get_video_captions(
        self,
        db: AsyncSession,
        video_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all available captions for a video

        Args:
            db: Database session
            video_id: YouTube video ID

        Returns:
            List of caption metadata (without full content)
        """
        self.validate_required(video_id, "video_id")

        # Verify video exists
        video = await self.video_repo.get_by_id(video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        captions = await self.caption_repo.get_by_video_id(video_id)

        return [
            {
                "id": cap.id,
                "language_code": cap.language_code,
                "language_name": cap.language_name,
                "caption_type": cap.caption_type,
                "word_count": cap.word_count,
                "segment_count": cap.segment_count,
                "duration_seconds": cap.duration_seconds,
                "is_processed": cap.is_processed,
                "fetched_at": cap.fetched_at.isoformat() if cap.fetched_at else None,
            }
            for cap in captions
        ]

    async def get_available_languages(
        self,
        db: AsyncSession,
        video_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get list of available caption languages for a video

        Args:
            db: Database session
            video_id: YouTube video ID

        Returns:
            List of language info dicts
        """
        self.validate_required(video_id, "video_id")

        return await self.caption_repo.get_available_languages(video_id)

    async def delete_video_captions(
        self,
        db: AsyncSession,
        video_id: str,
    ) -> Dict[str, Any]:
        """
        Delete all captions for a video

        Args:
            db: Database session
            video_id: YouTube video ID

        Returns:
            Deletion confirmation
        """
        self.validate_required(video_id, "video_id")

        # Delete segments first
        segments_deleted = await self.segment_repo.delete_by_video_id(video_id)

        # Delete captions
        captions_deleted = await self.caption_repo.delete_by_video(video_id)

        # Update video has_transcript flag
        await self.video_repo.update(video_id, has_transcript=False)
        await db.commit()

        # Invalidate cache
        self._invalidate_video_caption_cache(video_id)

        return {
            "success": True,
            "video_id": video_id,
            "captions_deleted": captions_deleted,
            "segments_deleted": segments_deleted,
        }

    # ========================================================================
    # Caption Fetching
    # ========================================================================

    async def fetch_captions(
        self,
        db: AsyncSession,
        video_id: str,
        languages: Optional[List[str]] = None,
        include_auto: bool = True,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch and store captions for a video

        Args:
            db: Database session
            video_id: YouTube video ID
            languages: Specific languages to fetch (None = all available)
            include_auto: Include auto-generated captions
            force_refresh: Re-fetch even if exists

        Returns:
            Fetch operation results
        """
        self.log_info(f"Fetching captions for video: {video_id}")
        self.validate_required(video_id, "video_id")

        # Verify video exists
        video = await self.video_repo.get_by_id(video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        results = {
            "video_id": video_id,
            "success": [],
            "failed": [],
            "skipped": [],
        }

        try:
            # Fetch caption tracks from YouTube
            caption_tracks = await self._fetch_caption_tracks(video_id)

            if not caption_tracks:
                self.log_info(f"No captions available for video: {video_id}")
                return {
                    **results,
                    "message": "No captions available for this video",
                }

            for track in caption_tracks:
                lang_code = track.get("language_code")
                caption_type = track.get("caption_type", CaptionType.AUTO.value)

                # Skip auto-generated if not wanted
                if not include_auto and caption_type == CaptionType.AUTO.value:
                    results["skipped"].append({
                        "language_code": lang_code,
                        "reason": "auto-generated excluded",
                    })
                    continue

                # Skip if language not in requested list
                if languages and lang_code not in languages:
                    continue

                # Check if already exists
                existing = await self.caption_repo.get_by_video_and_language(
                    video_id, lang_code
                )
                if existing and not force_refresh:
                    results["skipped"].append({
                        "language_code": lang_code,
                        "reason": "already exists",
                    })
                    continue

                try:
                    # Fetch caption content
                    caption_data = await self._fetch_caption_content(
                        video_id, track
                    )

                    if existing:
                        # Update existing
                        await self.caption_repo.update(
                            existing.id, **caption_data
                        )
                    else:
                        # Create new
                        caption_data["video_id"] = video_id
                        await self.caption_repo.create(**caption_data)

                    results["success"].append(lang_code)

                except Exception as e:
                    self.log_error(
                        f"Failed to fetch caption {lang_code} for {video_id}",
                        error=e,
                    )
                    results["failed"].append({
                        "language_code": lang_code,
                        "error": str(e),
                    })

            # Update video has_transcript flag if any captions fetched
            if results["success"]:
                await self.video_repo.update(
                    video_id,
                    has_transcript=True,
                    transcript_language=results["success"][0],
                )

            await db.commit()

            # Invalidate cache
            self._invalidate_video_caption_cache(video_id)

            self.log_info(
                f"Caption fetch complete for {video_id}: "
                f"{len(results['success'])} success, "
                f"{len(results['failed'])} failed, "
                f"{len(results['skipped'])} skipped"
            )

            return results

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "fetch_captions", {"video_id": video_id})

    async def _fetch_caption_tracks(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Fetch available caption tracks from YouTube

        This method tries multiple approaches:
        1. YouTube Data API (if client available)
        2. yt-dlp subtitle extraction
        """
        tracks = []

        # Try YouTube API first
        if self.youtube:
            try:
                api_tracks = self.youtube.get_caption_tracks(video_id)
                if api_tracks:
                    return api_tracks
            except Exception as e:
                self.log_warning(f"YouTube API caption fetch failed: {e}")

        # Fallback to yt-dlp
        try:
            tracks = await self._fetch_tracks_via_ytdlp(video_id)
        except Exception as e:
            self.log_error(f"yt-dlp caption track fetch failed: {e}")
            raise ExternalServiceError("yt-dlp", f"Failed to fetch caption tracks: {e}")

        return tracks

    async def _fetch_tracks_via_ytdlp(self, video_id: str) -> List[Dict[str, Any]]:
        """Fetch caption tracks using yt-dlp"""
        import subprocess
        import json

        try:
            # Get subtitle info without downloading
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--list-subs",
                "--print-json",
                f"https://www.youtube.com/watch?v={video_id}",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                self.log_warning(f"yt-dlp failed: {result.stderr}")
                return []

            # Parse JSON output
            data = json.loads(result.stdout)
            tracks = []

            # Process manual subtitles
            for lang_code, subs in data.get("subtitles", {}).items():
                if subs:
                    tracks.append({
                        "language_code": lang_code,
                        "language_name": self._get_language_name(lang_code),
                        "caption_type": CaptionType.MANUAL.value,
                        "formats": [s.get("ext", "vtt") for s in subs],
                    })

            # Process auto-generated subtitles
            for lang_code, subs in data.get("automatic_captions", {}).items():
                if subs:
                    tracks.append({
                        "language_code": lang_code,
                        "language_name": self._get_language_name(lang_code),
                        "caption_type": CaptionType.AUTO.value,
                        "formats": [s.get("ext", "vtt") for s in subs],
                    })

            return tracks

        except subprocess.TimeoutExpired:
            self.log_error("yt-dlp timed out")
            return []
        except json.JSONDecodeError as e:
            self.log_error(f"Failed to parse yt-dlp output: {e}")
            return []
        except FileNotFoundError:
            self.log_error("yt-dlp not found in PATH")
            raise ExternalServiceError("yt-dlp", "yt-dlp is not installed")

    async def _fetch_caption_content(
        self,
        video_id: str,
        track: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Fetch actual caption content for a track

        Args:
            video_id: YouTube video ID
            track: Track info dict

        Returns:
            Caption data dict ready for storage
        """
        import subprocess
        import tempfile
        import os

        lang_code = track["language_code"]
        caption_type = track.get("caption_type", CaptionType.AUTO.value)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "caption")

                # Download subtitle
                cmd = [
                    "yt-dlp",
                    "--skip-download",
                    "--write-sub" if caption_type == CaptionType.MANUAL.value else "--write-auto-sub",
                    "--sub-lang", lang_code,
                    "--sub-format", "json3",
                    "--convert-subs", "json3",
                    "-o", output_path,
                    f"https://www.youtube.com/watch?v={video_id}",
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.returncode != 0:
                    raise ProcessingError(
                        f"yt-dlp subtitle download failed: {result.stderr}"
                    )

                # Find and parse the downloaded file
                subtitle_file = None
                for f in os.listdir(tmpdir):
                    if f.endswith(".json3") or f.endswith(".json"):
                        subtitle_file = os.path.join(tmpdir, f)
                        break

                if not subtitle_file:
                    # Try VTT format as fallback
                    return await self._fetch_caption_vtt(video_id, track, tmpdir)

                # Parse JSON3 format
                return self._parse_json3_caption(
                    subtitle_file, video_id, lang_code, track
                )

        except subprocess.TimeoutExpired:
            raise ProcessingError("Caption download timed out")
        except Exception as e:
            self.log_error(f"Caption content fetch failed: {e}")
            raise

    async def _fetch_caption_vtt(
        self,
        video_id: str,
        track: Dict[str, Any],
        tmpdir: str,
    ) -> Dict[str, Any]:
        """Fallback to VTT format"""
        import subprocess
        import os

        lang_code = track["language_code"]
        caption_type = track.get("caption_type", CaptionType.AUTO.value)
        output_path = os.path.join(tmpdir, "caption_vtt")

        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-sub" if caption_type == CaptionType.MANUAL.value else "--write-auto-sub",
            "--sub-lang", lang_code,
            "--sub-format", "vtt",
            "-o", output_path,
            f"https://www.youtube.com/watch?v={video_id}",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Find VTT file
        vtt_file = None
        for f in os.listdir(tmpdir):
            if f.endswith(".vtt"):
                vtt_file = os.path.join(tmpdir, f)
                break

        if not vtt_file:
            raise ProcessingError("No subtitle file downloaded")

        return self._parse_vtt_caption(vtt_file, video_id, lang_code, track)

    def _parse_json3_caption(
        self,
        filepath: str,
        video_id: str,
        lang_code: str,
        track: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse YouTube JSON3 caption format"""
        import json

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        segments = []
        full_text_parts = []

        events = data.get("events", [])
        for i, event in enumerate(events):
            if "segs" not in event:
                continue

            start_time = event.get("tStartMs", 0) / 1000.0
            duration = event.get("dDurationMs", 0) / 1000.0
            end_time = start_time + duration

            # Combine segment text
            text_parts = []
            for seg in event.get("segs", []):
                text = seg.get("utf8", "")
                if text and text.strip():
                    text_parts.append(text)

            text = "".join(text_parts).strip()
            if text:
                segments.append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "text": text,
                    "segment_index": i,
                })
                full_text_parts.append(text)

        full_text = " ".join(full_text_parts)
        word_count = len(full_text.split())

        # Generate caption ID
        caption_id = f"{video_id}_{lang_code}"

        return {
            "id": caption_id,
            "language_code": lang_code,
            "language_name": track.get("language_name", self._get_language_name(lang_code)),
            "caption_type": track.get("caption_type", CaptionType.AUTO.value),
            "content": full_text,
            "content_json": segments,
            "word_count": word_count,
            "segment_count": len(segments),
            "duration_seconds": segments[-1]["end_time"] if segments else 0,
            "is_processed": True,
            "fetched_at": datetime.utcnow(),
        }

    def _parse_vtt_caption(
        self,
        filepath: str,
        video_id: str,
        lang_code: str,
        track: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse WebVTT caption format"""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        segments = []
        full_text_parts = []

        # Parse VTT
        pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*\n(.*?)(?=\n\n|\Z)"
        matches = re.findall(pattern, content, re.DOTALL)

        for i, (start, end, text) in enumerate(matches):
            start_sec = self._vtt_time_to_seconds(start)
            end_sec = self._vtt_time_to_seconds(end)

            # Clean text (remove VTT tags)
            text = re.sub(r"<[^>]+>", "", text)
            text = text.strip()

            if text:
                segments.append({
                    "start_time": start_sec,
                    "end_time": end_sec,
                    "duration": end_sec - start_sec,
                    "text": text,
                    "segment_index": i,
                })
                full_text_parts.append(text)

        full_text = " ".join(full_text_parts)
        word_count = len(full_text.split())

        caption_id = f"{video_id}_{lang_code}"

        return {
            "id": caption_id,
            "language_code": lang_code,
            "language_name": track.get("language_name", self._get_language_name(lang_code)),
            "caption_type": track.get("caption_type", CaptionType.AUTO.value),
            "content": full_text,
            "content_json": segments,
            "word_count": word_count,
            "segment_count": len(segments),
            "duration_seconds": segments[-1]["end_time"] if segments else 0,
            "is_processed": True,
            "fetched_at": datetime.utcnow(),
        }

    def _vtt_time_to_seconds(self, time_str: str) -> float:
        """Convert VTT timestamp to seconds"""
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    # ========================================================================
    # Caption Search
    # ========================================================================

    async def search_captions(
        self,
        db: AsyncSession,
        query: str,
        video_ids: Optional[List[str]] = None,
        language_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Search within caption content

        Args:
            db: Database session
            query: Search query text
            video_ids: Optional video ID filter
            language_code: Optional language filter
            page: Page number
            page_size: Results per page

        Returns:
            Tuple of (search results, total count)
        """
        self.validate_required(query, "query")
        self.validate_positive(page, "page")
        self.validate_positive(page_size, "page_size")

        skip, limit = self.calculate_pagination(page, page_size)

        results = await self.caption_repo.search_in_captions(
            query_text=query,
            video_ids=video_ids,
            language_code=language_code,
            skip=skip,
            limit=limit,
        )

        # For total count, we'd need a separate count query
        # For now, estimate based on results
        total = len(results) if len(results) < limit else skip + limit + 1

        return results, total

    async def search_segments(
        self,
        db: AsyncSession,
        query: str,
        video_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Search within caption segments for precise timestamps

        Args:
            db: Database session
            query: Search query text
            video_id: Optional video ID filter
            page: Page number
            page_size: Results per page

        Returns:
            Tuple of (segment results with timestamps, total count)
        """
        self.validate_required(query, "query")

        skip, limit = self.calculate_pagination(page, page_size)

        results = await self.segment_repo.search_segments(
            query_text=query,
            video_id=video_id,
            skip=skip,
            limit=limit,
        )

        total = len(results) if len(results) < limit else skip + limit + 1

        return results, total

    async def get_segment_at_time(
        self,
        db: AsyncSession,
        video_id: str,
        timestamp: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Get caption segment at a specific timestamp

        Args:
            db: Database session
            video_id: YouTube video ID
            timestamp: Time in seconds

        Returns:
            Segment data or None
        """
        self.validate_required(video_id, "video_id")

        segment = await self.segment_repo.get_segment_at_time(video_id, timestamp)

        if segment:
            return segment.to_dict()

        return None

    # ========================================================================
    # Segment Processing
    # ========================================================================

    async def process_caption_segments(
        self,
        db: AsyncSession,
        video_id: str,
        language_code: str,
    ) -> Dict[str, Any]:
        """
        Process caption into searchable segments

        Args:
            db: Database session
            video_id: YouTube video ID
            language_code: Language code

        Returns:
            Processing results
        """
        self.log_info(
            f"Processing segments for {video_id} language {language_code}"
        )

        caption = await self.caption_repo.get_by_video_and_language(
            video_id, language_code
        )

        if not caption:
            raise ResourceNotFoundError(
                "Caption", f"{video_id}:{language_code}"
            )

        if not caption.content_json:
            raise ValidationError(
                f"Caption {caption.id} has no segment data"
            )

        # Delete existing segments
        await self.segment_repo.delete_by_caption_id(caption.id)

        # Create new segments
        segments_data = []
        for seg in caption.content_json:
            segments_data.append({
                "caption_id": caption.id,
                "video_id": video_id,
                "start_time": seg.get("start_time", 0),
                "end_time": seg.get("end_time", 0),
                "duration": seg.get("duration", 0),
                "text": seg.get("text", ""),
                "text_normalized": self._normalize_text(seg.get("text", "")),
                "segment_index": seg.get("segment_index", 0),
            })

        created_segments = await self.segment_repo.bulk_create_segments(
            segments_data
        )

        # Mark caption as processed
        await self.caption_repo.update(
            caption.id,
            is_processed=True,
            segment_count=len(created_segments),
        )

        await db.commit()

        return {
            "video_id": video_id,
            "language_code": language_code,
            "segments_created": len(created_segments),
        }

    def _normalize_text(self, text: str) -> str:
        """Normalize text for better search matching"""
        if not text:
            return ""

        # Lowercase
        text = text.lower()

        # Remove punctuation except spaces
        text = re.sub(r"[^\w\s]", " ", text)

        # Normalize whitespace
        text = " ".join(text.split())

        return text

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _caption_to_dict(self, caption: Caption) -> Dict[str, Any]:
        """Convert Caption model to dictionary"""
        return {
            "id": caption.id,
            "video_id": caption.video_id,
            "language_code": caption.language_code,
            "language_name": caption.language_name,
            "caption_type": caption.caption_type,
            "content": caption.content,
            "word_count": caption.word_count,
            "segment_count": caption.segment_count,
            "duration_seconds": caption.duration_seconds,
            "is_processed": caption.is_processed,
            "fetched_at": caption.fetched_at.isoformat() if caption.fetched_at else None,
            "created_at": caption.created_at.isoformat() if caption.created_at else None,
        }

    def _get_language_name(self, lang_code: str) -> str:
        """Get human-readable language name from code"""
        language_names = {
            "en": "English",
            "en-US": "English (US)",
            "en-GB": "English (UK)",
            "zh": "Chinese",
            "zh-TW": "Chinese (Traditional)",
            "zh-CN": "Chinese (Simplified)",
            "ja": "Japanese",
            "ko": "Korean",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "pt": "Portuguese",
            "ru": "Russian",
            "ar": "Arabic",
            "hi": "Hindi",
            "it": "Italian",
            "nl": "Dutch",
            "pl": "Polish",
            "tr": "Turkish",
            "vi": "Vietnamese",
            "th": "Thai",
            "id": "Indonesian",
        }

        return language_names.get(lang_code, lang_code)

    def _invalidate_video_caption_cache(self, video_id: str) -> None:
        """Invalidate all caption cache entries for a video"""
        # In a real implementation, would iterate through all language codes
        # For now, just clear known patterns
        self.delete_from_cache(self.get_cache_key("caption", video_id, "*"))


__all__ = ["CaptionService"]
