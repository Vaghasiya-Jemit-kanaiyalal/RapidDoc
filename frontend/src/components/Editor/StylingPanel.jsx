import React, { useState } from 'react';
import { Type, ALargeSmall, AlignLeft, Image as ImageIcon, Save, ArrowLeft, Loader2, Sparkles, Sliders } from 'lucide-react';
import { motion } from 'framer-motion';
import { API_URL, getAuthHeaders } from '../../utils/api';

export const StylingPanel = ({ 
  document: doc, 
  token, 
  onBack, 
  onSaveSuccess,
  fontName: propFontName,
  setFontName: propSetFontName,
  fontSize: propFontSize,
  setFontSize: propSetFontSize
}) => {
  const [localFontName, setLocalFontName] = useState('Arial');
  const [localFontSize, setLocalFontSize] = useState(12);

  const fontName = propFontName !== undefined ? propFontName : localFontName;
  const setFontName = propSetFontName !== undefined ? propSetFontName : setLocalFontName;
  const fontSize = propFontSize !== undefined ? propFontSize : localFontSize;
  const setFontSize = propSetFontSize !== undefined ? propSetFontSize : setLocalFontSize;

  const [headerText, setHeaderText] = useState('');
  const [footerText, setFooterText] = useState('');
  const [replaceIndex, setReplaceIndex] = useState(0);
  const [imageFile, setImageFile] = useState(null);
  
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const fonts = ['Arial', 'Times New Roman', 'Calibri', 'Courier New', 'Inter', 'Georgia'];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');
    setSaving(true);

    const formData = new FormData();
    if (fontName) formData.append('font_name', fontName);
    if (fontSize) formData.append('font_size', fontSize);
    if (headerText) formData.append('header_text', headerText);
    if (footerText) formData.append('footer_text', footerText);
    
    // Add image replacement if file chosen
    if (imageFile !== null && doc.images_count > 0) {
      formData.append('replace_image_index', replaceIndex);
      formData.append('image_file', imageFile);
    }

    try {
      const response = await fetch(`${API_URL}/documents/${doc.id}/style`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to update style');
      }

      setSuccessMsg('Style changes applied successfully!');
      setImageFile(null);
      
      if (onSaveSuccess) {
        onSaveSuccess(data);
      }
    } catch (err) {
      setError(err.message || 'Error updating styles.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="w-full max-w-sm flex flex-col h-full bg-white/90 backdrop-blur-xl border-l border-borderline/80 p-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6 pb-4 border-b border-borderline/60">
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          onClick={onBack}
          className="p-2 hover:bg-slate-100 rounded-xl transition text-secondary hover:text-ink cursor-pointer"
          title="Back"
        >
          <ArrowLeft className="w-4 h-4" />
        </motion.button>
        <div>
          <h3 className="font-extrabold text-ink text-base flex items-center gap-1.5">
            <Sliders className="w-4 h-4 text-brand-600" />
            <span>Document Styling</span>
          </h3>
          <p className="text-xs text-secondary truncate max-w-[200px]">{doc.name}</p>
        </div>
      </div>

      {error && (
        <motion.div 
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-4 p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-semibold"
        >
          {error}
        </motion.div>
      )}

      {successMsg && (
        <motion.div 
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-4 p-3.5 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs rounded-2xl font-semibold flex items-center gap-1.5"
        >
          <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
          <span>{successMsg}</span>
        </motion.div>
      )}

      <form onSubmit={handleSubmit} className="flex-grow space-y-5">
        {/* Font Family */}
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-bold text-ink">
            <Type className="w-3.5 h-3.5 text-brand-600" />
            <span>Font Family</span>
          </label>
          <select
            value={fontName}
            onChange={(e) => setFontName(e.target.value)}
            className="w-full px-3.5 py-2.5 bg-slate-50 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-xl outline-none transition text-sm text-ink font-medium shadow-2xs"
          >
            {fonts.map(font => (
              <option key={font} value={font}>{font}</option>
            ))}
          </select>
        </div>

        {/* Font Size */}
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-bold text-ink">
            <ALargeSmall className="w-3.5 h-3.5 text-brand-600" />
            <span>Font Size (pt)</span>
          </label>
          <input
            type="number"
            min="6"
            max="72"
            value={fontSize}
            onChange={(e) => setFontSize(parseFloat(e.target.value) || 12)}
            className="w-full px-3.5 py-2.5 bg-slate-50 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-xl outline-none transition text-sm text-ink font-medium shadow-2xs"
          />
        </div>

        {/* Header Text */}
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-bold text-ink">
            <AlignLeft className="w-3.5 h-3.5 text-brand-600" />
            <span>Header Content</span>
          </label>
          <input
            type="text"
            value={headerText}
            onChange={(e) => setHeaderText(e.target.value)}
            placeholder="Document header title..."
            className="w-full px-3.5 py-2.5 bg-slate-50 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-xl outline-none transition text-sm text-ink font-medium shadow-2xs placeholder:text-slate-400"
          />
        </div>

        {/* Footer Text */}
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-bold text-ink">
            <AlignLeft className="w-3.5 h-3.5 text-brand-600 rotate-180" />
            <span>Footer Content</span>
          </label>
          <input
            type="text"
            value={footerText}
            onChange={(e) => setFooterText(e.target.value)}
            placeholder="Page numbering or footer note..."
            className="w-full px-3.5 py-2.5 bg-slate-50 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-xl outline-none transition text-sm text-ink font-medium shadow-2xs placeholder:text-slate-400"
          />
        </div>

        {/* Image Replacement */}
        {doc.images_count > 0 ? (
          <div className="p-4 bg-slate-50/80 border border-borderline rounded-2xl space-y-3">
            <div className="flex items-center gap-1.5 text-xs font-bold text-ink">
              <ImageIcon className="w-4 h-4 text-brand-600" />
              <span>Replace Document Image</span>
            </div>
            
            <div className="space-y-1">
              <label className="block text-[11px] text-secondary font-bold">Select image index:</label>
              <select
                value={replaceIndex}
                onChange={(e) => setReplaceIndex(parseInt(e.target.value))}
                className="w-full px-3 py-2 bg-white border border-borderline rounded-xl outline-none transition text-xs text-ink font-medium"
              >
                {Array.from({ length: doc.images_count }).map((_, idx) => (
                  <option key={idx} value={idx}>Image #{idx + 1}</option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="block text-[11px] text-secondary font-bold">Upload replacement:</label>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setImageFile(e.target.files[0] || null)}
                className="w-full text-xs text-secondary file:mr-3 file:py-1.5 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-brand-50 file:text-brand-600 hover:file:bg-brand-100 cursor-pointer"
              />
            </div>
          </div>
        ) : (
          <div className="p-4 bg-slate-50 border border-borderline/60 rounded-2xl text-center text-xs text-secondary">
            No image files detected in this document.
          </div>
        )}

        {/* Save button */}
        <motion.button
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          type="submit"
          disabled={saving}
          className="w-full py-3.5 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white font-bold rounded-2xl shadow-soft-blue flex items-center justify-center gap-2 transition duration-300 disabled:opacity-50 mt-6 cursor-pointer"
        >
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Applying Styles...</span>
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              <span>Apply & Save Changes</span>
            </>
          )}
        </motion.button>
      </form>
    </div>
  );
};
