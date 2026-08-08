import React, { useState } from 'react';
import { Type, ALargeSmall, AlignLeft, Image as ImageIcon, Save, ArrowLeft, Loader2 } from 'lucide-react';

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

  const fonts = ['Arial', 'Times New Roman', 'Calibri', 'Courier New'];

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
      const response = await fetch(`http://localhost:8000/api/documents/${doc.id}/style`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to update style');
      }

      setSuccessMsg('Style changes applied successfully!');
      setImageFile(null); // Clear input file after success
      
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
    <div className="w-full max-w-sm flex flex-col h-full bg-white border-l border-slate-100 p-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
        <button
          onClick={onBack}
          className="p-2 hover:bg-slate-100 rounded-xl transition text-slate-500"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h3 className="font-bold text-slate-800 text-base">Styling Panel</h3>
          <p className="text-xs text-slate-400 truncate max-w-[200px]">{doc.name}</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-100 text-red-700 text-xs rounded-xl">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="mb-4 p-3 bg-emerald-50 border border-emerald-100 text-emerald-700 text-xs rounded-xl">
          {successMsg}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex-grow space-y-6">
        {/* Font Family */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
            <Type className="w-4 h-4 text-slate-400" />
            <span>Font Family</span>
          </label>
          <select
            value={fontName}
            onChange={(e) => setFontName(e.target.value)}
            className="w-full px-3.5 py-3 bg-slate-50 border border-slate-200 focus:border-blue-500 rounded-xl outline-none transition text-sm text-slate-700"
          >
            {fonts.map(font => (
              <option key={font} value={font}>{font}</option>
            ))}
          </select>
        </div>

        {/* Font Size */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
            <ALargeSmall className="w-4 h-4 text-slate-400" />
            <span>Font Size (pt)</span>
          </label>
          <input
            type="number"
            min="6"
            max="72"
            value={fontSize}
            onChange={(e) => setFontSize(parseFloat(e.target.value) || 12)}
            className="w-full px-3.5 py-3 bg-slate-50 border border-slate-200 focus:border-blue-500 rounded-xl outline-none transition text-sm text-slate-700"
          />
        </div>

        {/* Header Text */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
            <AlignLeft className="w-4 h-4 text-slate-400" />
            <span>Header Text</span>
          </label>
          <input
            type="text"
            value={headerText}
            onChange={(e) => setHeaderText(e.target.value)}
            placeholder="Type header content..."
            className="w-full px-3.5 py-3 bg-slate-50 border border-slate-200 focus:border-blue-500 rounded-xl outline-none transition text-sm text-slate-700"
          />
        </div>

        {/* Footer Text */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
            <AlignLeft className="w-4 h-4 text-slate-400 rotate-180" />
            <span>Footer Text</span>
          </label>
          <input
            type="text"
            value={footerText}
            onChange={(e) => setFooterText(e.target.value)}
            placeholder="Type footer content..."
            className="w-full px-3.5 py-3 bg-slate-50 border border-slate-200 focus:border-blue-500 rounded-xl outline-none transition text-sm text-slate-700"
          />
        </div>

        {/* Image Replacement */}
        {doc.images_count > 0 ? (
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
              <ImageIcon className="w-4 h-4 text-slate-400" />
              <span>Replace Image</span>
            </div>
            
            <div className="space-y-2">
              <label className="block text-xs text-slate-400 font-semibold">Select image index to replace:</label>
              <select
                value={replaceIndex}
                onChange={(e) => setReplaceIndex(parseInt(e.target.value))}
                className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl outline-none transition text-xs text-slate-600 font-medium"
              >
                {Array.from({ length: doc.images_count }).map((_, idx) => (
                  <option key={idx} value={idx}>Image #{idx + 1}</option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="block text-xs text-slate-400 font-semibold">Upload new image file:</label>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setImageFile(e.target.files[0] || null)}
                className="w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer"
              />
            </div>
          </div>
        ) : (
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-2xl text-center text-xs text-slate-400">
            No image files detected in this document.
          </div>
        )}

        {/* Save button */}
        <button
          type="submit"
          disabled={saving}
          className="w-full py-4 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-700 hover:to-blue-600 text-white font-bold rounded-xl shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 hover:scale-[1.01] active:scale-[0.99] transition duration-200 disabled:opacity-50 mt-8"
        >
          {saving ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Applying Styles...</span>
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              <span>Save & Update</span>
            </>
          )}
        </button>
      </form>
    </div>
  );
};
