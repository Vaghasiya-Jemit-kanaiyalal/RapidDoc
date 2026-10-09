import React, { useEffect, useMemo, useRef, useState } from 'react';
import { API_URL, getAuthHeaders, isAuthExpired } from '../../utils/api';
import {
  X, Ruler, Loader2, ImageIcon, Link2, Unlink2, MoveHorizontal, Crosshair,
  Maximize2, RotateCcw, FilePlus2, AlertCircle, Sparkles
} from 'lucide-react';

// The backend normalises every unit against inches; these are the conversions
// the display needs so switching unit shows a number the user recognises.
const PER_INCH = { px: 96, pt: 72, in: 1, cm: 96 / 2.54, mm: 96 / 25.4 };

const UNITS = [
  { value: 'px', label: 'px' },
  { value: 'pt', label: 'pt' },
  { value: 'in', label: 'inches' },
  { value: 'cm', label: 'cm' },
  { value: 'mm', label: 'mm' },
];

const round = (n) => Math.round(n * 100) / 100;

export const ImageResizeDialog = ({
  document: doc,
  image,          // { index, width, height, pixel_width, pixel_height, page_num, occurrences }
  version,        // bump to force the thumbnail to refetch
  onClose,
  onResized,
}) => {
  const [unit, setUnit] = useState('in');
  const [width, setWidth] = useState('');
  const [height, setHeight] = useState('');
  const [keepAspect, setKeepAspect] = useState(true);
  const [anchor, setAnchor] = useState('top_left');
  const [newPage, setNewPage] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Drag interaction state for the 4 corner handles
  const [draggingCorner, setDraggingCorner] = useState(null);
  const dragStartRef = useRef(null);

  // Intrinsic/native dimensions
  const nativePxWidth = image?.pixel_width || image?.width || 300;
  const nativePxHeight = image?.pixel_height || image?.height || 200;
  const aspectRatio = nativePxWidth / (nativePxHeight || 1);

  // Seed from what the server says is currently drawn.
  useEffect(() => {
    if (!image?.width || !image?.height) return;
    const factor = PER_INCH[unit] || 1;
    setWidth(round(image.width / factor).toString());
    setHeight(round(image.height / factor).toString());

    // Auto-suggest new page if current height exceeds ~5 inches (480 px)
    if (image.height > 480) {
      setNewPage(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [image?.index]);

  /** Re-express both fields when the unit changes, preserving the real size. */
  const changeUnit = (next) => {
    const from = PER_INCH[unit] || 1;
    const to = PER_INCH[next] || 1;
    const w = parseFloat(width);
    const h = parseFloat(height);
    if (Number.isFinite(w)) setWidth(round((w * from) / to).toString());
    if (Number.isFinite(h)) setHeight(round((h * from) / to).toString());
    setUnit(next);
    setError('');
  };

  /** Mirror one field onto the other while the ratio is locked. */
  const onWidthChange = (raw) => {
    setWidth(raw);
    setError('');
    const w = parseFloat(raw);
    if (!keepAspect || !Number.isFinite(w)) return;
    const h = w / aspectRatio;
    setHeight(round(h).toString());

    // Check height in inches
    const factor = PER_INCH[unit] || 1;
    const heightInches = (h * factor) / 96;
    if (heightInches > 5) setNewPage(true);
  };

  const onHeightChange = (raw) => {
    setHeight(raw);
    setError('');
    const h = parseFloat(raw);
    if (!keepAspect || !Number.isFinite(h)) return;
    const w = h * aspectRatio;
    setWidth(round(w).toString());

    const factor = PER_INCH[unit] || 1;
    const heightInches = (h * factor) / 96;
    if (heightInches > 5) setNewPage(true);
  };

  /** Preset: Reset to 100% Original Stored Size */
  const setOriginalSize = () => {
    const factor = PER_INCH[unit] || 1;
    const w = round(nativePxWidth / factor);
    const h = round(nativePxHeight / factor);
    setWidth(w.toString());
    setHeight(h.toString());
    setError('');

    // If original height is large (> 5 inches = 480 px), automatically activate new page break
    if (nativePxHeight > 480) {
      setNewPage(true);
    }
  };

  /** Preset percentage scale based on original stored image pixels */
  const applyScalePreset = (percent) => {
    const factor = PER_INCH[unit] || 1;
    const w = round(((nativePxWidth * percent) / 100) / factor);
    const h = round(((nativePxHeight * percent) / 100) / factor);
    setWidth(w.toString());
    setHeight(h.toString());
    setError('');

    if (h * (factor / 96) > 5) {
      setNewPage(true);
    }
  };

  /** Set width to full printable page content width (~6.0 inches) */
  const applyFitPageWidth = () => {
    const factor = PER_INCH[unit] || 1;
    const targetInches = 6.0;
    const w = round(targetInches * (PER_INCH[unit] || 1));
    setWidth(w.toString());
    if (keepAspect) {
      const h = round(w / aspectRatio);
      setHeight(h.toString());
      if ((h * factor) / 96 > 5) setNewPage(true);
    }
    setError('');
  };

  // Convert current input values to pixels for the interactive canvas preview
  const currentPxWidth = useMemo(() => {
    const val = parseFloat(width);
    if (!Number.isFinite(val) || val <= 0) return 200;
    const factor = PER_INCH[unit] || 1;
    return val * factor;
  }, [width, unit]);

  const currentPxHeight = useMemo(() => {
    const val = parseFloat(height);
    if (!Number.isFinite(val) || val <= 0) return Math.round(200 / aspectRatio);
    const factor = PER_INCH[unit] || 1;
    return val * factor;
  }, [height, unit, aspectRatio]);

  // Height in inches to determine if it overflows current page space
  const currentHeightInches = useMemo(() => {
    return currentPxHeight / 96;
  }, [currentPxHeight]);

  const isLargeOrOverflow = currentHeightInches >= 4.8;

  /**
   * 4-Corner Interactive Drag Handlers
   * Northwest (top-left), Northeast (top-right), Southwest (bottom-left), Southeast (bottom-right)
   */
  const handleCornerPointerDown = (corner, e) => {
    e.preventDefault();
    e.stopPropagation();
    e.target.setPointerCapture(e.pointerId);
    setDraggingCorner(corner);
    dragStartRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      startW: currentPxWidth,
      startH: currentPxHeight,
    };
  };

  const handleCornerPointerMove = (e) => {
    if (!draggingCorner || !dragStartRef.current) return;
    const { startX, startY, startW, startH } = dragStartRef.current;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;

    let nextW = startW;
    let nextH = startH;

    // Scale sensitivity factor based on preview scaling
    const sensitivity = 1.6;

    if (draggingCorner === 'se') {
      nextW = startW + dx * sensitivity;
      nextH = startH + dy * sensitivity;
    } else if (draggingCorner === 'sw') {
      nextW = startW - dx * sensitivity;
      nextH = startH + dy * sensitivity;
    } else if (draggingCorner === 'ne') {
      nextW = startW + dx * sensitivity;
      nextH = startH - dy * sensitivity;
    } else if (draggingCorner === 'nw') {
      nextW = startW - dx * sensitivity;
      nextH = startH - dy * sensitivity;
    }

    nextW = Math.max(30, nextW);
    nextH = Math.max(30, nextH);

    if (keepAspect) {
      if (Math.abs(dx) > Math.abs(dy)) {
        nextH = nextW / aspectRatio;
      } else {
        nextW = nextH * aspectRatio;
      }
    }

    const factor = PER_INCH[unit] || 1;
    setWidth(round(nextW / factor).toString());
    setHeight(round(nextH / factor).toString());

    if (nextH / 96 > 5) {
      setNewPage(true);
    }
  };

  const handleCornerPointerUp = (e) => {
    if (draggingCorner) {
      try {
        e.target.releasePointerCapture(e.pointerId);
      } catch {
        // pointer may have been released
      }
      setDraggingCorner(null);
      dragStartRef.current = null;
    }
  };

  const canSubmit = Number.isFinite(parseFloat(width)) || Number.isFinite(parseFloat(height));

  const submit = async (e) => {
    e.preventDefault();
    setError('');

    const w = parseFloat(width);
    const h = parseFloat(height);
    const item = {
      index: image.index,
      unit,
      keep_aspect: keepAspect,
      anchor,
      new_page: newPage,
    };

    if (Number.isFinite(w)) item.width = w;
    if (Number.isFinite(h)) item.height = h;
    if (item.width === undefined && item.height === undefined) {
      setError('Enter a width, a height, or both.');
      return;
    }

    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/resize-image`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: [item] }),
      });
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'The image could not be resized.');
      }
      if (onResized) onResized(data);
      onClose();
    } catch (err) {
      setError(err.message || 'The image could not be resized.');
    } finally {
      setSaving(false);
    }
  };

  const location = useMemo(() => {
    if (image?.page_num === null || image?.page_num === undefined) return 'Whole document';
    return `Page ${image.page_num + 1}`;
  }, [image?.page_num]);

  const sharedNote = (image?.occurrences || 1) > 1
    ? `This picture is stored once and drawn in ${image.occurrences} places. Every one of them will be resized.`
    : null;

  return (
    <div className="fixed inset-0 z-[70] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-xl overflow-hidden border border-slate-100 animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 px-6 py-4 flex items-center justify-between text-white">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-white/15 rounded-2xl backdrop-blur-md">
              <Ruler className="w-5 h-5 text-blue-100" />
            </div>
            <div>
              <h3 className="font-bold text-base tracking-tight">Image Resizing & Placement</h3>
              <p className="text-xs text-blue-100/80 font-medium">
                Image {image?.index + 1} &middot; {location}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-xl transition text-white/90"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={submit} className="p-6 space-y-5">
          {error && (
            <div className="p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-medium">
              {error}
            </div>
          )}

          {/* Interactive 4-Corner Resize Canvas Preview */}
          <div className="relative rounded-2xl border border-slate-200 bg-slate-900/5 p-4 flex flex-col items-center justify-center overflow-hidden">
            <div className="w-full flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                <Maximize2 className="w-3.5 h-3.5 text-blue-600" />
                Interactive 4-Corner Resizing Box
              </span>
              <span className="text-[10px] bg-blue-100 text-blue-800 font-semibold px-2 py-0.5 rounded-full">
                Drag any corner to scale
              </span>
            </div>

            {/* Interactive Image Frame with 4 Drag Handles */}
            <div
              className="relative my-2 select-none flex items-center justify-center border-2 border-dashed border-blue-500/60 rounded-xl p-1 bg-white shadow-md transition-all"
              style={{
                maxWidth: '280px',
                maxHeight: '190px',
                aspectRatio: `${nativePxWidth} / ${nativePxHeight}`,
              }}
            >
              <img
                src={`${API_URL}/documents/${doc.id}/images/${image?.index}?v=${version || 0}`}
                alt="Target to resize"
                className="w-full h-full object-contain rounded-lg pointer-events-none"
              />

              {/* Northwest (Top-Left) Corner Handle */}
              <div
                onPointerDown={(e) => handleCornerPointerDown('nw', e)}
                onPointerMove={handleCornerPointerMove}
                onPointerUp={handleCornerPointerUp}
                title="Drag to resize top-left corner"
                className="absolute -top-2.5 -left-2.5 w-5 h-5 bg-white border-2 border-blue-600 rounded-full shadow-md cursor-nwse-resize hover:scale-125 transition-transform flex items-center justify-center group z-20"
              >
                <div className="w-1.5 h-1.5 bg-blue-600 rounded-full group-hover:bg-indigo-600" />
              </div>

              {/* Northeast (Top-Right) Corner Handle */}
              <div
                onPointerDown={(e) => handleCornerPointerDown('ne', e)}
                onPointerMove={handleCornerPointerMove}
                onPointerUp={handleCornerPointerUp}
                title="Drag to resize top-right corner"
                className="absolute -top-2.5 -right-2.5 w-5 h-5 bg-white border-2 border-blue-600 rounded-full shadow-md cursor-nesw-resize hover:scale-125 transition-transform flex items-center justify-center group z-20"
              >
                <div className="w-1.5 h-1.5 bg-blue-600 rounded-full group-hover:bg-indigo-600" />
              </div>

              {/* Southwest (Bottom-Left) Corner Handle */}
              <div
                onPointerDown={(e) => handleCornerPointerDown('sw', e)}
                onPointerMove={handleCornerPointerMove}
                onPointerUp={handleCornerPointerUp}
                title="Drag to resize bottom-left corner"
                className="absolute -bottom-2.5 -left-2.5 w-5 h-5 bg-white border-2 border-blue-600 rounded-full shadow-md cursor-nesw-resize hover:scale-125 transition-transform flex items-center justify-center group z-20"
              >
                <div className="w-1.5 h-1.5 bg-blue-600 rounded-full group-hover:bg-indigo-600" />
              </div>

              {/* Southeast (Bottom-Right) Corner Handle */}
              <div
                onPointerDown={(e) => handleCornerPointerDown('se', e)}
                onPointerMove={handleCornerPointerMove}
                onPointerUp={handleCornerPointerUp}
                title="Drag to resize bottom-right corner"
                className="absolute -bottom-2.5 -right-2.5 w-5 h-5 bg-white border-2 border-blue-600 rounded-full shadow-md cursor-nwse-resize hover:scale-125 transition-transform flex items-center justify-center group z-20"
              >
                <div className="w-1.5 h-1.5 bg-blue-600 rounded-full group-hover:bg-indigo-600" />
              </div>
            </div>

            {/* Live Size Pill */}
            <div className="mt-2 text-center text-[11px] font-semibold text-slate-600 bg-white/80 backdrop-blur-xs px-3 py-1 rounded-full border border-slate-200 shadow-xs">
              Live Size: <span className="text-blue-700 font-bold">{round(currentPxWidth)} &times; {round(currentPxHeight)} px</span>
              {' '}&middot;{' '}
              <span className="text-slate-500">{round(currentPxWidth / 96)} &times; {round(currentPxHeight / 96)} in</span>
            </div>
          </div>

          {/* Quick Presets & Original Size Button */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-bold text-slate-500 mr-1">Presets:</span>
            <button
              type="button"
              onClick={setOriginalSize}
              className="px-2.5 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-xl text-[11px] font-bold flex items-center gap-1.5 transition active:scale-95 shadow-xs"
              title="Reset width & height to original native image pixels"
            >
              <RotateCcw className="w-3 h-3" />
              Original Size (100%)
            </button>
            <button
              type="button"
              onClick={() => applyScalePreset(75)}
              className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-[11px] font-semibold transition"
            >
              75%
            </button>
            <button
              type="button"
              onClick={() => applyScalePreset(50)}
              className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-[11px] font-semibold transition"
            >
              50%
            </button>
            <button
              type="button"
              onClick={applyFitPageWidth}
              className="px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-xl text-[11px] font-bold transition"
            >
              Fit Page Width (6.0 in)
            </button>
          </div>

          {sharedNote && (
            <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 text-[11px] rounded-xl font-medium flex items-start gap-2">
              <ImageIcon className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{sharedNote}</span>
            </div>
          )}

          {/* Numeric Width & Height controls */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Dimensions</span>
              <div className="flex bg-slate-100 border border-slate-200 rounded-xl p-1">
                {UNITS.map((u) => (
                  <button
                    key={u.value}
                    type="button"
                    onClick={() => changeUnit(u.value)}
                    title={u.label}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition ${
                      unit === u.value
                        ? 'bg-white text-blue-700 shadow-sm'
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    {u.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 mb-1">
                  Width ({unit})
                </label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={width}
                  onChange={(e) => onWidthChange(e.target.value)}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500 shadow-xs"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 mb-1">
                  Height ({unit})
                </label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={height}
                  onChange={(e) => onHeightChange(e.target.value)}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500 shadow-xs"
                />
              </div>
            </div>

            {/* Aspect Ratio Lock */}
            <button
              type="button"
              onClick={() => setKeepAspect((v) => !v)}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl border text-[11px] font-bold transition ${
                keepAspect
                  ? 'bg-blue-50 border-blue-200 text-blue-700'
                  : 'bg-amber-50 border-amber-200 text-amber-700'
              }`}
            >
              <span className="flex items-center gap-2">
                {keepAspect ? <Link2 className="w-3.5 h-3.5" /> : <Unlink2 className="w-3.5 h-3.5" />}
                {keepAspect ? 'Aspect ratio locked' : 'Free stretching'}
              </span>
              <span className="font-medium opacity-70">
                {keepAspect ? '4 corners maintain ratio' : 'independent width/height'}
              </span>
            </button>

            {/* Overflow / Move to New Page Toggle */}
            <div className={`p-3.5 rounded-2xl border transition-all ${
              newPage
                ? 'bg-indigo-50/80 border-indigo-200 text-indigo-900'
                : 'bg-slate-50 border-slate-200 text-slate-700'
            }`}>
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={newPage}
                  onChange={(e) => setNewPage(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                />
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <FilePlus2 className="w-4 h-4 text-blue-600" />
                    <span className="text-xs font-bold">Start on New Page (Page Break)</span>
                    {isLargeOrOverflow && (
                      <span className="text-[10px] bg-indigo-600 text-white font-bold px-1.5 py-0.5 rounded-full">
                        Recommended
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500">
                    If this image does not fit comfortably on the current page, insert a page break so it displays fully on a new page without awkward clipping.
                  </p>
                </div>
              </label>

              {isLargeOrOverflow && !newPage && (
                <div className="mt-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200/80 rounded-xl px-2.5 py-1 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  <span>Height exceeds ~5 inches. Placing on a new page ensures clean document pagination.</span>
                </div>
              )}
            </div>

            {/* Anchor Selection */}
            <div>
              <span className="block text-[11px] font-semibold text-slate-500 mb-1.5">Anchor Point</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setAnchor('top_left')}
                  className={`flex items-center justify-center gap-2 px-3 py-2 rounded-xl border text-[11px] font-bold transition ${
                    anchor === 'top_left'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <MoveHorizontal className="w-3.5 h-3.5" />
                  Top-left stays
                </button>
                <button
                  type="button"
                  onClick={() => setAnchor('center')}
                  className={`flex items-center justify-center gap-2 px-3 py-2 rounded-xl border text-[11px] font-bold transition ${
                    anchor === 'center'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <Crosshair className="w-3.5 h-3.5" />
                  Centre stays
                </button>
              </div>
            </div>
          </div>

          {/* Footer Actions */}
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
              disabled={saving || !canSubmit}
              className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold rounded-xl text-xs flex items-center gap-2 shadow-lg shadow-blue-500/20 transition hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Applying Size & Layout...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Apply Size {newPage ? '& Move to New Page' : ''}</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};