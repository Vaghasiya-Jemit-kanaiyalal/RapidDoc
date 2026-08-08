import React, { useState, useCallback } from 'react';
import { Upload, AlertTriangle } from 'lucide-react';

export const UploadZone = ({ token, onUploadSuccess }) => {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const uploadFile = async (file) => {
    setError('');
    
    // File validation
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'pdf' && ext !== 'docx') {
      setError('Invalid file type. Only PDF and DOCX files are allowed.');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError('File is too large. Maximum size allowed is 10MB.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);
    try {
      const response = await fetch('http://localhost:8000/api/documents/upload', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || 'Upload failed');
      }

      if (onUploadSuccess) {
        onUploadSuccess(data);
      }
    } catch (err) {
      setError(err.message || 'Error uploading document.');
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadFile(e.dataTransfer.files[0]);
    }
  }, [token]);

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      uploadFile(e.target.files[0]);
    }
  };

  return (
    <div className="w-full">
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        className={`relative group border-2 border-dashed rounded-3xl p-8 text-center transition flex flex-col items-center justify-center cursor-pointer ${
          dragActive 
            ? 'border-blue-500 bg-blue-50/50' 
            : 'border-slate-200 hover:border-blue-400 bg-white/50 hover:bg-white/80'
        }`}
      >
        <input
          type="file"
          id="file-upload"
          multiple={false}
          onChange={handleChange}
          accept=".pdf,.docx"
          className="hidden"
          disabled={uploading}
        />
        
        <label htmlFor="file-upload" className="w-full h-full flex flex-col items-center justify-center cursor-pointer">
          <div className="p-4 bg-blue-50 text-blue-600 rounded-2xl group-hover:scale-110 transition duration-200 shadow-sm mb-4">
            <Upload className="w-6 h-6 animate-pulse" />
          </div>
          
          <h3 className="font-bold text-slate-800 mb-1">
            {uploading ? 'Uploading your document...' : 'Upload your document'}
          </h3>
          <p className="text-sm text-slate-500 mb-2">
            Drag and drop your file here, or <span className="text-blue-600 font-semibold hover:underline">browse</span>
          </p>
          <span className="text-xs text-slate-400 bg-slate-100/80 px-3 py-1 rounded-full">
            PDF or DOCX (max 10MB)
          </span>
        </label>

        {uploading && (
          <div className="absolute inset-0 bg-white/70 backdrop-blur-[2px] rounded-3xl flex flex-col items-center justify-center">
            <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mb-2"></div>
            <p className="text-sm font-semibold text-slate-700">Processing file...</p>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-2xl text-amber-800 text-sm flex items-start gap-2.5">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
};
