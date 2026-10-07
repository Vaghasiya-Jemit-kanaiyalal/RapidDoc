import React from 'react';
import { X, Check, Undo2, ArrowRight, FileCheck, Layers } from 'lucide-react';

export const DiffReviewModal = ({
  isOpen,
  onClose,
  diffData, // { title, originalText, newText, onAccept, onRevert }
  loading = false,
}) => {
  if (!isOpen || !diffData) return null;

  const { title, originalText = '', newText = '', onAccept, onRevert } = diffData;

  // Simple token/word diff calculation for visual highlights
  const originalWords = originalText.split(/(\s+)/);
  const newWords = newText.split(/(\s+)/);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl shadow-2xl border border-slate-200 max-w-2xl w-full overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-indigo-50 text-indigo-600 rounded-xl">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-800">{title || 'Review AI Revision'}</h3>
              <p className="text-xs text-slate-400">Inspect original versus revised text before applying</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-600 rounded-xl transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Diff Body */}
        <div className="p-6 overflow-y-auto space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Original Box */}
            <div className="flex flex-col border border-red-200 bg-red-50/40 rounded-2xl p-4">
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-red-100">
                <span className="text-[10px] font-bold uppercase tracking-wider text-red-700">
                  Original Content
                </span>
                <span className="text-[9px] text-red-500 font-medium">Before mutation</span>
              </div>
              <div className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed flex-1 font-serif">
                {originalText || <span className="italic text-slate-400">Empty</span>}
              </div>
            </div>

            {/* Revised Box */}
            <div className="flex flex-col border border-emerald-200 bg-emerald-50/40 rounded-2xl p-4">
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-emerald-100">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">
                  Proposed AI Rewrite
                </span>
                <span className="text-[9px] text-emerald-500 font-medium">Suggested version</span>
              </div>
              <div className="text-xs text-slate-800 whitespace-pre-wrap leading-relaxed flex-1 font-serif font-medium bg-emerald-100/50 p-2 rounded-xl">
                {newText}
              </div>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/60 flex items-center justify-between shrink-0">
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (onRevert) onRevert();
              onClose();
            }}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-200 text-xs font-bold transition cursor-pointer disabled:opacity-50"
          >
            <Undo2 className="w-3.5 h-3.5" />
            <span>Discard Changes</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={loading}
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-200 text-xs font-semibold transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                if (onAccept) onAccept();
                onClose();
              }}
              className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs transition shadow-sm cursor-pointer disabled:opacity-50"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Accept AI Version</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
