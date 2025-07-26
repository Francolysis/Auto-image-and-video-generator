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

class GenerationRequest(BaseModel):
    prompts: List[str]
    style: Optional[str] = "photorealistic"
    aspect_ratio: Optional[str] = "1:1"

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
                result = await response.json()
                if result.get("success") and result.get("result"):
                    # The image is returned as base64 encoded data
                    image_data = result["result"][0]  # First image from result
                    return base64.b64decode(image_data)
                else:
                    raise Exception(f"API returned no image data: {result}")
            else:
                error_text = await response.text()
                raise Exception(f"Cloudflare API error {response.status}: {error_text}")

@api_router.get("/")
async def root():
    return {"message": "YouTube Image Generator API"}

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
        total_images=len(request.prompts)
    )
    
    jobs_storage[job_id] = job
    
    # Start generation in background
    asyncio.create_task(process_image_generation(job_id))
    
    return {"job_id": job_id, "status": "started"}

async def process_image_generation(job_id: str):
    job = jobs_storage[job_id]
    job.status = "processing"
    
    # Create temp directory for images
    temp_dir = tempfile.mkdtemp()
    generated_images = []
    
    try:
        for i, prompt_obj in enumerate(job.prompts):
            try:
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
            zip_filename = f"youtube_images_{job_id}.zip"
            zip_path = os.path.join(temp_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for img_path in generated_images:
                    zipf.write(img_path, os.path.basename(img_path))
            
            job.zip_file_path = zip_path
            job.status = "completed"
        else:
            job.status = "failed"
    
    except Exception as e:
        job.status = "failed"
        print(f"Job {job_id} failed: {str(e)}")

@api_router.get("/job-status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_storage[job_id]
    return {
        "job_id": job_id,
        "status": job.status,
        "progress": job.progress,
        "total_images": job.total_images
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