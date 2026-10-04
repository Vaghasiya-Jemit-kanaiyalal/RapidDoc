import React, { useState } from 'react';
import { API_URL, getAuthHeaders, isAuthExpired } from '../../utils/api';
import {
  X, Save, AlignLeft, AlignCenter, AlignRight,
  FileSignature, Loader2, Trash2, Calendar, FileText, Hash, Layers, FilePlus2
} from 'lucide-react';

// Macro tokens the backend understands. They stay tokens in the text the user
// edits and become real fields on save, which is why the page number no longer
// comes out as the same digit on every page.
const MACROS = {
  page: '{PAGE}',
  pageOfTotal: '{PAGE} of {NUMPAGES}',
  totalPages: '{NUMPAGES}',
  date: '{DATE}',
  time: '{TIME}',
  title: '{TITLE}',
};

const asText = (v) => {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'object') return String(v.text ?? '') || String(v.section ?? '');
  return String(v);
};

// Preview only: show what a token resolves to on a sample page.
const previewText = (text, { page = 1, pages = 5 } = {}) =>
  String(text || '')
    .replace(/\{PAGE\}/g, String(page))
    .replace(/<<\s*PAGE\s*>>/gi, String(page))
    .replace(/\{NUMPAGES\}/gi, String(pages))
    .replace(/<<\s*NUMPAGES\s*>>/gi, String(pages))
    .replace(/\{DATE\}|<<\s*DATE\s*>>/gi, new Date().toLocaleDateString())
    .replace(/\{TIME\}|<<\s*TIME\s*>>/gi, new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

const alignClass = (align) =>
  align === 'left' ? 'text-left' : align === 'right' ? 'text-right' : 'text-center';

function AlignPicker({ value, onChange, label }) {
  const options = [
    { key: 'left', Icon: AlignLeft, title: 'Align Left' },
    { key: 'center', Icon: AlignCenter, title: 'Align Center' },
    { key: 'right', Icon: AlignRight, title: 'Align Right' },
  ];
  return (
    <div>
      <label className="block text-[11px] font-semibold text-slate-500 mb-1">{label}</label>
      <div className="flex bg-white border border-slate-200 rounded-xl p-1 justify-between">
        {options.map(({ key, Icon, title }) => (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            aria-pressed={value === key}
            className={`flex-1 py-1 flex items-center justify-center rounded-lg transition ${
              value === key ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100'
            }`}
            title={title}
          >
            <Icon className="w-3.5 h-3.5" />
          </button>
        ))}
      </div>
    </div>
  );
}

function TextField({ id, label, hint, value, onChange, onFocus, placeholder, align, fontName }) {
  return (
    <div>
      <label htmlFor={id} className="block text-[11px] font-semibold text-slate-500 mb-1">
        {label}
        {hint && <span className="ml-1 font-normal text-slate-400">{hint}</span>}
      </label>
      <textarea
        id={id}
        rows={2}
        value={value}
        onFocus={onFocus}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-xs text-slate-800 focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none transition resize-y font-medium"
      />
      <div className="mt-1 flex items-center justify-between">
        <span className="text-[10px] text-slate-400 truncate" style={{ fontFamily: fontName }}>
          {value ? previewText(value) : '—'}
        </span>
        <span className={`text-[10px] text-slate-300 ${alignClass(align)} w-24`}>
          {value ? (align === 'left' ? 'Left' : align === 'right' ? 'Right' : 'Center') : ''}
        </span>
      </div>
    </div>
  );
}

export const HeaderFooterEditor = ({
  document: doc,
  token,
  existingHeaders = [],
  existingFooters = [],
  variants = null,
  initialSection = 'both', // 'header', 'footer', or 'both'
  onClose,
  onSaveSuccess,
}) => {
  const sideSpecific = Boolean(variants?.different_odd_even);
  const firstSpecific = Boolean(variants?.different_first);

  const [header, setHeader] = useState({
    all: asText(variants?.header_odd) || asText(existingHeaders[0]),
    odd: asText(variants?.header_odd),
    even: asText(variants?.header_even),
    first: asText(variants?.header_first),
    sides: sideSpecific,
    firstPage: firstSpecific,
  });
  const [footer, setFooter] = useState({
    all: asText(variants?.footer_odd) || asText(existingFooters[0]),
    odd: asText(variants?.footer_odd),
    even: asText(variants?.footer_even),
    first: asText(variants?.footer_first),
    sides: sideSpecific,
    firstPage: firstSpecific,
  });

  const [fontName, setFontName] = useState('Arial');
  const [fontSize, setFontSize] = useState(10);
  const [headerAlign, setHeaderAlign] = useState('center');
  const [footerAlign, setFooterAlign] = useState('center');

  // Which textarea the Insert buttons write into, so one button row serves every
  // variant instead of repeating itself in six places.
  const [active, setActive] = useState({ zone: 'header', field: 'all' });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const fonts = ['Arial', 'Times New Roman', 'Calibri', 'Courier New', 'Helvetica'];

  const setZone = (zone, patch) => {
    const update = zone === 'header' ? setHeader : setFooter;
    update((prev) => ({ ...prev, ...patch }));
  };

  const insertMacro = (key) => {
    const macro = MACROS[key];
    if (!macro) return;
    const zone = active.zone === 'header' ? header : footer;
    setZone(active.zone, { [active.field]: zone[active.field] ? `${zone[active.field]} ${macro}` : macro });
  };

  const visibleFields = (zone) => {
    const fields = [];
    if (zone.firstPage) fields.push('first');
    if (zone.sides) fields.push('odd', 'even');
    else fields.push('all');
    return fields;
  };

  const activeLabel = {
    all: 'every page',
    odd: 'right pages (odd)',
    even: 'left pages (even)',
    first: 'first page',
  }[active.field];

  const zonePayload = (zone, zoneName) => ({
    // `all` is always sent, even when side-specific mode is on. Dropping it meant
    // a document that already had odd/even furniture (almost every lab report,
    // because the page number differs per side) opened with the sides toggle on,
    // so anything typed into "All pages" was discarded on save.
    [`${zoneName}_text`]: zone.all,
    [`${zoneName}_text_odd`]: zone.sides ? zone.odd : null,
    [`${zoneName}_text_even`]: zone.sides ? zone.even : null,
    [`${zoneName}_text_first`]: zone.firstPage ? zone.first : null,
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    try {
      const payload = {
        ...zonePayload(header, 'header'),
        ...zonePayload(footer, 'footer'),
        font_name: fontName,
        font_size: fontSize,
        alignment: 'center',
        header_alignment: headerAlign,
        footer_alignment: footerAlign,
      };

      const res = await fetch(`${API_URL}/documents/${doc.id}/header-footer`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
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

  const renderZone = (zoneName, zone, align, setAlign, accent, verb) => {
    const isHeader = zoneName === 'header';
    const showAlign = isHeader ? initialSection !== 'footer' : initialSection !== 'header';

    return (
      <div className="space-y-2.5 pt-2">
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs font-bold text-slate-700 uppercase tracking-wider">
            <span className={`w-2 h-2 rounded-full ${accent}`} />
            <span>{isHeader ? 'Header Content' : 'Footer Content'}</span>
          </label>
          <div className="flex items-center gap-3">
            {visibleFields(zone).some((f) => zone[f]) && (
              <button
                type="button"
                onClick={() =>
                  setZone(zoneName, Object.fromEntries(visibleFields(zone).map((f) => [f, ''])))
                }
                className="text-[11px] text-red-500 hover:text-red-700 flex items-center gap-1 font-semibold"
              >
                <Trash2 className="w-3 h-3" />
                Clear {isHeader ? 'Header' : 'Footer'}
              </button>
            )}
          </div>
        </div>

        {/* Page-side options */}
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-[11px] font-medium text-slate-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={zone.sides}
              onChange={(e) => {
                const sides = e.target.checked;
                setZone(zoneName, {
                  sides,
                  // Switching on with an empty even side would blank every left
                  // page, so seed it from what the right side already shows.
                  even: sides && !zone.even ? zone.all || zone.odd : zone.even,
                  odd: sides && !zone.odd ? zone.all : zone.odd,
                });
                setActive({ zone: zoneName, field: sides ? 'odd' : 'all' });
              }}
              className="w-3.5 h-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-400"
            />
            <Layers className="w-3.5 h-3.5 text-slate-400" />
            Different for left / right pages
          </label>

          <label className="flex items-center gap-2 text-[11px] font-medium text-slate-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={zone.firstPage}
              onChange={(e) => setZone(zoneName, { firstPage: e.target.checked })}
              className="w-3.5 h-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-400"
            />
            <FilePlus2 className="w-3.5 h-3.5 text-slate-400" />
            Different first page
          </label>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {zone.firstPage && (
            <TextField
              id={`${zoneName}-first`}
              label="First page"
              hint="(page 1)"
              value={zone.first}
              onFocus={() => setActive({ zone: zoneName, field: 'first' })}
              onChange={(v) => setZone(zoneName, { first: v })}
              placeholder={`Leave blank to keep the ${isHeader ? 'header' : 'footer'} off page 1`}
              align={align}
              fontName={fontName}
            />
          )}

          {zone.sides ? (
            <>
              <TextField
                id={`${zoneName}-odd`}
                label="Right pages"
                hint="(odd: 1, 3, 5…)"
                value={zone.odd}
                onFocus={() => setActive({ zone: zoneName, field: 'odd' })}
                onChange={(v) => setZone(zoneName, { odd: v })}
                placeholder={`Text shown on ${isHeader ? 'headers' : 'footers'} of right-hand pages`}
                align={align}
                fontName={fontName}
              />
              <TextField
                id={`${zoneName}-even`}
                label="Left pages"
                hint="(even: 2, 4, 6…)"
                value={zone.even}
                onFocus={() => setActive({ zone: zoneName, field: 'even' })}
                onChange={(v) => setZone(zoneName, { even: v })}
                placeholder={`Text shown on ${isHeader ? 'headers' : 'footers'} of left-hand pages`}
                align={align}
                fontName={fontName}
              />
            </>
          ) : (
            <TextField
              id={`${zoneName}-all`}
              label={`${isHeader ? 'Header' : 'Footer'} text`}
              value={zone.all}
              onFocus={() => setActive({ zone: zoneName, field: 'all' })}
              onChange={(v) => setZone(zoneName, { all: v })}
              placeholder={verb}
              align={align}
              fontName={fontName}
            />
          )}
        </div>

        {showAlign && (
          <div className="w-full sm:w-1/3 min-w-[140px]">
            <AlignPicker
              value={align}
              onChange={setAlign}
              label={`${isHeader ? 'Header' : 'Footer'} alignment`}
            />
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-[70] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden border border-slate-100 flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-200">
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

        <form onSubmit={handleSubmit} className="flex-grow overflow-y-auto p-6 space-y-5">
          {error && (
            <div className="p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-medium">
              {error}
            </div>
          )}

          {/* Font family and size are shared; alignment is per zone, because a
              title on the left and a page number on the right is the normal case. */}
          <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-2xl space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Font</span>
              <span className="text-[10px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-md font-bold uppercase">
                {doc.file_type.toUpperCase()} Mode
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 mb-1">Font Family</label>
                <select
                  value={fontName}
                  onChange={(e) => setFontName(e.target.value)}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500"
                >
                  {fonts.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </div>

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
            </div>
          </div>

          {/* Insert row: writes into whichever field was last focused. */}
          <div className="p-4 bg-white border border-slate-200/80 rounded-2xl space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Insert into {active.zone} — {activeLabel}
              </span>
              <span className="text-[10px] text-slate-400">
                Focus a field above to choose where these go
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => insertMacro('page')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Hash className="w-3 h-3 text-slate-400" />
                Page Number
              </button>
              <button
                type="button"
                onClick={() => insertMacro('pageOfTotal')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Hash className="w-3 h-3 text-slate-400" />
                Page X of Y
              </button>
              <button
                type="button"
                onClick={() => insertMacro('totalPages')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Hash className="w-3 h-3 text-slate-400" />
                Total Pages
              </button>
              <button
                type="button"
                onClick={() => insertMacro('date')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <Calendar className="w-3 h-3 text-slate-400" />
                Current Date
              </button>
              <button
                type="button"
                onClick={() => insertMacro('title')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
              >
                <FileText className="w-3 h-3 text-slate-400" />
                Document Title
              </button>
            </div>
            <p className="text-[10px] text-slate-400 leading-relaxed">
              These insert live fields, so the page number updates per page instead of
              repeating the same number, and the date stays current.
            </p>
          </div>

          {initialSection !== 'footer' &&
            renderZone(
              'header', header, headerAlign, setHeaderAlign, 'bg-blue-600',
              'Enter header text to appear at the top of every page...'
            )}

          {initialSection !== 'header' &&
            renderZone(
              'footer', footer, footerAlign, setFooterAlign, 'bg-indigo-600',
              'Enter footer text to appear at the bottom of every page...'
            )}

          {/* Preview */}
          <div className="space-y-1.5 pt-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Live Appearance Preview</span>
            <div className="bg-slate-100 rounded-2xl p-4 border border-slate-200">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { key: 'left', page: 2, label: 'Left page (even)' },
                  { key: 'right', page: 1, label: 'Right page (odd)' },
                ].map(({ key, page, label }) => {
                  const headerText = header.firstPage && page === 1 ? header.first : null;
                  const footerText = footer.firstPage && page === 1 ? footer.first : null;
                  const shownHeader =
                    headerText !== null
                      ? headerText
                      : previewText(header.sides ? (page % 2 ? header.odd : header.even) : header.all, { page });
                  const shownFooter =
                    footerText !== null
                      ? footerText
                      : previewText(footer.sides ? (page % 2 ? footer.odd : footer.even) : footer.all, { page });

                  return (
                    <div key={key} className="bg-white rounded-lg border border-slate-300/70 p-3 shadow-sm min-h-[130px] flex flex-col justify-between">
                      <div className="text-[9px] text-slate-400 mb-1 text-center font-semibold uppercase tracking-wider">
                        {label}
                      </div>
                      <div
                        className={`text-[10px] text-slate-600 pb-2 border-b border-dashed border-slate-200 min-h-[20px] ${alignClass(headerAlign)}`}
                        style={{ fontFamily: fontName }}
                      >
                        {shownHeader || <span className="text-slate-300 italic">[No Header]</span>}
                      </div>
                      <div className="py-2 text-[9px] text-slate-300 text-center italic">
                        — Body Content —
                      </div>
                      <div
                        className={`text-[10px] text-slate-600 pt-2 border-t border-dashed border-slate-200 min-h-[20px] ${alignClass(footerAlign)}`}
                        style={{ fontFamily: fontName }}
                      >
                        {shownFooter || <span className="text-slate-300 italic">[No Footer]</span>}
                      </div>
                    </div>
                  );
                })}
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