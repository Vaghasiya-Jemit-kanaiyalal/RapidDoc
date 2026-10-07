import React, { useState } from 'react';
import { 
  X, Check, Layout, Columns, FileSpreadsheet, Ruler, SplitSquareVertical 
} from 'lucide-react';

export const PageSetupDialog = ({
  isOpen,
  onClose,
  onApply,
  currentOrientation = 'portrait',
  loading = false,
}) => {
  const [orientation, setOrientation] = useState(currentOrientation);
  const [pageSize, setPageSize] = useState('Letter');
  const [margins, setMargins] = useState('1.0');

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    onApply({
      orientation,
      page_size: pageSize,
      margin_inches: parseFloat(margins) || 1.0,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl shadow-2xl border border-slate-200 max-w-md w-full overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-blue-50 text-blue-600 rounded-xl">
              <Layout className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-800">Page Setup & Layout</h3>
              <p className="text-xs text-slate-400">Configure page size, orientation, and margins</p>
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

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Orientation */}
          <div>
            <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">
              Orientation
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setOrientation('portrait')}
                className={`flex flex-col items-center justify-center p-3 rounded-2xl border-2 transition cursor-pointer ${
                  orientation === 'portrait'
                    ? 'border-blue-600 bg-blue-50/60 text-blue-800 font-bold shadow-xs'
                    : 'border-slate-200 hover:border-slate-300 text-slate-600'
                }`}
              >
                <div className="w-8 h-11 border-2 border-current rounded-sm mb-1.5 flex items-center justify-center">
                  <span className="text-[8px] uppercase">A4</span>
                </div>
                <span className="text-xs font-semibold">Portrait</span>
              </button>

              <button
                type="button"
                onClick={() => setOrientation('landscape')}
                className={`flex flex-col items-center justify-center p-3 rounded-2xl border-2 transition cursor-pointer ${
                  orientation === 'landscape'
                    ? 'border-blue-600 bg-blue-50/60 text-blue-800 font-bold shadow-xs'
                    : 'border-slate-200 hover:border-slate-300 text-slate-600'
                }`}
              >
                <div className="w-11 h-8 border-2 border-current rounded-sm mb-1.5 flex items-center justify-center">
                  <span className="text-[8px] uppercase">A4</span>
                </div>
                <span className="text-xs font-semibold">Landscape</span>
              </button>
            </div>
          </div>

          {/* Paper Size */}
          <div>
            <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">
              Paper Size
            </label>
            <div className="grid grid-cols-2 gap-3">
              {[
                { id: 'Letter', label: 'Letter', sub: '8.5" × 11.0"' },
                { id: 'A4', label: 'A4', sub: '8.27" × 11.69"' },
              ].map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setPageSize(p.id)}
                  className={`flex flex-col text-left p-3 rounded-2xl border-2 transition cursor-pointer ${
                    pageSize === p.id
                      ? 'border-blue-600 bg-blue-50/60 text-blue-800 font-bold shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 text-slate-600'
                  }`}
                >
                  <span className="text-xs font-bold">{p.label}</span>
                  <span className="text-[10px] text-slate-400">{p.sub}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Margins */}
          <div>
            <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">
              Margins
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { id: '1.0', label: 'Normal', val: '1.0"' },
                { id: '0.5', label: 'Narrow', val: '0.5"' },
                { id: '1.5', label: 'Wide', val: '1.5"' },
              ].map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setMargins(m.id)}
                  className={`flex flex-col items-center justify-center p-2.5 rounded-xl border-2 transition cursor-pointer ${
                    margins === m.id
                      ? 'border-blue-600 bg-blue-50/60 text-blue-800 font-bold shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 text-slate-600'
                  }`}
                >
                  <span className="text-xs font-semibold">{m.label}</span>
                  <span className="text-[10px] text-slate-400">{m.val}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Action buttons */}
          <div className="pt-3 flex gap-2 justify-end border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-100 font-semibold text-xs transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs transition shadow-sm cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" />
              <span>{loading ? 'Applying...' : 'Apply Layout'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
