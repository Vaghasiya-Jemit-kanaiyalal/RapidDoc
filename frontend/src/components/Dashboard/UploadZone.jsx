import React, { useState, useCallback } from 'react';
import { Upload, AlertTriangle, FileText, CheckCircle2, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { safeFetchJson } from '../../utils/api';

export const UploadZone = ({ token, onUploadSuccess }) => {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [splashData, setSplashData] = useState(null); // { type: 'pdf'|'docx', particles: [] }

  const triggerSplash = (type) => {
    const count = 14;
    const particles = Array.from({ length: count }).map((_, i) => {
      const angle = (i / count) * Math.PI * 2 + (Math.random() * 0.4 - 0.2);
      const distance = 80 + Math.random() * 90;
      return {
        id: i,
        x: Math.cos(angle) * distance,
        y: Math.sin(angle) * distance,
        scale: 0.8 + Math.random() * 0.5,
        rotation: (Math.random() - 0.5) * 60,
        type: i % 3 === 0 ? type : i % 3 === 1 ? 'dot' : 'sparkle',
      };
    });
    setSplashData({ type, particles });
    setTimeout(() => setSplashData(null), 1400);
  };

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
      setError('Invalid file format. Only PDF and DOCX files are supported.');
      return;
    }

    if (file.size > 15 * 1024 * 1024) {
      setError('File is too large. Maximum size limit is 15MB.');
      return;
    }

    // Trigger visual document splash
    triggerSplash(ext === 'pdf' ? 'pdf' : 'docx');

    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);
    try {
      const data = await safeFetchJson('/api/documents/upload', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });
      
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
    <div className="w-full relative">
      <motion.div
        whileHover={{ scale: 1.005 }}
        whileTap={{ scale: 0.998 }}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        className={`relative group border-2 border-dashed rounded-3xl p-8 sm:p-10 text-center transition-all duration-300 flex flex-col items-center justify-center cursor-pointer overflow-hidden ${
          dragActive 
            ? 'border-brand-500 bg-brand-50/60 shadow-soft-blue scale-[1.01]' 
            : 'border-borderline hover:border-brand-400 bg-white/70 hover:bg-white/90 shadow-card hover:shadow-card-hover'
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
        
        <label htmlFor="file-upload" className="w-full h-full flex flex-col items-center justify-center cursor-pointer relative z-10">
          {/* Animated Upload Icon Badge with Splash Center */}
          <div className="relative">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-brand-50 to-indigo-50 border border-brand-100/80 text-brand-600 flex items-center justify-center group-hover:scale-110 transition-transform duration-300 shadow-sm mb-4">
              <Upload className="w-7 h-7 text-brand-600" />
            </div>

            {/* Particle Splash Animation */}
            <AnimatePresence>
              {splashData && (
                <div className="absolute inset-0 pointer-events-none flex items-center justify-center z-30">
                  {splashData.particles.map((p) => {
                    const isPdf = splashData.type === 'pdf';
                    return (
                      <motion.div
                        key={p.id}
                        initial={{ opacity: 1, x: 0, y: 0, scale: 0.2 }}
                        animate={{
                          opacity: [1, 1, 0],
                          x: p.x,
                          y: p.y,
                          scale: [0.2, p.scale, 0],
                          rotate: p.rotation,
                        }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
                        className="absolute"
                      >
                        {p.type === 'pdf' ? (
                          <div className="px-2 py-0.5 rounded-md bg-white border border-red-400 text-red-600 text-[9px] font-extrabold shadow-md flex items-center gap-0.5">
                            <span className="w-1 h-1 rounded-full bg-red-500" /> PDF
                          </div>
                        ) : p.type === 'docx' ? (
                          <div className="px-2 py-0.5 rounded-md bg-white border border-blue-400 text-blue-600 text-[9px] font-extrabold shadow-md flex items-center gap-0.5">
                            <span className="w-1 h-1 rounded-full bg-blue-500" /> DOC
                          </div>
                        ) : p.type === 'sparkle' ? (
                          <Sparkles className={`w-4 h-4 ${isPdf ? 'text-red-400 fill-red-400' : 'text-blue-400 fill-blue-400'}`} />
                        ) : (
                          <div className={`w-2.5 h-2.5 rounded-full ${isPdf ? 'bg-red-400' : 'bg-blue-400'} shadow-sm`} />
                        )}
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </AnimatePresence>
          </div>
          
          <h3 className="font-extrabold text-lg text-ink mb-1.5">
            {uploading ? 'Processing your document...' : 'Upload your document'}
          </h3>
          <p className="text-sm text-secondary mb-4 max-w-sm">
            Drag and drop your file here, or <span className="text-brand-600 font-bold hover:underline">browse from device</span>
          </p>

          {/* Supported Format Pills */}
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50/80 border border-red-100 px-3 py-1 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" /> PDF Document
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-blue-600 bg-blue-50/80 border border-blue-100 px-3 py-1 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500" /> Word DOCX
            </span>
            <span className="text-[11px] text-secondary font-medium bg-slate-100/80 px-2.5 py-1 rounded-full">
              Up to 15MB
            </span>
          </div>
        </label>

        {/* Uploading Overlay */}
        {uploading && (
          <div className="absolute inset-0 bg-white/85 backdrop-blur-md rounded-3xl flex flex-col items-center justify-center z-20">
            <div className="w-12 h-12 border-4 border-brand-600 border-t-transparent rounded-full animate-spin mb-3"></div>
            <p className="text-sm font-bold text-ink">Extracting & analyzing document...</p>
            <p className="text-xs text-secondary mt-1">Applying OCR & AI intent parser</p>
          </div>
        )}
      </motion.div>

      {error && (
        <motion.div 
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 p-4 bg-amber-50 border border-amber-200/80 rounded-2xl text-amber-800 text-sm flex items-start gap-3"
        >
          <AlertTriangle className="w-5 h-5 flex-shrink-0 text-amber-600 mt-0.5" />
          <div className="flex-grow">
            <p className="font-bold text-xs">Upload Alert</p>
            <p className="text-xs mt-0.5">{error}</p>
          </div>
        </motion.div>
      )}
    </div>
  );
};
