#!/usr/bin/env python3
"""
Backend Test Suite for YouTube Image Generator
Tests all API endpoints and functionality
"""

import requests
import json
import time
import tempfile
import csv
import os
from pathlib import Path

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

class YouTubeImageGeneratorTest:
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
                if "message" in data and "YouTube Image Generator API" in data["message"]:
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
        """Test 2: CSV upload functionality"""
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

    def test_invalid_csv_upload(self):
        """Test 2b: Invalid CSV upload (non-CSV file)"""
        try:
            # Create a text file instead of CSV
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("This is not a CSV file")
                txt_file_path = f.name
            
            try:
                with open(txt_file_path, 'rb') as f:
                    files = {'file': ('test.txt', f, 'text/plain')}
                    response = self.session.post(f"{API_URL}/upload-csv", files=files)
                
                if response.status_code == 400:
                    self.log_result("Invalid CSV Upload Rejection", True, 
                                  "Correctly rejected non-CSV file")
                    return True
                else:
                    self.log_result("Invalid CSV Upload Rejection", False, 
                                  f"Should reject non-CSV files, got HTTP {response.status_code}")
                    return False
                    
            finally:
                os.unlink(txt_file_path)
                
        except Exception as e:
            self.log_result("Invalid CSV Upload Rejection", False, f"Error: {str(e)}")
            return False

    def test_image_generation_endpoint(self):
        """Test 3: Image generation endpoint"""
        try:
            # Test with sample prompts
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
                                      f"Successfully started generation job: {data['job_id']}")
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

    def test_job_status_monitoring(self, job_id):
        """Test 4: Job status monitoring"""
        if not job_id:
            self.log_result("Job Status Monitoring", False, "No job_id provided")
            return False
            
        try:
            max_attempts = 30  # Wait up to 30 seconds
            attempt = 0
            
            while attempt < max_attempts:
                response = self.session.get(f"{API_URL}/job-status/{job_id}")
                
                if response.status_code == 200:
                    data = response.json()
                    if all(key in data for key in ["job_id", "status", "progress", "total_images"]):
                        status = data["status"]
                        progress = data["progress"]
                        
                        print(f"   Job {job_id}: {status} - {progress}% complete")
                        
                        if status == "completed":
                            self.log_result("Job Status Monitoring", True, 
                                          f"Job completed successfully with {progress}% progress")
                            return True
                        elif status == "failed":
                            self.log_result("Job Status Monitoring", False, 
                                          "Job failed during processing", data)
                            return False
                        elif status in ["pending", "processing"]:
                            time.sleep(2)  # Wait 2 seconds before checking again
                            attempt += 1
                            continue
                        else:
                            self.log_result("Job Status Monitoring", False, 
                                          f"Unknown status: {status}", data)
                            return False
                    else:
                        self.log_result("Job Status Monitoring", False, 
                                      "Response missing required fields", data)
                        return False
                else:
                    self.log_result("Job Status Monitoring", False, 
                                  f"HTTP {response.status_code}", response.text)
                    return False
            
            # If we get here, job didn't complete in time
            self.log_result("Job Status Monitoring", False, 
                          f"Job did not complete within {max_attempts * 2} seconds")
            return False
            
        except Exception as e:
            self.log_result("Job Status Monitoring", False, f"Error: {str(e)}")
            return False

    def test_invalid_job_status(self):
        """Test 4b: Invalid job status request"""
        try:
            fake_job_id = "non-existent-job-id"
            response = self.session.get(f"{API_URL}/job-status/{fake_job_id}")
            
            if response.status_code == 404:
                self.log_result("Invalid Job Status Request", True, 
                              "Correctly returned 404 for non-existent job")
                return True
            else:
                self.log_result("Invalid Job Status Request", False, 
                              f"Should return 404, got HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Invalid Job Status Request", False, f"Error: {str(e)}")
            return False

    def test_download_endpoint(self, job_id):
        """Test 5: Download endpoint for completed jobs"""
        if not job_id:
            self.log_result("Download Endpoint", False, "No job_id provided")
            return False
            
        try:
            response = self.session.get(f"{API_URL}/download/{job_id}")
            
            if response.status_code == 200:
                # Check if response is a zip file
                content_type = response.headers.get('content-type', '')
                if 'application/zip' in content_type or 'application/octet-stream' in content_type:
                    # Check if content looks like a zip file
                    content = response.content
                    if len(content) > 0 and content[:4] == b'PK\x03\x04':  # ZIP file signature
                        self.log_result("Download Endpoint", True, 
                                      f"Successfully downloaded zip file ({len(content)} bytes)")
                        return True
                    else:
                        self.log_result("Download Endpoint", False, 
                                      "Response content is not a valid zip file")
                        return False
                else:
                    self.log_result("Download Endpoint", False, 
                                  f"Unexpected content type: {content_type}")
                    return False
            elif response.status_code == 400:
                self.log_result("Download Endpoint", False, 
                              "Job not completed or no zip file available", response.text)
                return False
            elif response.status_code == 404:
                self.log_result("Download Endpoint", False, 
                              "Job or zip file not found", response.text)
                return False
            else:
                self.log_result("Download Endpoint", False, 
                              f"HTTP {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_result("Download Endpoint", False, f"Error: {str(e)}")
            return False

    def test_invalid_download(self):
        """Test 5b: Invalid download request"""
        try:
            fake_job_id = "non-existent-job-id"
            response = self.session.get(f"{API_URL}/download/{fake_job_id}")
            
            if response.status_code == 404:
                self.log_result("Invalid Download Request", True, 
                              "Correctly returned 404 for non-existent job")
                return True
            else:
                self.log_result("Invalid Download Request", False, 
                              f"Should return 404, got HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Invalid Download Request", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 60)
        print("YouTube Image Generator Backend Test Suite")
        print("=" * 60)
        print(f"Testing API at: {API_URL}")
        print()
        
        # Test 1: Basic API endpoint
        if not self.test_basic_api_endpoint():
            print("❌ Basic API test failed - stopping tests")
            return self.generate_summary()
        
        # Test 2: CSV upload functionality
        prompts = self.test_csv_upload_functionality()
        self.test_invalid_csv_upload()
        
        # Test 3: Image generation endpoint
        job_id = self.test_image_generation_endpoint()
        
        # Test 4: Job status monitoring
        job_completed = False
        if job_id:
            job_completed = self.test_job_status_monitoring(job_id)
        self.test_invalid_job_status()
        
        # Test 5: Download endpoint
        if job_id and job_completed:
            self.test_download_endpoint(job_id)
        self.test_invalid_download()
        
        return self.generate_summary()

    def generate_summary(self):
        """Generate test summary"""
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
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
    tester = YouTubeImageGeneratorTest()
    summary = tester.run_all_tests()