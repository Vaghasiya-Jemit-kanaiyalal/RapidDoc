import React, { useState, useEffect } from 'react';
import { 
  X, Save, AlignLeft, AlignCenter, AlignRight, 
  FileSignature, Loader2, Sparkles, Trash2, Calendar, FileText, Hash
} from 'lucide-react';

export const HeaderFooterEditor = ({
  document: doc,
  token,
  existingHeaders = [],
  existingFooters = [],
  initialSection = 'both', // 'header', 'footer', or 'both'
  onClose,
  onSaveSuccess
}) => {
  const [headerText, setHeaderText] = useState(existingHeaders[0] || '');
  const [footerText, setFooterText] = useState(existingFooters[0] || '');
  const [fontName, setFontName] = useState('Arial');
  const [fontSize, setFontSize] = useState(10);
  const [alignment, setAlignment] = useState('center'); // 'left', 'center', 'right'
  const [targetHeader, setTargetHeader] = useState('');
  const [targetFooter, setTargetFooter] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const fonts = ['Arial', 'Times New Roman', 'Calibri', 'Courier New', 'Helvetica'];

  useEffect(() => {
    if (existingHeaders.length > 0 && !headerText) {
      setHeaderText(existingHeaders[0]);
    }
    if (existingFooters.length > 0 && !footerText) {
      setFooterText(existingFooters[0]);
    }
  }, [existingHeaders, existingFooters]);

  const handleInsertMacro = (type, target) => {
    let macro = '';
    if (type === 'page') macro = 'Page 1';
    else if (type === 'date') macro = new Date().toLocaleDateString();
    else if (type === 'title') macro = doc.name.replace(/\.[^/.]+$/, "");

    if (target === 'header') {
      setHeaderText(prev => prev ? `${prev} | ${macro}` : macro);
    } else {
      setFooterText(prev => prev ? `${prev} | ${macro}` : macro);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    try {
      const payload = {
        header_text: headerText,
        footer_text: footerText,
        target_header_text: targetHeader || null,
        target_footer_text: targetFooter || null,
        font_name: fontName,
        font_size: fontSize,
        alignment: alignment
      };

      const res = await fetch(`/api/documents/${doc.id}/header-footer`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to update header and footer');
      }

      if (onSaveSuccess) {
        onSaveSuccess(data);
      }
      onClose();
    } catch (err) {
      setError(err.message || 'Error updating header & footer');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden border border-slate-100 flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-200">
        {/* Top Header */}
        <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 px-6 py-4 flex items-center justify-between text-white shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-white/15 rounded-2xl backdrop-blur-md">
              <FileSignature className="w-5 h-5 text-blue-100" />
            </div>
            <div>
              <h3 className="font-bold text-base tracking-tight">Header & Footer Manager</h3>
              <p className="text-xs text-blue-100/80 font-medium truncate max-w-xs">{doc.name}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-xl transition text-white/90"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <form onSubmit={handleSubmit} className="flex-grow overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-medium">
              {error}
            </div>
          )}

          {/* Quick Presets / Formatting Bar */}
          <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-2xl space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Formatting & Layout</span>
              <span className="text-[10px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-md font-bold uppercase">
                {doc.file_type.toUpperCase()} Mode
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Font Family */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 mb-1">Font Family</label>
                <select
                  value={fontName}
                  onChange={(e) => setFontName(e.target.value)}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500"
                >
                  {fonts.map(f => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </div>

              {/* Font Size */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 mb-1">Font Size (pt)</label>
                <input
                  type="number"
                  min="6"
                  max="24"
                  value={fontSize}
                  onChange={(e) => setFontSize(parseFloat(e.target.value) || 10)}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Alignment */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 mb-1">Alignment</label>
                <div className="flex bg-white border border-slate-200 rounded-xl p-1 justify-between">
                  <button
                    type="button"
                    onClick={() => setAlignment('left')}
                    className={`flex-1 py-1 flex items-center justify-center rounded-lg transition ${
                      alignment === 'left' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100'
                    }`}
                    title="Align Left"
                  >
                    <AlignLeft className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setAlignment('center')}
                    className={`flex-1 py-1 flex items-center justify-center rounded-lg transition ${
                      alignment === 'center' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100'
                    }`}
                    title="Align Center"
                  >
                    <AlignCenter className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setAlignment('right')}
                    className={`flex-1 py-1 flex items-center justify-center rounded-lg transition ${
                      alignment === 'right' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100'
                    }`}
                    title="Align Right"
                  >
                    <AlignRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Header Section */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs font-bold text-slate-700 uppercase tracking-wider">
                <span className="w-2 h-2 rounded-full bg-blue-600" />
                <span>Header Content</span>
              </label>
              {headerText && (
                <button
                  type="button"
                  onClick={() => setHeaderText('')}
                  className="text-[11px] text-red-500 hover:text-red-700 flex items-center gap-1 font-semibold"
                >
                  <Trash2 className="w-3 h-3" />
                  Clear Header
                </button>
              )}
            </div>

            <textarea
              rows={2}
              value={headerText}
              onChange={(e) => setHeaderText(e.target.value)}
              placeholder="Enter header text to appear at top of document..."
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-xs text-slate-800 focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none transition resize-y font-medium"
            />

            {/* Header Presets */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase mr-1">Insert:</span>
              <button
                type="button"
                onClick={() => handleInsertMacro('title', 'header')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <FileText className="w-3 h-3 text-slate-400" />
                Document Title
              </button>
              <button
                type="button"
                onClick={() => handleInsertMacro('date', 'header')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Calendar className="w-3 h-3 text-slate-400" />
                Current Date
              </button>
              <button
                type="button"
                onClick={() => handleInsertMacro('page', 'header')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Hash className="w-3 h-3 text-slate-400" />
                Page Number
              </button>
            </div>
          </div>

          {/* Footer Section */}
          <div className="space-y-2.5 pt-2">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs font-bold text-slate-700 uppercase tracking-wider">
                <span className="w-2 h-2 rounded-full bg-indigo-600" />
                <span>Footer Content</span>
              </label>
              {footerText && (
                <button
                  type="button"
                  onClick={() => setFooterText('')}
                  className="text-[11px] text-red-500 hover:text-red-700 flex items-center gap-1 font-semibold"
                >
                  <Trash2 className="w-3 h-3" />
                  Clear Footer
                </button>
              )}
            </div>

            <textarea
              rows={2}
              value={footerText}
              onChange={(e) => setFooterText(e.target.value)}
              placeholder="Enter footer text to appear at bottom of document..."
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-xs text-slate-800 focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none transition resize-y font-medium"
            />

            {/* Footer Presets */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase mr-1">Insert:</span>
              <button
                type="button"
                onClick={() => handleInsertMacro('page', 'footer')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Hash className="w-3 h-3 text-slate-400" />
                Page Number
              </button>
              <button
                type="button"
                onClick={() => handleInsertMacro('date', 'footer')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Calendar className="w-3 h-3 text-slate-400" />
                Current Date
              </button>
              <button
                type="button"
                onClick={() => handleInsertMacro('title', 'footer')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <FileText className="w-3 h-3 text-slate-400" />
                Document Title
              </button>
            </div>
          </div>

          {/* Live Page Preview Box */}
          <div className="space-y-1.5 pt-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Live Appearance Preview</span>
            <div className="bg-slate-100 rounded-2xl p-4 border border-slate-200">
              <div className="bg-white rounded-lg border border-slate-300/70 p-4 shadow-sm min-h-[140px] flex flex-col justify-between text-slate-700">
                <div 
                  className={`text-[10px] text-slate-600 pb-2 border-b border-dashed border-slate-200 min-h-[20px] ${
                    alignment === 'left' ? 'text-left' : alignment === 'right' ? 'text-right' : 'text-center'
                  }`}
                  style={{ fontFamily: fontName }}
                >
                  {headerText || <span className="text-slate-300 italic">[No Header Specified]</span>}
                </div>
                <div className="py-3 text-[9px] text-slate-300 text-center italic">
                  — Document Body Content Preview Area —
                </div>
                <div 
                  className={`text-[10px] text-slate-600 pt-2 border-t border-dashed border-slate-200 min-h-[20px] ${
                    alignment === 'left' ? 'text-left' : alignment === 'right' ? 'text-right' : 'text-center'
                  }`}
                  style={{ fontFamily: fontName }}
                >
                  {footerText || <span className="text-slate-300 italic">[No Footer Specified]</span>}
                </div>
              </div>
            </div>
          </div>

          {/* Submit Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-xs transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold rounded-xl text-xs flex items-center gap-2 shadow-lg shadow-blue-500/20 transition hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Applying Changes...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>Save Header & Footer</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
