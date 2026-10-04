import React, { useEffect, useMemo, useState } from 'react';
import { API_URL, getAuthHeaders, isAuthExpired } from '../../utils/api';
import {
  X, Ruler, Loader2, ImageIcon, Link2, Unlink2, MoveHorizontal, Crosshair,
} from 'lucide-react';

// The backend normalises every unit against inches; these are the conversions
// the *display* needs so switching unit shows a number the user recognises
// rather than an unexplained one.
const PER_INCH = { px: 96, pt: 72, in: 1, cm: 96 / 2.54, mm: 96 / 25.4 };

const UNITS = [
  { value: 'px', label: 'px' },
  { value: 'pt', label: 'pt' },
  { value: 'in', label: 'inches' },
  { value: 'cm', label: 'cm' },
  { value: 'mm', label: 'mm' },
];

const round = (n) => Math.round(n * 100) / 100;

/**
 * Change how large one picture prints.
 *
 * The unit selector converts the *current* value rather than leaving the number
 * untouched, because "4 in" shown next to a "cm" dropdown reads as 4cm and would
 * silently resize by a factor of 2.5.
 *
 * Aspect lock is on by default: squashing a logo is rarely what anyone means,
 * and at thumbnail size it is easy to miss. Unlocking is one click away for the
 * cases that genuinely want it.
 */
export const ImageResizeDialog = ({
  document: doc,
  image,          // the inventory entry: { index, width, height, page_num, ... }
  version,        // bump to force the thumbnail to refetch
  onClose,
  onResized,
}) => {
  const [unit, setUnit] = useState('in');
  const [width, setWidth] = useState('');
  const [height, setHeight] = useState('');
  const [keepAspect, setKeepAspect] = useState(true);
  const [anchor, setAnchor] = useState('top_left');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Seed from what the server says is currently drawn. `width`/`height` are the
  // drawn size in 96dpi px for both DOCX and PDF, so one conversion covers both.
  useEffect(() => {
    if (!image?.width || !image?.height) return;
    const factor = PER_INCH[unit] || 1;
    setWidth(round(image.width / factor).toString());
    setHeight(round(image.height / factor).toString());
    // Seed once per image; re-running on `unit` would fight the user's typing.
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
    if (!keepAspect) return;
    const w = parseFloat(raw);
    const ratio = image?.width && image?.height ? image.height / image.width : null;
    if (Number.isFinite(w) && ratio) setHeight(round(w * ratio).toString());
  };

  const onHeightChange = (raw) => {
    setHeight(raw);
    setError('');
    if (!keepAspect) return;
    const h = parseFloat(raw);
    const ratio = image?.width && image?.height ? image.width / image.height : null;
    if (Number.isFinite(h) && ratio) setWidth(round(h * ratio).toString());
  };

  const canSubmit = Number.isFinite(parseFloat(width)) || Number.isFinite(parseFloat(height));

  const submit = async (e) => {
    e.preventDefault();
    setError('');

    const w = parseFloat(width);
    const h = parseFloat(height);
    const item = {
      index: image.index,
      keep_aspect: keepAspect,
      anchor,
    };
    // Send only the field the user filled in: sending both would make the locked
    // case depend on the server's tie-break rather than on what was asked.
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
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden border border-slate-100 animate-in fade-in zoom-in-95 duration-200">
        <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 px-6 py-4 flex items-center justify-between text-white">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-white/15 rounded-2xl backdrop-blur-md">
              <Ruler className="w-5 h-5 text-blue-100" />
            </div>
            <div>
              <h3 className="font-bold text-base tracking-tight">Resize Image</h3>
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

          {/* Current appearance, so the target size is something concrete. */}
          <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-2xl flex items-center gap-4">
            <div className="p-2.5 bg-white rounded-xl border border-slate-200 shrink-0">
              <img
                src={`${API_URL}/documents/${doc.id}/images/${image?.index}?v=${version || 0}`}
                alt=""
                className="max-h-16 max-w-24 object-contain"
              />
            </div>
            <div className="text-[11px] text-slate-600 space-y-0.5">
              <p className="font-bold text-slate-700">
                Currently {image?.width}&times;{image?.height} px
              </p>
              {image?.pixel_width && (
                <p className="text-slate-500">
                  Stored image data is {image.pixel_width}&times;{image.pixel_height} px
                </p>
              )}
              <p className="text-slate-400">Resizing changes how it prints, not the pixels.</p>
            </div>
          </div>

          {sharedNote && (
            <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 text-[11px] rounded-xl font-medium flex items-start gap-2">
              <ImageIcon className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{sharedNote}</span>
            </div>
          )}

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Size</span>
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
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500"
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
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

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
                {keepAspect ? 'the other side follows' : 'both sides applied exactly'}
              </span>
            </button>

            <div>
              <span className="block text-[11px] font-semibold text-slate-500 mb-1.5">Anchor</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setAnchor('top_left')}
                  className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl border text-[11px] font-bold transition ${
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
                  className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl border text-[11px] font-bold transition ${
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
                  <span>Resizing...</span>
                </>
              ) : (
                <>
                  <Ruler className="w-4 h-4" />
                  <span>Apply Size</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};