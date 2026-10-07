import React, { useState } from 'react';
import { 
  Bold, Italic, Underline, Strikethrough, Highlighter, 
  Palette, Type, Sparkles, Send, X, ChevronDown 
} from 'lucide-react';

const PALETTE_COLORS = [
  { name: 'Black', hex: '#000000' },
  { name: 'Charcoal', hex: '#374151' },
  { name: 'Blue', hex: '#2563eb' },
  { name: 'Navy', hex: '#1e3a8a' },
  { name: 'Crimson', hex: '#dc2626' },
  { name: 'Emerald', hex: '#059669' },
  { name: 'Purple', hex: '#7c3aed' },
];

const FONT_FAMILIES = [
  'Arial', 'Calibri', 'Times New Roman', 'Georgia', 'Inter', 'Courier New'
];

const FONT_SIZES = [9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32];

export const SelectionBubble = ({
  position,
  selectedText,
  onFormat,
  onAiPrompt,
  onClose
}) => {
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [showFontPicker, setShowFontPicker] = useState(false);
  const [showSizePicker, setShowSizePicker] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);

  if (!position) return null;

  const handleAiSubmit = async (e) => {
    e.preventDefault();
    if (!aiPrompt.trim() || !onAiPrompt) return;
    setAiLoading(true);
    try {
      await onAiPrompt(aiPrompt);
      setAiPrompt('');
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        left: `${position.x}px`,
        top: `${position.y}px`,
        transform: 'translate(-50%, -100%) translateY(-10px)',
        zIndex: 9999,
      }}
      className="bg-slate-900/95 backdrop-blur-md text-white rounded-2xl shadow-2xl border border-slate-700/80 p-1.5 flex flex-col gap-1.5 animate-in fade-in zoom-in-95 duration-150 select-none text-xs"
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Top action row */}
      <div className="flex items-center gap-1">
        {/* Bold */}
        <button
          type="button"
          onClick={() => onFormat('bold')}
          title="Bold (Ctrl+B)"
          className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-200 hover:text-white transition cursor-pointer"
        >
          <Bold className="w-3.5 h-3.5" />
        </button>

        {/* Italic */}
        <button
          type="button"
          onClick={() => onFormat('italic')}
          title="Italic (Ctrl+I)"
          className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-200 hover:text-white transition cursor-pointer"
        >
          <Italic className="w-3.5 h-3.5" />
        </button>

        {/* Underline */}
        <button
          type="button"
          onClick={() => onFormat('underline')}
          title="Underline (Ctrl+U)"
          className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-200 hover:text-white transition cursor-pointer"
        >
          <Underline className="w-3.5 h-3.5" />
        </button>

        {/* Strikethrough */}
        <button
          type="button"
          onClick={() => onFormat('strike')}
          title="Strikethrough"
          className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-200 hover:text-white transition cursor-pointer"
        >
          <Strikethrough className="w-3.5 h-3.5" />
        </button>

        <div className="w-px h-4 bg-slate-700 mx-0.5" />

        {/* Highlight */}
        <button
          type="button"
          onClick={() => onFormat('highlight')}
          title="Highlight Yellow"
          className="p-1.5 rounded-lg hover:bg-amber-500/20 text-amber-400 hover:text-amber-300 transition cursor-pointer"
        >
          <Highlighter className="w-3.5 h-3.5" />
        </button>

        {/* Color picker toggle */}
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setShowColorPicker(!showColorPicker);
              setShowFontPicker(false);
              setShowSizePicker(false);
            }}
            title="Text Color"
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-200 hover:text-white transition cursor-pointer flex items-center gap-0.5"
          >
            <Palette className="w-3.5 h-3.5" />
            <ChevronDown className="w-2.5 h-2.5 opacity-60" />
          </button>
          {showColorPicker && (
            <div className="absolute top-full left-0 mt-1.5 p-2 bg-slate-900 border border-slate-700 rounded-xl shadow-xl flex gap-1.5 z-50 animate-in fade-in duration-100">
              {PALETTE_COLORS.map((col) => (
                <button
                  key={col.hex}
                  type="button"
                  title={col.name}
                  onClick={() => {
                    onFormat('color', col.hex);
                    setShowColorPicker(false);
                  }}
                  className="w-5 h-5 rounded-full border border-slate-600 hover:scale-110 transition shadow-xs"
                  style={{ backgroundColor: col.hex }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Font family picker toggle */}
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setShowFontPicker(!showFontPicker);
              setShowColorPicker(false);
              setShowSizePicker(false);
            }}
            title="Font Family"
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-200 hover:text-white transition cursor-pointer flex items-center gap-0.5"
          >
            <Type className="w-3.5 h-3.5" />
            <ChevronDown className="w-2.5 h-2.5 opacity-60" />
          </button>
          {showFontPicker && (
            <div className="absolute top-full left-0 mt-1.5 py-1 w-32 bg-slate-900 border border-slate-700 rounded-xl shadow-xl flex flex-col z-50 max-h-40 overflow-y-auto animate-in fade-in duration-100">
              {FONT_FAMILIES.map((fam) => (
                <button
                  key={fam}
                  type="button"
                  onClick={() => {
                    onFormat('font_name', fam);
                    setShowFontPicker(false);
                  }}
                  style={{ fontFamily: fam }}
                  className="px-2.5 py-1 text-left text-[11px] text-slate-300 hover:text-white hover:bg-slate-800 transition truncate"
                >
                  {fam}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Font size picker toggle */}
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setShowSizePicker(!showSizePicker);
              setShowColorPicker(false);
              setShowFontPicker(false);
            }}
            title="Font Size"
            className="px-1.5 py-1 rounded-lg hover:bg-slate-800 text-[11px] font-bold text-slate-300 hover:text-white transition cursor-pointer flex items-center gap-0.5"
          >
            <span>Size</span>
            <ChevronDown className="w-2.5 h-2.5 opacity-60" />
          </button>
          {showSizePicker && (
            <div className="absolute top-full left-0 mt-1.5 py-1 w-20 bg-slate-900 border border-slate-700 rounded-xl shadow-xl flex flex-col z-50 max-h-40 overflow-y-auto animate-in fade-in duration-100">
              {FONT_SIZES.map((sz) => (
                <button
                  key={sz}
                  type="button"
                  onClick={() => {
                    onFormat('font_size', sz);
                    setShowSizePicker(false);
                  }}
                  className="px-2.5 py-1 text-left text-[11px] text-slate-300 hover:text-white hover:bg-slate-800 transition"
                >
                  {sz} pt
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Close */}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition ml-0.5"
          >
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* AI Quick prompt input on selection */}
      <form onSubmit={handleAiSubmit} className="flex items-center gap-1.5 pt-1 border-t border-slate-800">
        <Sparkles className="w-3 h-3 text-purple-400 shrink-0 ml-1" />
        <input
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          placeholder="Ask AI: e.g. Make concise, Rephrase..."
          className="bg-slate-800/80 border border-slate-700/80 rounded-lg px-2 py-1 text-[10px] text-white placeholder-slate-400 outline-none focus:border-purple-500 w-48 transition"
        />
        <button
          type="submit"
          disabled={!aiPrompt.trim() || aiLoading}
          className="p-1 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 disabled:opacity-40 text-white rounded-lg transition shadow-xs cursor-pointer"
        >
          <Send className="w-2.5 h-2.5" />
        </button>
      </form>
    </div>
  );
};
