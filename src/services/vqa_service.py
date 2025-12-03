# src/services/vqa_service.py
"""
VQA Service
Business logic for Visual Question Answering operations
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import uuid
import os
import base64
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.base_service import BaseService
from src.services.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    ExternalServiceError,
    ProcessingError,
)
from src.services.llm_client import get_llm_client, Message

from src.infrastructure.repositories.vqa_repository import (
    VideoFrameRepository,
    FrameAnalysisRepository,
    VQASessionRepository,
    VQAQuestionRepository,
    VideoFrameExtractionRepository,
)
from src.infrastructure.repositories.video_repository import VideoRepository
from src.app.models import (
    VideoFrame,
    FrameAnalysis,
    VQASession,
    VQAQuestion,
    VideoFrameExtraction,
    FrameExtractionStatus,
    VQAModelType,
)

logger = logging.getLogger(__name__)


class VQAService(BaseService):
    """
    VQA operations service

    Handles:
    - Video frame extraction
    - Frame visual analysis
    - Question answering sessions
    - Visual search
    """

    def __init__(
        self,
        frame_repo: VideoFrameRepository,
        analysis_repo: FrameAnalysisRepository,
        session_repo: VQASessionRepository,
        question_repo: VQAQuestionRepository,
        extraction_repo: VideoFrameExtractionRepository,
        video_repo: VideoRepository,
        cache=None,
        config=None,
    ):
        super().__init__(cache=cache, config=config)
        self.frame_repo = frame_repo
        self.analysis_repo = analysis_repo
        self.session_repo = session_repo
        self.question_repo = question_repo
        self.extraction_repo = extraction_repo
        self.video_repo = video_repo

        # Model instance (lazy loaded)
        self._vqa_model = None
        self._model_type = None

    def get_service_name(self) -> str:
        return "vqa"

    # ========================================================================
    # Frame Extraction Operations
    # ========================================================================

    async def extract_frames(
        self,
        db: AsyncSession,
        video_id: str,
        method: str = "keyframe",
        max_frames: int = 50,
        interval_seconds: Optional[float] = None,
        force_reextract: bool = False,
    ) -> Dict[str, Any]:
        """
        Extract frames from a video

        Args:
            db: Database session
            video_id: YouTube video ID
            method: Extraction method (keyframe, interval, scene_change)
            max_frames: Maximum frames to extract
            interval_seconds: Interval for interval-based extraction
            force_reextract: Re-extract even if exists

        Returns:
            Extraction result
        """
        self.log_info(f"Extracting frames for video: {video_id}")
        self.validate_required(video_id, "video_id")

        # Verify video exists
        video = await self.video_repo.get_by_id(video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        # Check existing extraction
        existing = await self.extraction_repo.get_by_video_id(video_id)
        if existing and not force_reextract:
            if existing.status == FrameExtractionStatus.COMPLETED.value:
                return {
                    "video_id": video_id,
                    "status": "already_extracted",
                    "frames_count": existing.frames_extracted,
                }
            elif existing.status == FrameExtractionStatus.EXTRACTING.value:
                return {
                    "video_id": video_id,
                    "status": "in_progress",
                    "progress": existing.progress,
                }

        try:
            # Create or reset extraction job
            extraction = await self.extraction_repo.create_or_reset(
                video_id=video_id,
                extraction_method=method,
                max_frames=max_frames,
                interval_seconds=interval_seconds,
            )

            # Update status to extracting
            await self.extraction_repo.update_status(
                video_id, FrameExtractionStatus.EXTRACTING.value, progress=10
            )

            # Delete existing frames if re-extracting
            if force_reextract:
                await self.frame_repo.delete_by_video(video_id)

            # Perform extraction
            frames_data = await self._extract_video_frames(
                video_id=video_id,
                method=method,
                max_frames=max_frames,
                interval_seconds=interval_seconds,
            )

            # Update progress
            await self.extraction_repo.update_status(
                video_id, FrameExtractionStatus.EXTRACTING.value, progress=70
            )

            # Save frames to database
            if frames_data:
                await self.frame_repo.bulk_create_frames(frames_data)

            # Mark as completed
            await self.extraction_repo.update_status(
                video_id,
                FrameExtractionStatus.COMPLETED.value,
                progress=100,
                frames_extracted=len(frames_data),
            )

            await db.commit()

            self.log_info(f"Extracted {len(frames_data)} frames for video {video_id}")

            return {
                "video_id": video_id,
                "status": "completed",
                "frames_count": len(frames_data),
                "extraction_method": method,
            }

        except Exception as e:
            await self.extraction_repo.update_status(
                video_id,
                FrameExtractionStatus.FAILED.value,
                error_message=str(e),
            )
            await db.rollback()
            raise self.handle_error(e, "extract_frames", {"video_id": video_id})

    async def _extract_video_frames(
        self,
        video_id: str,
        method: str,
        max_frames: int,
        interval_seconds: Optional[float],
    ) -> List[Dict[str, Any]]:
        """
        Internal method to extract frames using ffmpeg/yt-dlp

        Returns list of frame data dicts ready for database insertion
        """
        import subprocess
        import tempfile
        import json

        frames_data = []

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                video_url = f"https://www.youtube.com/watch?v={video_id}"

                # Get video info first
                info_cmd = [
                    "yt-dlp",
                    "--dump-json",
                    "--skip-download",
                    video_url,
                ]
                info_result = subprocess.run(
                    info_cmd, capture_output=True, text=True, timeout=60
                )

                if info_result.returncode != 0:
                    raise ProcessingError(f"Failed to get video info: {info_result.stderr}")

                video_info = json.loads(info_result.stdout)
                duration = video_info.get("duration", 0)

                # Download video for frame extraction
                video_path = os.path.join(tmpdir, "video.mp4")
                download_cmd = [
                    "yt-dlp",
                    "-f", "best[height<=720]",
                    "-o", video_path,
                    video_url,
                ]
                download_result = subprocess.run(
                    download_cmd, capture_output=True, text=True, timeout=600
                )

                if download_result.returncode != 0:
                    raise ProcessingError(f"Failed to download video: {download_result.stderr}")

                # Extract frames based on method
                frames_dir = os.path.join(tmpdir, "frames")
                os.makedirs(frames_dir, exist_ok=True)

                if method == "interval":
                    # Extract at fixed intervals
                    interval = interval_seconds or 10.0
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-i", video_path,
                        "-vf", f"fps=1/{interval}",
                        "-frames:v", str(max_frames),
                        "-q:v", "2",
                        os.path.join(frames_dir, "frame_%04d.jpg"),
                    ]
                elif method == "scene_change":
                    # Extract on scene changes
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-i", video_path,
                        "-vf", "select='gt(scene,0.3)',showinfo",
                        "-vsync", "vfr",
                        "-frames:v", str(max_frames),
                        "-q:v", "2",
                        os.path.join(frames_dir, "frame_%04d.jpg"),
                    ]
                else:  # keyframe
                    # Extract keyframes (I-frames)
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-i", video_path,
                        "-vf", "select='eq(pict_type,I)'",
                        "-vsync", "vfr",
                        "-frames:v", str(max_frames),
                        "-q:v", "2",
                        os.path.join(frames_dir, "frame_%04d.jpg"),
                    ]

                ffmpeg_result = subprocess.run(
                    ffmpeg_cmd, capture_output=True, text=True, timeout=300
                )

                # Get output directory for frames
                output_dir = self._get_frames_output_dir(video_id)
                os.makedirs(output_dir, exist_ok=True)

                # Process extracted frames
                frame_files = sorted(
                    [f for f in os.listdir(frames_dir) if f.endswith(".jpg")]
                )

                for i, frame_file in enumerate(frame_files[:max_frames]):
                    src_path = os.path.join(frames_dir, frame_file)
                    dst_path = os.path.join(output_dir, f"{video_id}_{i:04d}.jpg")

                    # Move frame to output directory
                    import shutil
                    shutil.copy2(src_path, dst_path)

                    # Calculate timestamp based on frame number
                    if method == "interval":
                        timestamp = i * (interval_seconds or 10.0)
                    else:
                        # Estimate timestamp based on position
                        timestamp = (i / max(len(frame_files), 1)) * duration

                    # Get image dimensions
                    from PIL import Image
                    with Image.open(dst_path) as img:
                        width, height = img.size

                    frames_data.append({
                        "video_id": video_id,
                        "frame_number": i,
                        "timestamp": timestamp,
                        "file_path": dst_path,
                        "width": width,
                        "height": height,
                        "file_size": os.path.getsize(dst_path),
                        "format": "jpg",
                        "extraction_method": method,
                        "is_keyframe": method == "keyframe",
                    })

        except subprocess.TimeoutExpired:
            raise ProcessingError("Frame extraction timed out")
        except Exception as e:
            self.log_error(f"Frame extraction failed: {e}")
            raise

        return frames_data

    def _get_frames_output_dir(self, video_id: str) -> str:
        """Get output directory for video frames"""
        if self._config:
            base_dir = self._config.get("output_dir", "./output")
        else:
            base_dir = "./output"

        return os.path.join(base_dir, "frames", video_id)

    # ========================================================================
    # Frame Analysis Operations
    # ========================================================================

    async def analyze_frame(
        self,
        db: AsyncSession,
        frame_id: int,
        model_type: str = VQAModelType.BLIP2.value,
    ) -> Dict[str, Any]:
        """
        Analyze a single frame using VQA model

        Args:
            db: Database session
            frame_id: Frame ID
            model_type: Model to use for analysis

        Returns:
            Analysis result
        """
        self.log_info(f"Analyzing frame {frame_id} with model {model_type}")

        # Get frame
        frame = await self.frame_repo.get_by_id(frame_id)
        if not frame:
            raise ResourceNotFoundError("VideoFrame", str(frame_id))

        if not frame.file_path or not os.path.exists(frame.file_path):
            raise ValidationError(f"Frame file not found: {frame.file_path}")

        try:
            import time
            start_time = time.time()

            # Load model if needed
            self._ensure_model_loaded(model_type)

            # Perform analysis
            analysis_result = await self._analyze_image(
                frame.file_path, model_type
            )

            processing_time = int((time.time() - start_time) * 1000)

            # Save analysis
            analysis_data = {
                "frame_id": frame_id,
                "model_type": model_type,
                "caption": analysis_result.get("caption"),
                "description": analysis_result.get("description"),
                "objects_detected": analysis_result.get("objects"),
                "text_detected": analysis_result.get("text"),
                "scene_type": analysis_result.get("scene_type"),
                "scene_confidence": analysis_result.get("scene_confidence"),
                "tags": analysis_result.get("tags"),
                "raw_output": analysis_result.get("raw"),
                "processing_time_ms": processing_time,
            }

            analysis = await self.analysis_repo.create(**analysis_data)
            await db.commit()

            return analysis.to_dict()

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "analyze_frame", {"frame_id": frame_id})

    async def analyze_video_frames(
        self,
        db: AsyncSession,
        video_id: str,
        model_type: str = VQAModelType.BLIP2.value,
        max_frames: int = 20,
    ) -> Dict[str, Any]:
        """
        Analyze multiple frames from a video

        Args:
            db: Database session
            video_id: Video ID
            model_type: Model to use
            max_frames: Maximum frames to analyze

        Returns:
            Analysis summary
        """
        self.log_info(f"Analyzing frames for video {video_id}")

        # Get keyframes
        frames = await self.frame_repo.get_keyframes(video_id, limit=max_frames)

        if not frames:
            raise ValidationError(f"No frames found for video {video_id}")

        results = {
            "video_id": video_id,
            "model_type": model_type,
            "success": [],
            "failed": [],
        }

        for frame in frames:
            try:
                analysis = await self.analyze_frame(db, frame.id, model_type)
                results["success"].append({
                    "frame_id": frame.id,
                    "timestamp": frame.timestamp,
                    "caption": analysis.get("caption"),
                })
            except Exception as e:
                self.log_warning(f"Failed to analyze frame {frame.id}: {e}")
                results["failed"].append({
                    "frame_id": frame.id,
                    "error": str(e),
                })

        return results

    def _ensure_model_loaded(self, model_type: str):
        """Ensure VQA model is loaded"""
        if self._vqa_model is not None and self._model_type == model_type:
            return

        self.log_info(f"Loading VQA model: {model_type}")

        # For now, use a placeholder - actual model loading would go here
        # This is where you'd initialize BLIP-2, LLaVA, etc.
        self._model_type = model_type
        self._vqa_model = "placeholder"

    async def _analyze_image(
        self,
        image_path: str,
        model_type: str,
    ) -> Dict[str, Any]:
        """
        Analyze image using vision-capable LLM or local VQA model

        Supports:
        - OpenAI GPT-4 Vision
        - LLMVendor LLMProvider Vision
        - Ollama with LLaVA
        """
        import httpx
        from PIL import Image

        # Get image dimensions
        with Image.open(image_path) as img:
            width, height = img.size

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Determine image mime type
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")

        model_lower = model_type.lower()

        # OpenAI GPT-4 Vision
        if "gpt" in model_lower or "openai" in model_lower:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": "gpt-4o-mini",
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Analyze this video frame. Provide: 1) A brief caption, 2) A detailed description, 3) List of visible objects, 4) Any text visible in the image, 5) Scene type (indoor/outdoor/presentation/etc). Format as JSON.",
                                            },
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:{mime_type};base64,{image_data}",
                                                },
                                            },
                                        ],
                                    }
                                ],
                                "max_tokens": 1000,
                            },
                        )
                        response.raise_for_status()
                        result = response.json()
                        content = result["choices"][0]["message"]["content"]

                        # Parse the response
                        return self._parse_vision_response(content, model_type, width, height)
                except Exception as e:
                    logger.error(f"OpenAI Vision analysis failed: {e}")

        # LLMVendor LLMProvider Vision
        elif "llm_provider" in model_lower or "llm_vendor" in model_lower:
            api_key = os.getenv("LLM_VENDOR_API_KEY")
            if api_key:
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            "https://api.llm_vendor.com/v1/messages",
                            headers={
                                "x-api-key": api_key,
                                "Content-Type": "application/json",
                                "llm_vendor-version": "2023-06-01",
                            },
                            json={
                                "model": "llm_provider-3-haiku-20240307",
                                "max_tokens": 1000,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "image",
                                                "source": {
                                                    "type": "base64",
                                                    "media_type": mime_type,
                                                    "data": image_data,
                                                },
                                            },
                                            {
                                                "type": "text",
                                                "text": "Analyze this video frame. Provide: 1) A brief caption, 2) A detailed description, 3) List of visible objects, 4) Any text visible in the image, 5) Scene type. Format as JSON.",
                                            },
                                        ],
                                    }
                                ],
                            },
                        )
                        response.raise_for_status()
                        result = response.json()
                        content = result["content"][0]["text"]

                        return self._parse_vision_response(content, model_type, width, height)
                except Exception as e:
                    logger.error(f"LLMProvider Vision analysis failed: {e}")

        # Ollama with LLaVA
        elif "llava" in model_lower or "ollama" in model_lower or "blip" in model_lower:
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{ollama_host}/api/generate",
                        json={
                            "model": "llava",
                            "prompt": "Analyze this video frame. Describe what you see, list objects, identify the scene type, and note any text visible.",
                            "images": [image_data],
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    content = result.get("response", "")

                    return self._parse_vision_response(content, model_type, width, height)
            except Exception as e:
                logger.warning(f"Ollama LLaVA analysis failed: {e}")

        # Fallback to basic analysis
        return {
            "caption": f"Video frame ({width}x{height})",
            "description": "Vision model not available. Configure OPENAI_API_KEY, LLM_VENDOR_API_KEY, or Ollama with LLaVA for image analysis.",
            "objects": [],
            "text": [],
            "scene_type": "unknown",
            "scene_confidence": 0.0,
            "tags": ["frame", "video"],
            "raw": {"model": model_type, "status": "fallback", "width": width, "height": height},
        }

    def _parse_vision_response(
        self,
        content: str,
        model_type: str,
        width: int,
        height: int,
    ) -> Dict[str, Any]:
        """Parse vision model response into structured format"""
        import json
        import re

        # Try to parse as JSON first
        try:
            # Find JSON in the response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "caption": data.get("caption", ""),
                    "description": data.get("description", content[:500]),
                    "objects": data.get("objects", []),
                    "text": data.get("text", []),
                    "scene_type": data.get("scene_type", "unknown"),
                    "scene_confidence": data.get("confidence", 0.8),
                    "tags": data.get("tags", []),
                    "raw": {"model": model_type, "response": content},
                }
        except json.JSONDecodeError:
            pass

        # Fallback: extract from plain text
        lines = content.strip().split('\n')
        caption = lines[0] if lines else ""

        return {
            "caption": caption[:200],
            "description": content[:1000],
            "objects": [],
            "text": [],
            "scene_type": "unknown",
            "scene_confidence": 0.7,
            "tags": ["analyzed"],
            "raw": {"model": model_type, "response": content, "width": width, "height": height},
        }

    # ========================================================================
    # VQA Session Operations
    # ========================================================================

    async def create_session(
        self,
        db: AsyncSession,
        video_id: str,
        user_id: Optional[str] = None,
        model_type: str = VQAModelType.BLIP2.value,
    ) -> Dict[str, Any]:
        """
        Create a new VQA session

        Args:
            db: Database session
            video_id: Video ID
            user_id: User identifier
            model_type: VQA model to use

        Returns:
            Created session info
        """
        self.log_info(f"Creating VQA session for video {video_id}")

        # Verify video exists and has frames
        video = await self.video_repo.get_by_id(video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        frame_count = await self.frame_repo.count_by_video(video_id)
        if frame_count == 0:
            raise ValidationError(
                f"Video {video_id} has no extracted frames. "
                "Please extract frames first."
            )

        try:
            session_id = str(uuid.uuid4())

            session = await self.session_repo.create(
                id=session_id,
                video_id=video_id,
                user_id=user_id,
                model_type=model_type,
                is_active=True,
                question_count=0,
            )

            await db.commit()

            return {
                "session_id": session.id,
                "video_id": video_id,
                "model_type": model_type,
                "frame_count": frame_count,
                "created_at": session.created_at.isoformat(),
            }

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "create_session", {"video_id": video_id})

    async def ask_question(
        self,
        db: AsyncSession,
        session_id: str,
        question: str,
        timestamp: Optional[float] = None,
        frame_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Ask a question in a VQA session

        Args:
            db: Database session
            session_id: Session ID
            question: User's question
            timestamp: Optional video timestamp for context
            frame_id: Optional specific frame ID

        Returns:
            Question and answer
        """
        self.log_info(f"Processing question in session {session_id}")
        self.validate_required(question, "question")

        # Get session
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise ResourceNotFoundError("VQASession", session_id)

        if not session.is_active:
            raise ValidationError("Session is no longer active")

        try:
            import time
            start_time = time.time()

            # Get relevant frames
            relevant_frames = []
            if frame_id:
                frame = await self.frame_repo.get_by_id(frame_id)
                if frame:
                    relevant_frames = [frame]
            elif timestamp is not None:
                frame = await self.frame_repo.get_frame_at_timestamp(
                    session.video_id, timestamp
                )
                if frame:
                    relevant_frames = [frame]
            else:
                # Use keyframes as context
                relevant_frames = await self.frame_repo.get_keyframes(
                    session.video_id, limit=5
                )

            # Get recent Q&A for context
            recent_questions = await self.question_repo.get_recent_questions(
                session_id, limit=3
            )

            # Generate answer
            answer_result = await self._generate_answer(
                question=question,
                frames=relevant_frames,
                context=recent_questions,
                model_type=session.model_type,
            )

            processing_time = int((time.time() - start_time) * 1000)

            # Save question and answer
            question_data = {
                "session_id": session_id,
                "frame_id": frame_id or (relevant_frames[0].id if relevant_frames else None),
                "question": question,
                "question_type": self._classify_question(question),
                "timestamp_start": timestamp,
                "answer": answer_result.get("answer"),
                "confidence": answer_result.get("confidence"),
                "relevant_frames": [f.id for f in relevant_frames],
                "evidence": answer_result.get("evidence"),
                "model_type": session.model_type,
                "processing_time_ms": processing_time,
                "answered_at": datetime.utcnow(),
            }

            saved_question = await self.question_repo.create(**question_data)

            # Update session
            session.question_count += 1
            session.last_activity_at = datetime.utcnow()
            await db.commit()

            return {
                "question_id": saved_question.id,
                "question": question,
                "answer": answer_result.get("answer"),
                "confidence": answer_result.get("confidence"),
                "relevant_frames": [
                    {"id": f.id, "timestamp": f.timestamp}
                    for f in relevant_frames
                ],
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "ask_question", {"session_id": session_id})

    async def _generate_answer(
        self,
        question: str,
        frames: List[VideoFrame],
        context: List[VQAQuestion],
        model_type: str,
    ) -> Dict[str, Any]:
        """
        Generate answer using vision-capable LLM

        Supports:
        - OpenAI GPT-4 Vision
        - LLMVendor LLMProvider Vision
        - Ollama with LLaVA
        """
        import httpx

        # Build context from previous Q&A
        context_str = ""
        if context:
            context_str = "Previous conversation:\n"
            for q in context:
                context_str += f"Q: {q.question}\nA: {q.answer}\n\n"

        # Load and encode frame images
        encoded_images = []
        for frame in frames[:3]:  # Limit to 3 frames
            if frame.file_path and os.path.exists(frame.file_path):
                try:
                    with open(frame.file_path, "rb") as f:
                        image_data = base64.b64encode(f.read()).decode("utf-8")
                        ext = os.path.splitext(frame.file_path)[1].lower()
                        mime_type = {
                            ".jpg": "image/jpeg",
                            ".jpeg": "image/jpeg",
                            ".png": "image/png",
                        }.get(ext, "image/jpeg")
                        encoded_images.append({
                            "data": image_data,
                            "mime_type": mime_type,
                            "timestamp": frame.timestamp,
                        })
                except Exception as e:
                    logger.warning(f"Failed to load frame {frame.id}: {e}")

        model_lower = model_type.lower()

        # OpenAI GPT-4 Vision
        if "gpt" in model_lower or "openai" in model_lower:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key and encoded_images:
                try:
                    # Build message content with images
                    content = [
                        {
                            "type": "text",
                            "text": f"{context_str}Based on these video frames, please answer: {question}",
                        }
                    ]
                    for img in encoded_images:
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{img['mime_type']};base64,{img['data']}",
                            },
                        })

                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": "gpt-4o-mini",
                                "messages": [{"role": "user", "content": content}],
                                "max_tokens": 1000,
                            },
                        )
                        response.raise_for_status()
                        result = response.json()
                        answer = result["choices"][0]["message"]["content"]

                        return {
                            "answer": answer,
                            "confidence": 0.85,
                            "evidence": {
                                "frames_analyzed": len(encoded_images),
                                "context_turns": len(context),
                                "model": "gpt-4o-mini",
                            },
                        }
                except Exception as e:
                    logger.error(f"OpenAI VQA failed: {e}")

        # LLMVendor LLMProvider Vision
        elif "llm_provider" in model_lower or "llm_vendor" in model_lower:
            api_key = os.getenv("LLM_VENDOR_API_KEY")
            if api_key and encoded_images:
                try:
                    # Build content with images
                    content = []
                    for img in encoded_images:
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": img["mime_type"],
                                "data": img["data"],
                            },
                        })
                    content.append({
                        "type": "text",
                        "text": f"{context_str}Based on these video frames, please answer: {question}",
                    })

                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            "https://api.llm_vendor.com/v1/messages",
                            headers={
                                "x-api-key": api_key,
                                "Content-Type": "application/json",
                                "llm_vendor-version": "2023-06-01",
                            },
                            json={
                                "model": "llm_provider-3-haiku-20240307",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": content}],
                            },
                        )
                        response.raise_for_status()
                        result = response.json()
                        answer = result["content"][0]["text"]

                        return {
                            "answer": answer,
                            "confidence": 0.85,
                            "evidence": {
                                "frames_analyzed": len(encoded_images),
                                "context_turns": len(context),
                                "model": "llm_provider-3-haiku",
                            },
                        }
                except Exception as e:
                    logger.error(f"LLMProvider VQA failed: {e}")

        # Ollama with LLaVA
        elif encoded_images:
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{ollama_host}/api/generate",
                        json={
                            "model": "llava",
                            "prompt": f"{context_str}Based on this video frame, please answer: {question}",
                            "images": [encoded_images[0]["data"]],
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    answer = result.get("response", "")

                    return {
                        "answer": answer,
                        "confidence": 0.7,
                        "evidence": {
                            "frames_analyzed": 1,
                            "context_turns": len(context),
                            "model": "llava",
                        },
                    }
            except Exception as e:
                logger.warning(f"Ollama LLaVA VQA failed: {e}")

        # Fallback: Use text-only LLM with frame analysis descriptions
        try:
            llm_client = get_llm_client()
            prompt = f"""{context_str}
The user is asking about video frames. Number of frames available: {len(frames)}.
Frame timestamps: {[f.timestamp for f in frames]}

Question: {question}

Note: Vision model not available. Please provide a general response based on the context."""

            response = await llm_client.generate(
                prompt=prompt,
                system_prompt="You are a helpful video analysis assistant. Answer questions about video content.",
            )

            return {
                "answer": response.content,
                "confidence": 0.5,
                "evidence": {
                    "frames_analyzed": len(frames),
                    "context_turns": len(context),
                    "model": response.model,
                    "note": "Vision model not available, using text-only fallback",
                },
            }
        except Exception as e:
            logger.error(f"VQA generation failed: {e}")
            return {
                "answer": f"I was unable to analyze the video frames. Please ensure a vision-capable model is configured. Error: {str(e)}",
                "confidence": 0.0,
                "evidence": {
                    "frames_analyzed": len(frames),
                    "context_turns": len(context),
                    "model": model_type,
                    "error": str(e),
                },
            }

    def _classify_question(self, question: str) -> str:
        """Classify question type"""
        question_lower = question.lower()

        if question_lower.startswith("what"):
            return "what"
        elif question_lower.startswith("who"):
            return "who"
        elif question_lower.startswith("where"):
            return "where"
        elif question_lower.startswith("when"):
            return "when"
        elif question_lower.startswith("why"):
            return "why"
        elif question_lower.startswith("how"):
            return "how"
        elif any(word in question_lower for word in ["describe", "explain", "tell"]):
            return "describe"
        else:
            return "other"

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
        include_questions: bool = False,
    ) -> Dict[str, Any]:
        """Get session details"""
        if include_questions:
            session = await self.session_repo.get_with_questions(session_id)
        else:
            session = await self.session_repo.get_by_id(session_id)

        if not session:
            raise ResourceNotFoundError("VQASession", session_id)

        result = session.to_dict()

        if include_questions:
            result["questions"] = [q.to_dict() for q in session.questions]

        return result

    async def end_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> Dict[str, Any]:
        """End a VQA session"""
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise ResourceNotFoundError("VQASession", session_id)

        await self.session_repo.deactivate_session(session_id)
        await db.commit()

        return {
            "session_id": session_id,
            "status": "ended",
            "question_count": session.question_count,
        }

    async def rate_answer(
        self,
        db: AsyncSession,
        question_id: int,
        rating: int,
        feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rate an answer"""
        self.validate_range(rating, "rating", 1, 5)

        success = await self.question_repo.update_rating(
            question_id, rating, feedback
        )

        if not success:
            raise ResourceNotFoundError("VQAQuestion", str(question_id))

        await db.commit()

        return {
            "question_id": question_id,
            "rating": rating,
            "feedback": feedback,
        }

    # ========================================================================
    # Frame Retrieval
    # ========================================================================

    async def get_video_frames(
        self,
        db: AsyncSession,
        video_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get frames for a video"""
        frames = await self.frame_repo.get_by_video_id(video_id, skip, limit)
        total = await self.frame_repo.count_by_video(video_id)

        return [f.to_dict() for f in frames], total

    async def get_frame_with_analysis(
        self,
        db: AsyncSession,
        frame_id: int,
    ) -> Dict[str, Any]:
        """Get frame with its analyses"""
        frame = await self.frame_repo.get_by_id(frame_id)
        if not frame:
            raise ResourceNotFoundError("VideoFrame", str(frame_id))

        analyses = await self.analysis_repo.get_by_frame_id(frame_id)

        return {
            "frame": frame.to_dict(),
            "analyses": [a.to_dict() for a in analyses],
        }

    async def search_frames(
        self,
        db: AsyncSession,
        query: str,
        video_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search frames by caption/description"""
        return await self.analysis_repo.search_by_caption(
            query, video_id, skip, limit
        )


__all__ = ["VQAService"]
