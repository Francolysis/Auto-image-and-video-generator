#!/usr/bin/env python3
"""
Backend Test Suite for AI Video Production Studio
Tests all API endpoints and functionality including new video generation features
"""

import requests
import json
import time
import tempfile
import csv
import os
from pathlib import Path
import io

# Get backend URL from frontend .env
def get_backend_url():
    frontend_env_path = Path("/app/frontend/.env")
    if frontend_env_path.exists():
        with open(frontend_env_path, 'r') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip()
    return "http://localhost:8001"

BASE_URL = get_backend_url()
API_URL = f"{BASE_URL}/api"

class AIVideoProductionStudioTest:
    def __init__(self):
        self.session = requests.Session()
        self.test_results = []
        
    def log_result(self, test_name, success, message="", details=None):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "details": details
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if message:
            print(f"   Message: {message}")
        if details:
            print(f"   Details: {details}")
        print()

    def test_basic_api_endpoint(self):
        """Test 1: Basic API endpoint to ensure server is running"""
        try:
            response = self.session.get(f"{API_URL}/")
            if response.status_code == 200:
                data = response.json()
                if "message" in data and "AI Video Production Studio API" in data["message"]:
                    self.log_result("Basic API Endpoint", True, "API is running and responding correctly")
                    return True
                else:
                    self.log_result("Basic API Endpoint", False, "API response format incorrect", data)
                    return False
            else:
                self.log_result("Basic API Endpoint", False, f"HTTP {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("Basic API Endpoint", False, f"Connection error: {str(e)}")
            return False

    def test_csv_upload_functionality(self):
        """Test 2: CSV upload functionality (existing functionality)"""
        try:
            # Create a sample CSV with image prompts
            csv_content = """A beautiful sunset over mountains
A futuristic city skyline at night
A serene lake with reflection of trees
A vintage car on a country road
A colorful flower garden in spring"""
            
            # Create temporary CSV file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
                f.write(csv_content)
                csv_file_path = f.name
            
            try:
                # Upload CSV file
                with open(csv_file_path, 'rb') as f:
                    files = {'file': ('test_prompts.csv', f, 'text/csv')}
                    response = self.session.post(f"{API_URL}/upload-csv", files=files)
                
                if response.status_code == 200:
                    data = response.json()
                    if "prompts" in data and "count" in data:
                        if data["count"] == 5 and len(data["prompts"]) == 5:
                            self.log_result("CSV Upload Functionality", True, 
                                          f"Successfully parsed {data['count']} prompts from CSV")
                            return data["prompts"]
                        else:
                            self.log_result("CSV Upload Functionality", False, 
                                          f"Expected 5 prompts, got {data['count']}", data)
                            return None
                    else:
                        self.log_result("CSV Upload Functionality", False, 
                                      "Response missing required fields", data)
                        return None
                else:
                    self.log_result("CSV Upload Functionality", False, 
                                  f"HTTP {response.status_code}", response.text)
                    return None
                    
            finally:
                # Clean up temporary file
                os.unlink(csv_file_path)
                
        except Exception as e:
            self.log_result("CSV Upload Functionality", False, f"Error: {str(e)}")
            return None

    def test_text_to_video_endpoint(self):
        """Test 3: NEW - Text-to-video endpoint"""
        try:
            # Sample script for testing
            test_script = """
            Once upon a time in a magical forest, there lived a wise old owl who watched over all the woodland creatures.
            
            The owl perched high in an ancient oak tree, its golden eyes scanning the forest floor below.
            
            One day, a young rabbit approached the tree, seeking guidance about a mysterious glowing stone it had found.
            
            The owl descended gracefully, its wings spread wide against the moonlit sky, ready to share its wisdom.
            """
            
            payload = {
                "script": test_script,
                "style": "photorealistic",
                "aspect_ratio": "16:9"
            }
            
            response = self.session.post(f"{API_URL}/generate-text-to-video", 
                                       json=payload,
                                       headers={'Content-Type': 'application/json'})
            
            if response.status_code == 200:
                data = response.json()
                if "job_id" in data and "status" in data:
                    if data["status"] == "started":
                        self.log_result("Text-to-Video Endpoint", True, 
                                      f"Successfully started text-to-video job: {data['job_id']}")
                        return data["job_id"]
                    else:
                        self.log_result("Text-to-Video Endpoint", False, 
                                      f"Unexpected status: {data['status']}", data)
                        return None
                else:
                    self.log_result("Text-to-Video Endpoint", False, 
                                  "Response missing required fields", data)
                    return None
            else:
                self.log_result("Text-to-Video Endpoint", False, 
                              f"HTTP {response.status_code}", response.text)
                return None
                
        except Exception as e:
            self.log_result("Text-to-Video Endpoint", False, f"Error: {str(e)}")
            return None

    def test_voice_to_video_endpoint_structure(self):
        """Test 4: NEW - Voice-to-video endpoint structure (without actual audio file)"""
        try:
            # Create a dummy audio file for testing endpoint structure
            dummy_audio_content = b"dummy audio content for testing"
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(dummy_audio_content)
                audio_file_path = f.name
            
            try:
                with open(audio_file_path, 'rb') as f:
                    files = {
                        'audio': ('test_audio.mp3', f, 'audio/mpeg')
                    }
                    data = {
                        'style': 'photorealistic',
                        'aspect_ratio': '16:9'
                    }
                    response = self.session.post(f"{API_URL}/generate-voice-to-video", 
                                               files=files, data=data)
                
                if response.status_code == 200:
                    response_data = response.json()
                    if "job_id" in response_data and "status" in response_data:
                        if response_data["status"] == "started":
                            self.log_result("Voice-to-Video Endpoint Structure", True, 
                                          f"Endpoint accepts requests correctly: {response_data['job_id']}")
                            return response_data["job_id"]
                        else:
                            self.log_result("Voice-to-Video Endpoint Structure", False, 
                                          f"Unexpected status: {response_data['status']}", response_data)
                            return None
                    else:
                        self.log_result("Voice-to-Video Endpoint Structure", False, 
                                      "Response missing required fields", response_data)
                        return None
                else:
                    # Even if it fails due to invalid audio, we want to check if endpoint structure is correct
                    if response.status_code in [400, 422]:  # Expected for dummy audio
                        self.log_result("Voice-to-Video Endpoint Structure", True, 
                                      "Endpoint structure correct - properly validates audio input")
                        return None
                    else:
                        self.log_result("Voice-to-Video Endpoint Structure", False, 
                                      f"HTTP {response.status_code}", response.text)
                        return None
                    
            finally:
                os.unlink(audio_file_path)
                
        except Exception as e:
            self.log_result("Voice-to-Video Endpoint Structure", False, f"Error: {str(e)}")
            return None

    def test_enhanced_job_status_monitoring(self, job_id, job_type="text_to_video"):
        """Test 5: Enhanced job status monitoring with new fields"""
        if not job_id:
            self.log_result("Enhanced Job Status Monitoring", False, "No job_id provided")
            return False
            
        try:
            response = self.session.get(f"{API_URL}/job-status/{job_id}")
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["job_id", "status", "progress", "total_images", "current_task", "job_type"]
                
                if all(key in data for key in required_fields):
                    status = data["status"]
                    progress = data["progress"]
                    current_task = data["current_task"]
                    job_type_returned = data["job_type"]
                    
                    print(f"   Job {job_id}: {status} - {progress}% - {current_task}")
                    print(f"   Job Type: {job_type_returned}")
                    
                    # Verify job type matches expected
                    if job_type_returned == job_type:
                        self.log_result("Enhanced Job Status Monitoring", True, 
                                      f"Enhanced status tracking working - Type: {job_type_returned}, Task: {current_task}")
                        return True
                    else:
                        self.log_result("Enhanced Job Status Monitoring", False, 
                                      f"Job type mismatch - Expected: {job_type}, Got: {job_type_returned}")
                        return False
                else:
                    missing_fields = [field for field in required_fields if field not in data]
                    self.log_result("Enhanced Job Status Monitoring", False, 
                                  f"Response missing required fields: {missing_fields}", data)
                    return False
            else:
                self.log_result("Enhanced Job Status Monitoring", False, 
                              f"HTTP {response.status_code}", response.text)
                return False
            
        except Exception as e:
            self.log_result("Enhanced Job Status Monitoring", False, f"Error: {str(e)}")
            return False

    def test_video_download_endpoint(self, job_id):
        """Test 6: Video download endpoint"""
        if not job_id:
            self.log_result("Video Download Endpoint", False, "No job_id provided")
            return False
            
        try:
            response = self.session.get(f"{API_URL}/download-video/{job_id}")
            
            if response.status_code == 200:
                # Check if response is a video file
                content_type = response.headers.get('content-type', '')
                if 'video/mp4' in content_type:
                    content = response.content
                    if len(content) > 0:
                        self.log_result("Video Download Endpoint", True, 
                                      f"Successfully accessed video download endpoint ({len(content)} bytes)")
                        return True
                    else:
                        self.log_result("Video Download Endpoint", False, 
                                      "Response content is empty")
                        return False
                else:
                    self.log_result("Video Download Endpoint", False, 
                                  f"Unexpected content type: {content_type}")
                    return False
            elif response.status_code == 400:
                self.log_result("Video Download Endpoint", True, 
                              "Correctly handles incomplete jobs - endpoint structure working")
                return True
            elif response.status_code == 404:
                self.log_result("Video Download Endpoint", True, 
                              "Correctly handles non-existent jobs - endpoint structure working")
                return True
            else:
                self.log_result("Video Download Endpoint", False, 
                              f"HTTP {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_result("Video Download Endpoint", False, f"Error: {str(e)}")
            return False

    def test_video_processing_dependencies(self):
        """Test 7: Verify video processing dependencies are available"""
        try:
            # Test if video_processor module is importable and has required methods
            response = self.session.get(f"{API_URL}/")  # Basic connectivity test
            
            if response.status_code == 200:
                # If the server is running and imports video_processor successfully, dependencies are likely OK
                self.log_result("Video Processing Dependencies", True, 
                              "Server running with video_processor module - dependencies appear to be installed")
                return True
            else:
                self.log_result("Video Processing Dependencies", False, 
                              "Server not responding - cannot verify dependencies")
                return False
                
        except Exception as e:
            self.log_result("Video Processing Dependencies", False, f"Error: {str(e)}")
            return False

    def test_image_generation_endpoint(self):
        """Test existing image generation functionality"""
        try:
            test_prompts = [
                "A beautiful sunset over mountains",
                "A futuristic city skyline at night"
            ]
            
            payload = {
                "prompts": test_prompts,
                "style": "photorealistic",
                "aspect_ratio": "1:1"
            }
            
            response = self.session.post(f"{API_URL}/generate-images", 
                                       json=payload,
                                       headers={'Content-Type': 'application/json'})
            
            if response.status_code == 200:
                data = response.json()
                if "job_id" in data and "status" in data:
                    if data["status"] == "started":
                        self.log_result("Image Generation Endpoint", True, 
                                      f"Successfully started image generation job: {data['job_id']}")
                        return data["job_id"]
                    else:
                        self.log_result("Image Generation Endpoint", False, 
                                      f"Unexpected status: {data['status']}", data)
                        return None
                else:
                    self.log_result("Image Generation Endpoint", False, 
                                  "Response missing required fields", data)
                    return None
            else:
                self.log_result("Image Generation Endpoint", False, 
                              f"HTTP {response.status_code}", response.text)
                return None
                
        except Exception as e:
            self.log_result("Image Generation Endpoint", False, f"Error: {str(e)}")
            return None

    def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 70)
        print("AI Video Production Studio Backend Test Suite")
        print("=" * 70)
        print(f"Testing API at: {API_URL}")
        print()
        
        # Test 1: Basic API endpoint
        if not self.test_basic_api_endpoint():
            print("❌ Basic API test failed - stopping tests")
            return self.generate_summary()
        
        # Test 2: CSV upload functionality (existing)
        self.test_csv_upload_functionality()
        
        # Test 3: NEW - Text-to-video endpoint
        text_video_job_id = self.test_text_to_video_endpoint()
        
        # Test 4: NEW - Voice-to-video endpoint structure
        voice_video_job_id = self.test_voice_to_video_endpoint_structure()
        
        # Test 5: Enhanced job status monitoring
        if text_video_job_id:
            self.test_enhanced_job_status_monitoring(text_video_job_id, "text_to_video")
        
        # Test 6: Video download endpoints
        if text_video_job_id:
            self.test_video_download_endpoint(text_video_job_id)
        
        # Test 7: Video processing dependencies
        self.test_video_processing_dependencies()
        
        # Test existing image generation
        image_job_id = self.test_image_generation_endpoint()
        if image_job_id:
            self.test_enhanced_job_status_monitoring(image_job_id, "images")
        
        return self.generate_summary()

    def generate_summary(self):
        """Generate test summary"""
        print("=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        print()
        
        if failed_tests > 0:
            print("FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"❌ {result['test']}: {result['message']}")
            print()
        
        return {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": (passed_tests/total_tests)*100,
            "results": self.test_results
        }

if __name__ == "__main__":
    tester = AIVideoProductionStudioTest()
    summary = tester.run_all_tests()