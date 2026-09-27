import { API_URL, getAuthHeaders, isAuthExpired } from './api';

const FORMAT_INFO = {
  original: { ext: null, type: 'application/octet-stream' },
  pdf: { ext: 'pdf', type: 'application/pdf' },
  docx: { ext: 'docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
  txt: { ext: 'txt', type: 'text/plain;charset=utf-8' },
  pptx: { ext: 'pptx', type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }
};

const sanitizeName = (name) => String(name || '').replace(/[\\/:*?"<>|]/g, '').trim();

// A cold DOCX->PDF conversion shells out to LibreOffice and can take 10-15s the
// first time, and a PDF->PPTX build a couple of seconds. Both are cached
// server-side afterwards, so the slow path is paid once. Callers use onStage to
// show that state rather than leaving a button that looks broken.
export const EXPORT_STAGE = {
  preparing: 'preparing',
  downloading: 'downloading'
};

export const downloadDocument = async (
  token,
  docId,
  filename,
  format = 'original',
  theme = '',
  onStage
) => {
  const params = new URLSearchParams({ format });
  // Only meaningful for PPTX, but harmless to send otherwise; the server falls
  // back to the default theme for names it does not know.
  if (format === 'pptx' && theme) params.set('theme', theme);
  if (onStage) onStage(EXPORT_STAGE.preparing);
  const res = await fetch(`${API_URL}/documents/${docId}/export?${params.toString()}`, {
    headers: getAuthHeaders()
  });

  if (!res.ok) {
    if (isAuthExpired(res)) throw new Error('Your session has expired. Please sign in again.');
    const data = await res.json().catch(() => ({}));
    const detail = data.detail;
    // The server pre-checks whether a document can actually make a good deck
    // and answers 422 with the reasons. Surface them instead of a bare failure.
    if (detail && typeof detail === 'object' && detail.reasons) {
      const err = new Error(detail.message || 'This document is not suitable for a presentation.');
      err.reasons = detail.reasons;
      err.unsuitable = true;
      throw err;
    }
    throw new Error((typeof detail === 'string' && detail) || 'Failed to download document');
  }

  const spec = FORMAT_INFO[format] || FORMAT_INFO.original;
  if (onStage) onStage(EXPORT_STAGE.downloading);
  const blob = await res.blob();
  if (!blob || blob.size === 0) {
    throw new Error('The downloaded file came back empty.');
  }

  const cached = (res.headers.get('X-Export-Cache') || '').toLowerCase() === 'hit';

  const cd = res.headers.get('Content-Disposition') || '';
  const nameMatch = cd && cd.match(/filename="?([^"]+)"?/i);
  let downloadName = nameMatch && nameMatch[1] ? sanitizeName(nameMatch[1]) : null;

  if (!downloadName) {
    const base = sanitizeName(filename).replace(/\.[^.]+$/, '') || `document-${docId}`;
    downloadName = spec.ext ? `${base}.${spec.ext}` : sanitizeName(filename) || `document-${docId}`;
  }

  const url = window.URL.createObjectURL(new Blob([blob], { type: spec.type || blob.type || 'application/octet-stream' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = downloadName;
  document.body.appendChild(link);
  link.click();

  setTimeout(() => {
    link.remove();
    window.URL.revokeObjectURL(url);
  }, 1500);

  return { cached, format };
};

export const downloadFormats = [
  { id: 'original', label: 'Original Format' },
  { id: 'pdf', label: 'PDF' },
  { id: 'docx', label: 'Word (DOCX)' },
  { id: 'txt', label: 'Plain Text (TXT)' },
  { id: 'pptx', label: 'PowerPoint (PPTX)' }
];