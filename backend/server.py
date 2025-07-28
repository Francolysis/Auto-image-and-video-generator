from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import csv
import io
import base64
import zipfile
import tempfile
import asyncio
import aiohttp
import json
from video_processor import video_processor
import sys; print("PYTHON VERSION:", sys.version)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Cloudflare Workers AI Configuration
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
CLOUDFLARE_API_TOKEN = os.environ.get('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_API_BASE = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run"

# Define Models
class ImagePrompt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    style: Optional[str] = "photorealistic"
    aspect_ratio: Optional[str] = "1:1"

class GenerationJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompts: List[ImagePrompt]
    status: str = "pending"  # pending, processing, completed, failed
    progress: int = 0
    total_images: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    zip_file_path: Optional[str] = None
    video_file_path: Optional[str] = None
    current_task: Optional[str] = "Initializing..."
    job_type: str = "images"  # images, text_to_video, voice_to_video

class GenerationRequest(BaseModel):
    prompts: List[str]
    style: Optional[str] = "photorealistic"
    aspect_ratio: Optional[str] = "1:1"

class TextToVideoRequest(BaseModel):
    script: str
    style: Optional[str] = "photorealistic"
    aspect_ratio: Optional[str] = "16:9"

# Storage for jobs (in production, use database)
jobs_storage = {}

def get_image_dimensions(aspect_ratio: str):
    """Convert aspect ratio to width/height dimensions"""
    ratio_map = {
        "1:1": (1024, 1024),
        "16:9": (1344, 768),
        "9:16": (768, 1344),
        "4:3": (1152, 896),
        "3:4": (896, 1152),
        "21:9": (1536, 640)
    }
    return ratio_map.get(aspect_ratio, (1024, 1024))

async def generate_single_image(prompt: str, style: str, aspect_ratio: str):
    """Generate a single image using Cloudflare Workers AI"""
    width, height = get_image_dimensions(aspect_ratio)
    
    # Create enhanced prompt with style
    enhanced_prompt = f"{prompt}, {style} style, high quality, detailed"
    
    payload = {
        "prompt": enhanced_prompt,
        "width": width,
        "height": height,
        "num_steps": 20,
        "strength": 0.8,
        "guidance": 7.5
    }
    
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{CLOUDFLARE_API_BASE}/@cf/stabilityai/stable-diffusion-xl-base-1.0",
            headers=headers,
            json=payload
        ) as response:
            if response.status == 200:
                content_type = response.headers.get('content-type', '')
                if 'image/' in content_type:
                    # Direct binary image response
                    return await response.read()
                else:
                    # JSON response with base64 encoded data
                    result = await response.json()
                    if result.get("success") and result.get("result"):
                        image_data = result["result"][0]  # First image from result
                        return base64.b64decode(image_data)
                    else:
                        raise Exception(f"API returned no image data: {result}")
            else:
                error_text = await response.text()
                raise Exception(f"Cloudflare API error {response.status}: {error_text}")

@api_router.get("/")
async def root():
    return {"message": "AI Video Production Studio API"}

@api_router.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    try:
        content = await file.read()
        csv_data = content.decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.reader(io.StringIO(csv_data))
        prompts = []
        
        for row in csv_reader:
            if row and len(row) > 0 and row[0].strip():  # Skip empty rows
                prompts.append(row[0].strip())
        
        if not prompts:
            raise HTTPException(status_code=400, detail="No valid prompts found in CSV")
        
        return {"prompts": prompts, "count": len(prompts)}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing CSV: {str(e)}")

@api_router.post("/generate-images")
async def generate_images(request: GenerationRequest):
    job_id = str(uuid.uuid4())
    
    # Create job
    job = GenerationJob(
        id=job_id,
        prompts=[ImagePrompt(prompt=p, style=request.style, aspect_ratio=request.aspect_ratio) 
                for p in request.prompts],
        total_images=len(request.prompts),
        job_type="images"
    )
    
    jobs_storage[job_id] = job
    
    # Start generation in background
    asyncio.create_task(process_image_generation(job_id))
    
    return {"job_id": job_id, "status": "started"}

@api_router.post("/generate-text-to-video")
async def generate_text_to_video(request: TextToVideoRequest):
    job_id = str(uuid.uuid4())
    
    # Split script into scenes
    scenes = video_processor.split_text_into_scenes(request.script)
    
    if not scenes:
        raise HTTPException(status_code=400, detail="Could not extract scenes from script")
    
    # Create job
    job = GenerationJob(
        id=job_id,
        prompts=[ImagePrompt(prompt=scene, style=request.style, aspect_ratio=request.aspect_ratio) 
                for scene in scenes],
        total_images=len(scenes),
        job_type="text_to_video",
        current_task="Processing script..."
    )
    
    jobs_storage[job_id] = job
    
    # Start generation in background
    asyncio.create_task(process_text_to_video_generation(job_id, request.script))
    
    return {"job_id": job_id, "status": "started"}

@api_router.post("/generate-voice-to-video")
async def generate_voice_to_video(
    audio: UploadFile = File(...),
    style: str = "photorealistic",
    aspect_ratio: str = "16:9"
):
    job_id = str(uuid.uuid4())
    
    # Save uploaded audio file
    audio_path = os.path.join(tempfile.gettempdir(), f"audio_{job_id}.{audio.filename.split('.')[-1]}")
    with open(audio_path, "wb") as f:
        f.write(await audio.read())
    
    # Create initial job
    job = GenerationJob(
        id=job_id,
        prompts=[],
        total_images=0,
        job_type="voice_to_video",
        current_task="Transcribing audio..."
    )
    
    jobs_storage[job_id] = job
    
    # Start generation in background
    asyncio.create_task(process_voice_to_video_generation(job_id, audio_path, style, aspect_ratio))
    
    return {"job_id": job_id, "status": "started"}

async def process_image_generation(job_id: str):
    job = jobs_storage[job_id]
    job.status = "processing"
    job.current_task = "Generating images..."
    
    # Create temp directory for images
    temp_dir = tempfile.mkdtemp()
    generated_images = []
    
    try:
        for i, prompt_obj in enumerate(job.prompts):
            try:
                job.current_task = f"Generating image {i+1}/{len(job.prompts)}"
                
                # Generate image using Cloudflare Workers AI
                image_data = await generate_single_image(
                    prompt_obj.prompt, 
                    prompt_obj.style, 
                    prompt_obj.aspect_ratio
                )
                
                if image_data:
                    # Save image
                    image_filename = f"image_{i+1:03d}_{prompt_obj.prompt[:30].replace(' ', '_')}.png"
                    image_path = os.path.join(temp_dir, image_filename)
                    
                    with open(image_path, "wb") as f:
                        f.write(image_data)
                    
                    generated_images.append(image_path)
                    
                    # Update progress
                    job.progress = int(((i + 1) / len(job.prompts)) * 100)
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(1)
                
            except Exception as e:
                print(f"Error generating image for prompt {i+1}: {str(e)}")
                continue
        
        # Create zip file
        if generated_images:
            job.current_task = "Creating ZIP file..."
            zip_filename = f"youtube_images_{job_id}.zip"
            zip_path = os.path.join(temp_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for img_path in generated_images:
                    zipf.write(img_path, os.path.basename(img_path))
            
            job.zip_file_path = zip_path
            job.status = "completed"
            job.current_task = "Generation completed!"
        else:
            job.status = "failed"
            job.current_task = "Generation failed - no images created"
    
    except Exception as e:
        job.status = "failed"
        job.current_task = f"Generation failed: {str(e)}"
        print(f"Job {job_id} failed: {str(e)}")

async def process_text_to_video_generation(job_id: str, script: str):
    job = jobs_storage[job_id]
    job.status = "processing"
    
    temp_dir = tempfile.mkdtemp()
    generated_images = []
    
    try:
        # Generate images for each scene
        job.current_task = "Generating scene images..."
        for i, prompt_obj in enumerate(job.prompts):
            try:
                job.current_task = f"Generating scene {i+1}/{len(job.prompts)}"
                
                image_data = await generate_single_image(
                    prompt_obj.prompt, 
                    prompt_obj.style, 
                    prompt_obj.aspect_ratio
                )
                
                if image_data:
                    image_filename = f"scene_{i+1:03d}.png"
                    image_path = os.path.join(temp_dir, image_filename)
                    
                    with open(image_path, "wb") as f:
                        f.write(image_data)
                    
                    generated_images.append(image_path)
                    
                    # Update progress (50% for image generation)
                    job.progress = int(((i + 1) / len(job.prompts)) * 50)
                    
                    await asyncio.sleep(1)
                
            except Exception as e:
                print(f"Error generating image for scene {i+1}: {str(e)}")
                continue
        
        if generated_images:
            # Create TTS audio
            job.current_task = "Creating voiceover..."
            job.progress = 60
            audio_path = video_processor.create_tts_audio(script)
            
            # Calculate scene durations based on script
            scenes = [p.prompt for p in job.prompts]
            scene_durations = video_processor.calculate_scene_durations(scenes)
            
            # Generate animation effects
            animation_effects = ["zoom_in", "zoom_out", "pan_right", "pan_left"] * (len(generated_images) // 4 + 1)
            animation_effects = animation_effects[:len(generated_images)]
            
            # Compile video
            job.current_task = "Compiling video..."
            job.progress = 80
            
            video_path = await video_processor.compile_video_from_images(
                generated_images,
                audio_path,
                scene_durations,
                animation_effects
            )
            
            job.video_file_path = video_path
            job.status = "completed"
            job.progress = 100
            job.current_task = "Video generation completed!"
            
        else:
            job.status = "failed"
            job.current_task = "Failed to generate images"
    
    except Exception as e:
        job.status = "failed"
        job.current_task = f"Video generation failed: {str(e)}"
        print(f"Text-to-video job {job_id} failed: {str(e)}")

async def process_voice_to_video_generation(job_id: str, audio_path: str, style: str, aspect_ratio: str):
    job = jobs_storage[job_id]
    job.status = "processing"
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Transcribe audio
        job.current_task = "Transcribing audio..."
        job.progress = 10
        
        transcript = await video_processor.transcribe_audio(audio_path)
        
        # Split into scenes
        job.current_task = "Analyzing scenes..."
        job.progress = 20
        
        scenes = video_processor.split_text_into_scenes(transcript)
        
        if not scenes:
            raise Exception("Could not extract scenes from transcript")
        
        # Update job with prompts
        job.prompts = [ImagePrompt(prompt=scene, style=style, aspect_ratio=aspect_ratio) 
                      for scene in scenes]
        job.total_images = len(scenes)
        
        # Generate images for each scene
        generated_images = []
        for i, prompt_obj in enumerate(job.prompts):
            try:
                job.current_task = f"Generating scene {i+1}/{len(job.prompts)}"
                
                image_data = await generate_single_image(
                    prompt_obj.prompt, 
                    prompt_obj.style, 
                    prompt_obj.aspect_ratio
                )
                
                if image_data:
                    image_filename = f"scene_{i+1:03d}.png"
                    image_path = os.path.join(temp_dir, image_filename)
                    
                    with open(image_path, "wb") as f:
                        f.write(image_data)
                    
                    generated_images.append(image_path)
                    
                    # Update progress (20% + 60% for image generation)
                    job.progress = 20 + int(((i + 1) / len(job.prompts)) * 60)
                    
                    await asyncio.sleep(1)
                
            except Exception as e:
                print(f"Error generating image for scene {i+1}: {str(e)}")
                continue
        
        if generated_images:
            # Calculate scene durations
            job.current_task = "Calculating timing..."
            job.progress = 85
            
            # Get audio duration for proper timing
            from pydub import AudioSegment
            audio_segment = AudioSegment.from_file(audio_path)
            audio_duration = len(audio_segment) / 1000.0  # Convert to seconds
            
            scene_durations = video_processor.calculate_scene_durations(scenes, audio_duration)
            
            # Generate animation effects
            animation_effects = ["zoom_in", "zoom_out", "pan_right", "pan_left"] * (len(generated_images) // 4 + 1)
            animation_effects = animation_effects[:len(generated_images)]
            
            # Compile video with original audio
            job.current_task = "Compiling video..."
            job.progress = 90
            
            video_path = await video_processor.compile_video_from_images(
                generated_images,
                audio_path,
                scene_durations,
                animation_effects
            )
            
            job.video_file_path = video_path
            job.status = "completed"
            job.progress = 100
            job.current_task = "Video generation completed!"
            
        else:
            job.status = "failed"
            job.current_task = "Failed to generate images"
    
    except Exception as e:
        job.status = "failed"
        job.current_task = f"Voice-to-video generation failed: {str(e)}"
        print(f"Voice-to-video job {job_id} failed: {str(e)}")

@api_router.get("/job-status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_storage[job_id]
    return {
        "job_id": job_id,
        "status": job.status,
        "progress": job.progress,
        "total_images": job.total_images,
        "current_task": job.current_task,
        "job_type": job.job_type
    }

@api_router.get("/download/{job_id}")
async def download_zip(job_id: str):
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_storage[job_id]
    
    if job.status != "completed" or not job.zip_file_path:
        raise HTTPException(status_code=400, detail="Job not completed or no zip file available")
    
    if not os.path.exists(job.zip_file_path):
        raise HTTPException(status_code=404, detail="Zip file not found")
    
    return FileResponse(
        path=job.zip_file_path,
        filename=f"youtube_images_{job_id}.zip",
        media_type="application/zip"
    )

@api_router.get("/download-video/{job_id}")
async def download_video(job_id: str):
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_storage[job_id]
    
    if job.status != "completed" or not job.video_file_path:
        raise HTTPException(status_code=400, detail="Job not completed or no video file available")
    
    if not os.path.exists(job.video_file_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        path=job.video_file_path,
        filename=f"generated_video_{job_id}.mp4",
        media_type="video/mp4"
    )

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
#logs
