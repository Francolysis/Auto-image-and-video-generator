import React, { useState, useRef } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [csvFile, setCsvFile] = useState(null);
  const [prompts, setPrompts] = useState([]);
  const [style, setStyle] = useState("photorealistic");
  const [aspectRatio, setAspectRatio] = useState("1:1");
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [jobId, setJobId] = useState(null);
  const [downloadReady, setDownloadReady] = useState(false);
  const fileInputRef = useRef(null);

  const styles = [
    "photorealistic",
    "artistic",
    "cartoon",
    "anime",
    "oil painting",
    "watercolor",
    "digital art",
    "sketch",
    "vintage",
    "modern"
  ];

  const aspectRatios = [
    "1:1", "16:9", "9:16", "4:3", "3:4", "21:9"
  ];

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setCsvFile(file);
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API}/upload-csv`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      setPrompts(response.data.prompts);
    } catch (error) {
      alert('Error uploading CSV: ' + (error.response?.data?.detail || error.message));
    }
  };

  const startGeneration = async () => {
    if (prompts.length === 0) {
      alert('Please upload a CSV file first');
      return;
    }

    setIsGenerating(true);
    setProgress(0);
    setDownloadReady(false);

    try {
      const response = await axios.post(`${API}/generate-images`, {
        prompts: prompts,
        style: style,
        aspect_ratio: aspectRatio
      });

      const newJobId = response.data.job_id;
      setJobId(newJobId);
      
      // Poll for progress
      pollJobStatus(newJobId);
    } catch (error) {
      alert('Error starting generation: ' + (error.response?.data?.detail || error.message));
      setIsGenerating(false);
    }
  };

  const pollJobStatus = async (jobId) => {
    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`${API}/job-status/${jobId}`);
        const status = response.data;
        
        setProgress(status.progress);
        
        if (status.status === 'completed') {
          clearInterval(interval);
          setIsGenerating(false);
          setDownloadReady(true);
        } else if (status.status === 'failed') {
          clearInterval(interval);
          setIsGenerating(false);
          alert('Generation failed. Please try again.');
        }
      } catch (error) {
        clearInterval(interval);
        setIsGenerating(false);
        alert('Error checking status: ' + error.message);
      }
    }, 2000);
  };

  const downloadZip = () => {
    if (jobId) {
      window.open(`${API}/download/${jobId}`, '_blank');
    }
  };

  const resetApp = () => {
    setCsvFile(null);
    setPrompts([]);
    setProgress(0);
    setJobId(null);
    setDownloadReady(false);
    setIsGenerating(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-6xl font-bold text-white mb-4">
            🎬 YouTube Image Generator
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto">
            Transform your storytelling prompts into stunning visuals. Upload your CSV, select your style, and generate professional images for your videos.
          </p>
        </div>

        {/* Main Content */}
        <div className="max-w-4xl mx-auto">
          {/* Upload Section */}
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 mb-8 border border-white/20">
            <h2 className="text-2xl font-bold text-white mb-4 flex items-center">
              📁 Upload Your Prompts
            </h2>
            <div className="space-y-4">
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleFileUpload}
                  className="hidden"
                  id="csvInput"
                />
                <label
                  htmlFor="csvInput"
                  className="block w-full p-4 border-2 border-dashed border-white/30 rounded-lg text-center cursor-pointer hover:border-white/50 transition-colors"
                >
                  <div className="text-white">
                    {csvFile ? (
                      <span className="text-green-300">✅ {csvFile.name}</span>
                    ) : (
                      <span>Click to upload CSV file or drag and drop</span>
                    )}
                  </div>
                </label>
              </div>
              
              {prompts.length > 0 && (
                <div className="bg-green-500/20 rounded-lg p-4">
                  <p className="text-green-300 font-semibold">
                    ✅ {prompts.length} prompts loaded successfully!
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Settings Section */}
          {prompts.length > 0 && (
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 mb-8 border border-white/20">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center">
                🎨 Generation Settings
              </h2>
              
              <div className="grid md:grid-cols-2 gap-6">
                {/* Style Selection */}
                <div>
                  <label className="block text-white font-semibold mb-3">Art Style</label>
                  <select
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                    className="w-full p-3 rounded-lg bg-white/20 text-white border border-white/30 focus:border-blue-400 focus:outline-none"
                  >
                    {styles.map((s) => (
                      <option key={s} value={s} className="bg-gray-800">
                        {s.charAt(0).toUpperCase() + s.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Aspect Ratio Selection */}
                <div>
                  <label className="block text-white font-semibold mb-3">Aspect Ratio</label>
                  <select
                    value={aspectRatio}
                    onChange={(e) => setAspectRatio(e.target.value)}
                    className="w-full p-3 rounded-lg bg-white/20 text-white border border-white/30 focus:border-blue-400 focus:outline-none"
                  >
                    {aspectRatios.map((ratio) => (
                      <option key={ratio} value={ratio} className="bg-gray-800">
                        {ratio}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Generation Section */}
          {prompts.length > 0 && (
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 mb-8 border border-white/20">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center">
                🚀 Generate Images
              </h2>
              
              {!isGenerating && !downloadReady && (
                <button
                  onClick={startGeneration}
                  className="w-full bg-gradient-to-r from-purple-600 to-blue-600 text-white font-bold py-4 px-8 rounded-lg hover:from-purple-700 hover:to-blue-700 transform hover:scale-105 transition-all duration-200 shadow-lg"
                >
                  🎨 Generate {prompts.length} Images
                </button>
              )}

              {isGenerating && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between text-white">
                    <span>Generating images...</span>
                    <span>{progress}%</span>
                  </div>
                  <div className="w-full bg-white/20 rounded-full h-3">
                    <div
                      className="bg-gradient-to-r from-green-400 to-blue-500 h-3 rounded-full transition-all duration-500"
                      style={{ width: `${progress}%` }}
                    ></div>
                  </div>
                  <p className="text-gray-300 text-center">
                    This may take a few minutes. Please don't close this page.
                  </p>
                </div>
              )}

              {downloadReady && (
                <div className="space-y-4">
                  <div className="bg-green-500/20 rounded-lg p-6 text-center">
                    <div className="text-4xl mb-2">🎉</div>
                    <h3 className="text-xl font-bold text-green-300 mb-2">
                      Generation Complete!
                    </h3>
                    <p className="text-green-200">
                      Your {prompts.length} images are ready for download.
                    </p>
                  </div>
                  
                  <div className="flex space-x-4">
                    <button
                      onClick={downloadZip}
                      className="flex-1 bg-gradient-to-r from-green-600 to-teal-600 text-white font-bold py-4 px-8 rounded-lg hover:from-green-700 hover:to-teal-700 transform hover:scale-105 transition-all duration-200 shadow-lg"
                    >
                      📥 Download ZIP File
                    </button>
                    <button
                      onClick={resetApp}
                      className="flex-1 bg-gradient-to-r from-gray-600 to-gray-700 text-white font-bold py-4 px-8 rounded-lg hover:from-gray-700 hover:to-gray-800 transform hover:scale-105 transition-all duration-200 shadow-lg"
                    >
                      🔄 Start New Generation
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Prompts Preview */}
          {prompts.length > 0 && (
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 border border-white/20">
              <h3 className="text-xl font-bold text-white mb-4">
                📝 Loaded Prompts ({prompts.length})
              </h3>
              <div className="max-h-60 overflow-y-auto space-y-2">
                {prompts.slice(0, 10).map((prompt, index) => (
                  <div key={index} className="bg-white/5 rounded-lg p-3">
                    <span className="text-blue-300 font-mono text-sm">#{index + 1}</span>
                    <span className="text-white ml-2">{prompt}</span>
                  </div>
                ))}
                {prompts.length > 10 && (
                  <div className="text-gray-400 text-center py-2">
                    ... and {prompts.length - 10} more prompts
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;