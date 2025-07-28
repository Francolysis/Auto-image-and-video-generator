import os
import tempfile
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple
import re
import whisper
from gtts import gTTS
from moviepy.editor import *
from moviepy.video.fx import resize, fadeout
from pydub import AudioSegment
import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        self.whisper_model = None
        
    async def load_whisper_model(self):
        """Load Whisper model for speech recognition"""
        if not self.whisper_model:
            logger.info("Loading Whisper model...")
            self.whisper_model = whisper.load_model("base")
            
    def split_text_into_scenes(self, text: str) -> List[str]:
        """Split text into scenes based on narrative structure"""
        # Split by common scene indicators
        scene_patterns = [
            r'\n\n+',  # Double line breaks
            r'\.(\s*)(Meanwhile|Later|Then|Next|After|Suddenly|However)',
            r'\.(\s*)(Scene|Chapter|Part)',
            r'\.(\s*)[A-Z][a-z]+\s*(walked|went|moved|arrived|entered)'
        ]
        
        scenes = [text]
        for pattern in scene_patterns:
            new_scenes = []
            for scene in scenes:
                new_scenes.extend(re.split(pattern, scene, flags=re.IGNORECASE))
            scenes = [s.strip() for s in new_scenes if s.strip()]
        
        # Ensure minimum scene length and maximum scene count
        filtered_scenes = []
        for scene in scenes:
            if len(scene) > 20:  # Minimum 20 characters
                # Truncate very long scenes to manageable prompts
                if len(scene) > 200:
                    scene = scene[:200] + "..."
                filtered_scenes.append(scene)
        
        return filtered_scenes[:20]  # Maximum 20 scenes
    
    async def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcribe audio to text using Whisper"""
        await self.load_whisper_model()
        logger.info(f"Transcribing audio: {audio_file_path}")
        
        result = self.whisper_model.transcribe(audio_file_path)
        return result["text"]
    
    def create_animation_effect(self, image_path: str, duration: float, effect_type: str = "zoom_in") -> VideoFileClip:
        """Create animated effects for images"""
        try:
            # Load image
            img_clip = ImageClip(image_path, duration=duration)
            
            # Get image dimensions
            img = Image.open(image_path)
            w, h = img.size
            
            # Target video dimensions (1920x1080 for YouTube)
            target_w, target_h = 1920, 1080
            
            if effect_type == "zoom_in":
                # Start zoomed out, zoom in
                img_clip = img_clip.resize(lambda t: 1 + 0.1 * t / duration)
                img_clip = img_clip.set_position('center')
                
            elif effect_type == "zoom_out":
                # Start zoomed in, zoom out
                img_clip = img_clip.resize(lambda t: 1.2 - 0.1 * t / duration)
                img_clip = img_clip.set_position('center')
                
            elif effect_type == "pan_right":
                # Pan from left to right
                img_clip = img_clip.resize(height=target_h)
                if img_clip.w > target_w:
                    img_clip = img_clip.set_position(lambda t: (-100 * t / duration, 'center'))
                else:
                    img_clip = img_clip.set_position('center')
                    
            elif effect_type == "pan_left":
                # Pan from right to left
                img_clip = img_clip.resize(height=target_h)
                if img_clip.w > target_w:
                    img_clip = img_clip.set_position(lambda t: (100 * t / duration - 100, 'center'))
                else:
                    img_clip = img_clip.set_position('center')
                    
            else:  # static
                img_clip = img_clip.resize(height=target_h).set_position('center')
            
            # Ensure clip fits screen
            if img_clip.w < target_w or img_clip.h < target_h:
                img_clip = img_clip.resize((target_w, target_h))
            
            return img_clip
            
        except Exception as e:
            logger.error(f"Error creating animation for {image_path}: {e}")
            # Fallback to static image
            return ImageClip(image_path, duration=duration).resize((1920, 1080))
    
    def create_transition(self, duration: float = 0.5) -> VideoFileClip:
        """Create a transition effect between scenes"""
        # Simple fade transition
        black_clip = ColorClip(size=(1920, 1080), color=(0,0,0), duration=duration)
        return black_clip.fadeout(duration/2).fadein(duration/2)
    
    async def compile_video_from_images(
        self, 
        image_paths: List[str], 
        audio_path: Optional[str] = None,
        scene_durations: Optional[List[float]] = None,
        animation_effects: Optional[List[str]] = None
    ) -> str:
        """Compile video from images with animations and transitions"""
        
        if not image_paths:
            raise ValueError("No images provided for video compilation")
        
        # Default values
        if not scene_durations:
            scene_durations = [4.0] * len(image_paths)  # 4 seconds per scene
        if not animation_effects:
            animation_effects = ["zoom_in", "zoom_out", "pan_right", "pan_left"] * (len(image_paths) // 4 + 1)
            animation_effects = animation_effects[:len(image_paths)]
        
        logger.info(f"Compiling video with {len(image_paths)} scenes")
        
        try:
            # Create video clips for each image
            video_clips = []
            
            for i, (img_path, duration, effect) in enumerate(zip(image_paths, scene_durations, animation_effects)):
                if os.path.exists(img_path):
                    logger.info(f"Processing scene {i+1}/{len(image_paths)}: {effect}")
                    
                    # Create animated clip
                    clip = self.create_animation_effect(img_path, duration, effect)
                    video_clips.append(clip)
                    
                    # Add transition between scenes (except for the last one)
                    if i < len(image_paths) - 1:
                        transition = self.create_transition(0.5)
                        video_clips.append(transition)
            
            if not video_clips:
                raise ValueError("No valid video clips created")
            
            # Concatenate all clips
            logger.info("Concatenating video clips...")
            final_video = concatenate_videoclips(video_clips, method="compose")
            
            # Add audio if provided
            if audio_path and os.path.exists(audio_path):
                logger.info("Adding audio track...")
                audio_clip = AudioFileClip(audio_path)
                
                # Adjust video duration to match audio if needed
                if audio_clip.duration > final_video.duration:
                    # Extend video by looping last frame
                    last_frame = ImageClip(image_paths[-1], duration=audio_clip.duration - final_video.duration)
                    final_video = concatenate_videoclips([final_video, last_frame])
                elif audio_clip.duration < final_video.duration:
                    # Trim video to audio length
                    final_video = final_video.subclip(0, audio_clip.duration)
                
                final_video = final_video.set_audio(audio_clip)
            
            # Export video
            output_path = os.path.join(tempfile.gettempdir(), f"compiled_video_{os.getpid()}.mp4")
            logger.info(f"Exporting video to: {output_path}")
            
            final_video.write_videofile(
                output_path,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                verbose=False,
                logger=None
            )
            
            # Cleanup
            final_video.close()
            if audio_path and os.path.exists(audio_path):
                AudioFileClip(audio_path).close()
            
            logger.info(f"Video compilation completed: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error compiling video: {e}")
            raise
    
    def create_tts_audio(self, text: str, language: str = 'en') -> str:
        """Create text-to-speech audio"""
        try:
            logger.info("Creating TTS audio...")
            tts = gTTS(text=text, lang=language, slow=False)
            
            audio_path = os.path.join(tempfile.gettempdir(), f"tts_audio_{os.getpid()}.mp3")
            tts.save(audio_path)
            
            logger.info(f"TTS audio created: {audio_path}")
            return audio_path
            
        except Exception as e:
            logger.error(f"Error creating TTS audio: {e}")
            raise
    
    def calculate_scene_durations(self, scenes: List[str], total_audio_duration: Optional[float] = None) -> List[float]:
        """Calculate appropriate duration for each scene based on text length"""
        if not scenes:
            return []
        
        # Base duration calculation (words per minute = 150)
        words_per_minute = 150
        base_durations = []
        
        for scene in scenes:
            word_count = len(scene.split())
            duration = max(3.0, (word_count / words_per_minute) * 60)  # Minimum 3 seconds
            base_durations.append(duration)
        
        # If we have audio duration, scale to fit
        if total_audio_duration:
            total_base = sum(base_durations)
            if total_base > 0:
                scale_factor = total_audio_duration / total_base
                base_durations = [d * scale_factor for d in base_durations]
        
        return base_durations

# Global instance
video_processor = VideoProcessor()