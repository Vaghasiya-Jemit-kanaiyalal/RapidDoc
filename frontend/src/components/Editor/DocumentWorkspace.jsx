import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { downloadDocument, downloadFormats } from '../../utils/download';
import { API_URL, getAuthHeaders, isAuthExpired } from '../../utils/api';
import laodingEffect from '../../assets/laoding_effect.png';
import { HeaderFooterEditor } from './HeaderFooterEditor';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ImageResizeDialog } from './ImageResizeDialog';
import { useEditHistory, useUndoRedoShortcuts } from '../../hooks/useEditHistory';
import { DocumentSkeleton, PreviewSkeleton } from './EditorSkeletons';
import { 
  FileText, Download, ChevronDown,
  RefreshCw, AlertTriangle, Save, Loader2, CheckCircle2,
  Send, ZoomIn, X, Wand2, History, ArrowRight, FileSignature, ArrowLeft,
  Sparkles, ListOrdered, Copy, Undo2, Redo2, ImageIcon, Paperclip, Ruler
} from 'lucide-react';

const AI_STATUSES = [
  'Initializing RapidDoc AI',
  'Scanning your document',
  'Finding text blocks',
  'Analyzing content',
  'Applying changes'
];

/**
 * Slide themes offered for PPTX export. The server is the source of truth (it
 * can add more), but seeding the list here means the picker is usable on first
 * paint instead of appearing a beat later.
 */
const PPTX_THEMES = [
  { id: 'modern', label: 'Modern', hint: 'Blue accent, white slides' },
  { id: 'corporate', label: 'Corporate', hint: 'Teal accent, clean layout' },
  { id: 'minimal', label: 'Minimal', hint: 'Greyscale, high contrast' },
];

/** Summary export formats, matching what the server's summary_export accepts. */
const SUMMARY_FORMATS = [
  { value: 'md', label: 'MD' },
  { value: 'txt', label: 'TXT' },
  { value: 'docx', label: 'DOCX' },
  { value: 'pdf', label: 'PDF' },
];

/** Header/footer field codes the editor can insert, e.g. `PAGE`, `DATE`, `TITLE`. */
const FIELD_MACRO_RE = /(\{\s*(?:PAGE|NUMPAGES|DATE|TIME|TITLE|FILENAME)\s*\}|<<\s*(?:PAGE|NUMPAGES|DATE|TIME|TITLE|FILENAME)\s*>>)/gi;

/** Render header/footer text with field macros visually distinguished. */
const renderFieldMacros = (text) => {
  const parts = String(text ?? '').split(FIELD_MACRO_RE);
  if (parts.length === 1) return text;
  return parts.map((part, i) =>
    FIELD_MACRO_RE.test(part) ? (
      <code
        key={i}
        className="rounded bg-slate-100 border border-slate-200 px-1 py-px text-[9px] font-bold text-slate-500"
      >
        {part}
      </code>
    ) : (
      <span key={i}>{part}</span>
    )
  );
};

/**
 * A page header/footer band for the document canvas.
 *
 * This used to be a plain `whitespace-pre-wrap` div that grew to fit whatever
 * text it was given. On a real report that is a disaster: a three-line header
 * (or one long line that wrapped) pushed the body text down, and because the
 * page was `min-h-[700px]` inside a `max-h-[560px]` scroller, the opening
 * paragraphs ended up below the fold with no way to see them - it looked like
 * the header had been pasted over the top of the content.
 *
 * A real Word page gives the header a fixed band and keeps the body separate,
 * so that is what this does:
 *   - `shrink-0` plus a capped height means the band can never grow into the body.
 *   - long text is line-clamped, with the full value kept in `title` so it is
 *     still readable on hover.
 *   - only the first header/footer is drawn, since a multi-section document
 *     would otherwise stack a wall of them; the rest become a "+N more" chip.
 *   - field macros (PAGE / DATE / TITLE) are highlighted so users can tell them
 *     apart from literal text.
 */
const PageBand = ({ kind, values, onEdit }) => {
  const isHeader = kind === 'header';
  const has = values.length > 0;
  const primary = has ? values[0] : '';
  const extra = values.length - 1;
  const accent = isHeader
    ? {
        border: 'border-b-2 border-dashed border-slate-200 hover:border-blue-400',
        hover: 'hover:bg-blue-50/50',
        chip: 'text-blue-600 bg-blue-100 border-blue-200',
      }
    : {
        border: 'border-t-2 border-dashed border-slate-200 hover:border-indigo-400',
        hover: 'hover:bg-indigo-50/50',
        chip: 'text-indigo-600 bg-indigo-100 border-indigo-200',
      };

  return (
    <div
      onClick={onEdit}
      title={has ? values.join('\n\n') : `Click to add / edit Document ${kind}`}
      className={`group relative shrink-0 text-center text-xs ${accent.border} ${accent.hover}
        px-2 py-1.5 rounded-lg cursor-pointer transition duration-150 max-h-[4.5rem] overflow-hidden`}
    >
      {has ? (
        <div
          className="font-medium text-slate-600 text-[10px] leading-snug
                     [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2]
                     overflow-hidden break-words"
        >
          {renderFieldMacros(primary)}
        </div>
      ) : (
        <span className="text-slate-400 italic text-[10px]">
          Click to add / edit Document {kind}...
        </span>
      )}

      {extra > 0 && (
        <span
          className="absolute left-2 top-1/2 -translate-y-1/2 text-[8px] font-bold
                     text-slate-500 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded-md"
        >
          +{extra} more
        </span>
      )}

      <span
        className={`absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100
          transition text-[8px] font-bold uppercase ${accent.chip} border px-2 py-0.5 rounded-md
          pointer-events-none flex items-center gap-1 shadow-xs`}
      >
        <FileSignature className="w-3 h-3" /> Edit {isHeader ? 'Header' : 'Footer'}
      </span>
    </div>
  );
};

/**
 * Addressing for a pending edit.
 *
 * `pendingEdits` is a flat map, and a paragraph index and a table coordinate are
 * both plain numbers - so they would collide and silently overwrite each other.
 * Namespaced string keys keep the two spaces apart, and `normalizeEdit` upgrades
 * the legacy bare-number keys (`{"0": "text"}`, the shape persisted in
 * `draft_edits` by older sessions) so in-flight drafts keep loading.
 */
const paraKey = (index) => `p:${index}`;
const cellKey = (tableIndex, row, col) => `c:${tableIndex}:${row}:${col}`;
const pdfBlockKey = (pageNum, blockNo) => `b:${pageNum}_${blockNo}`;

const normalizeEdit = (key, value) => {
  if (value && typeof value === 'object') return value;
  const cell = /^c:(\d+):(-?\d+):(-?\d+)$/.exec(String(key));
  if (cell) {
    return {
      kind: 'table_cell',
      table_index: Number(cell[1]),
      row: Number(cell[2]),
      col: Number(cell[3]),
      text: String(value ?? ''),
    };
  }
  // PDF blocks were historically keyed "<page>_<block>", either bare (the shape
  // persisted in older draft_edits) or with the `b:` namespace. Recognise both,
  // otherwise `parseInt` would quietly turn "2_5" into paragraph 2.
  const pdf = /^(?:b:)?(\d+)_(\d+)$/.exec(String(key));
  if (pdf) {
    return {
      kind: 'pdf_block',
      page_num: Number(pdf[1]),
      block_no: Number(pdf[2]),
      text: String(value ?? ''),
    };
  }
  return { kind: 'paragraph', index: parseInt(key, 10), text: String(value ?? '') };
};

const normalizeEdits = (edits) => {
  const out = {};
  for (const [key, value] of Object.entries(edits || {})) {
    const edit = normalizeEdit(key, value);
    const k = edit.kind === 'table_cell'
      ? cellKey(edit.table_index, edit.row, edit.col)
      : edit.kind === 'pdf_block'
        ? pdfBlockKey(edit.page_num, edit.block_no)
        : paraKey(edit.index);
    out[k] = edit;
  }
  return out;
};

/**
 * Renders one embedded document image.
 *
 * The bytes live behind an authenticated endpoint, so a plain <img src> would
 * come back as the login payload. Fetching to a blob and revoking it on unmount
 * keeps the image request authorized without leaking object URLs.
 *
 * `version` is part of the effect deps on purpose: the endpoint is keyed by
 * index, so after a replacement the URL is unchanged and the browser would serve
 * the pre-edit bytes from its cache. Bumping `version` is what makes the swap
 * actually visible.
 */
const DocumentImage = ({ docId, index, maxHeight = 220, alt, className = '', version }) => {
  const [url, setUrl] = useState('');
  const [failed, setFailed] = useState(false);
  const urlRef = useRef('');

  useEffect(() => {
    let cancelled = false;
    setUrl('');
    setFailed(false);

    (async () => {
      try {
        const res = await fetch(`${API_URL}/documents/${docId}/images/${index}`, {
          headers: getAuthHeaders(),
          cache: 'no-store',
        });
        if (!res.ok) throw new Error('image request failed');
        const blob = await res.blob();
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob);
        urlRef.current = objectUrl;
        setUrl(objectUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = '';
      }
    };
  }, [docId, index, version]);

  if (failed) {
    return (
      <div className={`flex items-center justify-center border border-dashed border-slate-200 rounded-xl py-6 text-[10px] text-slate-400 italic ${className}`}>
        Image {index + 1} could not be displayed
      </div>
    );
  }

  if (!url) {
    return (
      <div className={`flex items-center justify-center border border-dashed border-slate-200 rounded-xl py-6 ${className}`}>
        <Loader2 className="w-4 h-4 text-slate-300 animate-spin" />
      </div>
    );
  }

  return (
    <img
      src={url}
      alt={alt || `Document image ${index + 1}`}
      style={{ maxHeight: `${maxHeight}px` }}
      className={`mx-auto object-contain rounded-lg ${className}`}
    />
  );
};

/**
 * One image in the document stream, with the double-click-to-replace affordance.
 *
 * Kept as its own component so the hover overlay and the double-click handler
 * exist in one place for both the DOCX and PDF render paths, which are otherwise
 * near-identical for images and would drift apart.
 */
const EditableImageBlock = ({ docId, index, caption, alt, maxHeight, version, onRequestReplace, onRequestResize, replacing }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="my-3 bg-white border border-slate-100 rounded-lg p-2.5 group/image relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onDoubleClick={() => { if (!replacing) onRequestReplace(index); }}
      title="Double-click to replace this image"
    >
      <DocumentImage
        docId={docId}
        index={index}
        maxHeight={maxHeight}
        alt={alt}
        version={version}
      />
      <span className="mt-1.5 inline-block text-[7px] font-bold text-slate-400 uppercase bg-slate-50 border border-slate-100 px-1.5 py-0.5 rounded">
        {caption}
      </span>

      {/* Hover actions. Hidden from touch, where there is no double-click. */}
      {hovered && !replacing && (
        <div className="absolute top-3 right-3 flex items-center gap-1.5 opacity-0 group-hover/image:opacity-100 focus-within:opacity-100 transition pointer-events-none group-hover/image:pointer-events-auto">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onRequestResize(index); }}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-white/95 border border-slate-200 text-slate-600 text-[9px] font-bold uppercase tracking-wide hover:bg-blue-50 hover:text-blue-600 transition"
            tabIndex={-1}
          >
            <Ruler className="w-3 h-3" />
            Resize
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onRequestReplace(index); }}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-slate-900/85 text-[9px] font-bold uppercase tracking-wide text-white hover:bg-slate-900 transition"
            tabIndex={-1}
          >
            <ImageIcon className="w-3 h-3" />
            Replace
          </button>
        </div>
      )}

      {replacing && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/70 rounded-lg">
          <span className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-600">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Replacing…
          </span>
        </div>
      )}
    </div>
  );
};

/**
 * Merge a page's text blocks and images into one top-to-bottom stream.
 *
 * PyMuPDF reports images as separate non-text blocks, so rendering only
 * `page.blocks` is why pictures never appeared in the interactive view. Sorting
 * on the bbox origin puts each image back where it sits on the page.
 */
const interleavePageItems = (page) => {
  const items = (page.blocks || []).map((block) => ({
    kind: 'text',
    top: Array.isArray(block.bbox) ? block.bbox[1] : 0,
    block,
  }));
  const images = (page.images || []).map((image) => ({
    kind: 'image',
    // An image without a bbox still has to be rendered, so park it last
    // rather than letting `undefined` poison the sort comparator.
    top: Array.isArray(image.bbox) ? image.bbox[1] : Number.MAX_SAFE_INTEGER,
    image,
  }));
  return [...items, ...images].sort((a, b) => a.top - b.top);
};

/**
 * Flatten the backend's ordered DOCX block stream for rendering.
 *
 * Paragraph styling still comes from `content` (the descriptor list the save /
 * rewrite / find-replace flows are keyed to), so only tables and images are
 * sourced from `blocks`. Falling back to `content` alone keeps the editor
 * working against a backend that does not send `blocks`.
 */
const buildDocxStream = (blocks, content) => {
  const paragraphs = content || [];
  if (!blocks || !blocks.length) {
    return paragraphs.map((p) => ({ kind: 'paragraph', index: p.index, paragraph: p }));
  }
  const byIndex = new Map(paragraphs.map((p) => [p.index, p]));
  return blocks.map((block) => {
    if (block.kind === 'table') return { kind: 'table', table: block };
    if (block.kind === 'image') return { kind: 'image', image: block };
    return {
      kind: 'paragraph',
      index: block.index,
      paragraph: byIndex.get(block.index) || { index: block.index, text: block.text },
    };
  });
};

/**
 * Look up a table cell's current text in the loaded block stream.
 *
 * The table map is rebuilt on every call, which is fine for the handful of
 * highlight markers a save produces; `TableGrid` uses its own memoized lookup
 * for the hot render path.
 */
const makeCellTextLookup = (stream) => {
  const lookup = new Map();
  for (const item of stream) {
    if (item.kind !== 'table') continue;
    const { table_index: ti, rows } = item.table;
    rows.forEach((row, r) => row.forEach((cellText, c) => {
      lookup.set(cellKey(ti, r, c), cellText || '');
    }));
  }
  return (tableIndex, row, col) => lookup.get(cellKey(tableIndex, row, col)) ?? '';
};

export const DocumentWorkspace = ({ document: initialDoc, token, onBack, onHome }) => {
  const [doc, setDoc] = useState(initialDoc || null);
  
  // Pipeline state
  const [pipelineStage, setPipelineStage] = useState(initialDoc?.pipeline_stage || 1);
  const [completionPercent, setCompletionPercent] = useState(initialDoc?.completion_percent || 25);
  const [pipelineStatus, setPipelineStatus] = useState(initialDoc?.pipeline_status || 'In Progress');
  const [savingProgress, setSavingProgress] = useState(false);


  // Log drawer state

  const [showLogDrawer, setShowLogDrawer] = useState(false);

  // Display font settings (document canvas)
  const [fontName] = useState('Arial');
  const [fontSize] = useState(12);

  // Content state
  const [content, setContent] = useState(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState('');
  // Ordered paragraph/table/image stream from the backend. `content` remains
  // the source of truth for editing because save/rewrite key off its indices.
  const [docBlocks, setDocBlocks] = useState(null);
  const [headerFooter, setHeaderFooter] = useState({ headers: [], footers: [] });
  
  // Header & Footer Modal State
  const [hfModalOpen, setHfModalOpen] = useState(false);
  const [hfInitialSection, setHfInitialSection] = useState('both');
  
  // Editing state
  const [editingIndex, setEditingIndex] = useState(null);
  // `editingIndex` is the key of whichever paragraph/cell is open, so a table
  // cell and a paragraph can never be "the thing being edited" at once.
  const {
    edits: pendingEdits,
    setEdits: setPendingEdits,
    replaceAll: replaceAllEdits,
    reset: resetEdits,
    undo,
    redo,
    canUndo,
    canRedo,
    undoDepth,
    redoDepth,
  } = useEditHistory(normalizeEdits(initialDoc?.draft_edits));
  const [savedEdits, setSavedEdits] = useState({}); // { key: {old, new} } — preview-only markers
  const [savingEdits, setSavingEdits] = useState(false);
  const [saveError, setSaveError] = useState('');

  // Ctrl/Cmd+Z / Ctrl/Cmd+Shift+Z. Disabled while a save is in flight so undo
  // cannot race the server write and resurrect a stale pending map.
  useUndoRedoShortcuts({ undo, redo, enabled: !savingEdits });

  // Sync state if initialDoc changes. Declared after useEditHistory because it
  // depends on `resetEdits`, which is a `const` from that call.
  useEffect(() => {
    if (initialDoc) {
      setDoc(initialDoc);
      setPipelineStage(initialDoc.pipeline_stage || 1);
      setCompletionPercent(initialDoc.completion_percent || 25);
      setPipelineStatus(initialDoc.pipeline_status || 'In Progress');
      // Always re-seed, never merge: switching documents must not carry the
      // previous document's draft across. This has to run for an *empty* draft
      // too - otherwise opening a document you have never edited after one you
      // had been editing leaves the other one's pending edits on screen, and
      // Save would write them into the wrong file.
      resetEdits(normalizeEdits(initialDoc.draft_edits));
    }
  }, [initialDoc, resetEdits]);

  // Block-level AI rewrite
  const [rewriteInstruction, setRewriteInstruction] = useState('');
  const [rewritingIndex, setRewritingIndex] = useState(null);
  const [rewriteBusy, setRewriteBusy] = useState(false);

  // Image replacement state. `imagesVersion` is bumped after a successful swap
  // so every <DocumentImage> refetches - the image endpoint is keyed by index,
  // so without it the browser keeps serving the pre-edit bytes from cache.
  const [imagesVersion, setImagesVersion] = useState(0);
  const [replacingImageIndex, setReplacingImageIndex] = useState(null);
  const [imageReplaceNotice, setImageReplaceNotice] = useState(null); // {tone, text}
  // The index a pending file picker is targeting, and the prompt-bar attachment.
  const pendingImageIndexRef = useRef(null);
  const imagePickInputRef = useRef(null);
  const [promptImage, setPromptImage] = useState(null); // {file, previewUrl}
  const promptImageInputRef = useRef(null);

  // Resizing needs the server's drawn size (a PDF stores pixel data that says
  // nothing about how big the picture prints), so the dialog is fed from
  // GET /images rather than from whatever the tile happens to show.
  const [imageInventory, setImageInventory] = useState([]);
  const [resizeTarget, setResizeTarget] = useState(null); // the chosen inventory entry
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [showImageModule, setShowImageModule] = useState(false);
  const [slashMenuOpen, setSlashMenuOpen] = useState(false);

  // Rollback timeline. `edit_history` below is prose; these are the entries that
  // hold file bytes, which is what makes a restore possible.
  const [versions, setVersions] = useState([]);
  const [restoringVersion, setRestoringVersion] = useState(null);
  const [versionError, setVersionError] = useState('');

  // AI Assistant state
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiProcessing, setAiProcessing] = useState(false);
  const [aiStatusIndex, setAiStatusIndex] = useState(0);
  const [aiResult, setAiResult] = useState('');
  const [aiInteractiveMode, setAiInteractiveMode] = useState('none'); // 'none', 'select_variants'
  const [aiVariantGroups, setAiVariantGroups] = useState([]);
  const [aiSelectedVariants, setAiSelectedVariants] = useState([]);
  const [aiFindText, setAiFindText] = useState('');
  const [aiReplaceText, setAiReplaceText] = useState('');
  const [aiChanges, setAiChanges] = useState([]); // [{paragraph, index, old_text, new_text}]
  const [aiSummary, setAiSummary] = useState(null); // {summary, source, engine, length}
  const [commandHistory, setCommandHistory] = useState([]); // conversation memory for universal command bar
  const [activeSelection, setActiveSelection] = useState(null); // active selected text context

  // Summary exports. The text is whatever is on screen, so what is downloaded is
  // what the user read.
  const [summaryExporting, setSummaryExporting] = useState(null);
  const [summaryExportError, setSummaryExportError] = useState('');
  const [aiQuestions, setAiQuestions] = useState(null); // {questions, requested, engine}
  // Interactive quiz state. `quizPicks` maps question index -> chosen letter;
  // a question is only revealed once it has been answered.
  const [quizPicks, setQuizPicks] = useState({});
  const [quizMode, setQuizMode] = useState(false); // true = answer interactively

  // Preview state
  const [viewMode, setViewMode] = useState('full'); // 'full' (rendered file) | 'edit' (paragraph canvas)

  // PDF preview modal state
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

  // Real rendered document preview (auto-refreshes after every change)
  const [fullPreviewUrl, setFullPreviewUrl] = useState('');
  const [fullPreviewLoading, setFullPreviewLoading] = useState(false);
  const [fullPreviewError, setFullPreviewError] = useState('');
  // A cold LibreOffice render can take 20s+, so the wait shows a live counter
  // instead of an indefinite spinner.
  const [fullPreviewElapsed, setFullPreviewElapsed] = useState(0);

  // The generated preview URL is owned by a ref, not by the cleanup effect on
  // [fullPreviewUrl]: several refreshes can be in flight at once and the effect
  // would revoke a URL the <iframe> had not painted yet.
  const fullPreviewUrlRef = useRef('');
  // Monotonic request id. A slow first conversion used to land *after* a faster
  // second one and overwrite the good PDF with the stale/empty one - which is
  // what made a Word file "fail on load, work on retry".
  const fullPreviewRequestId = useRef(0);

  const replaceFullPreviewUrl = (nextUrl) => {
    const previous = fullPreviewUrlRef.current;
    if (previous && previous !== nextUrl) {
      URL.revokeObjectURL(previous);
    }
    fullPreviewUrlRef.current = nextUrl;
    setFullPreviewUrl(nextUrl);
  };

  // The ordered block stream used to be rebuilt twice per render (once for the
  // emptiness check, once for the map). Memoising it also keeps the reference
  // stable so the table cell-text lookup below is not invalidated on every
  // keystroke elsewhere in the document.
  const docStream = useMemo(
    () => buildDocxStream(docBlocks, content),
    [docBlocks, content]
  );
  const findTableCellText = useMemo(() => makeCellTextLookup(docStream), [docStream]);
  const pendingEditCount = Object.keys(pendingEdits).length;

  const refreshFullPreview = async () => {
    if (!doc?.id) return;
    const requestId = ++fullPreviewRequestId.current;
    const isStale = () => requestId !== fullPreviewRequestId.current;

    setFullPreviewLoading(true);
    setFullPreviewError('');
    setFullPreviewElapsed(0);
    const startedAt = Date.now();
    const ticker = setInterval(
      () => setFullPreviewElapsed(Math.floor((Date.now() - startedAt) / 1000)),
      1000
    );
    try {
      const formData = new FormData();
      formData.append('doc_id', doc.id);
      const res = await fetch(`${API_URL}/docs/preview`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to render document preview.');
      }
      const blob = await res.blob();
      if (isStale()) return; // a newer request already won
      // Side effects stay out of the state updater on purpose: React may call
      // an updater twice, and revoking inside it destroyed the new URL.
      replaceFullPreviewUrl(URL.createObjectURL(blob));
    } catch (err) {
      if (isStale()) return;
      setFullPreviewError(err.message || 'Error rendering document preview.');
    } finally {
      clearInterval(ticker);
      if (!isStale()) setFullPreviewLoading(false);
    }
  };

  useEffect(() => {
    if (doc?.id) {
      refreshFullPreview();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc?.id]);

  // Revoke the generated object URL when it changes or on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  // Release the last rendered preview on unmount so the blob is not leaked.
  useEffect(() => {
    return () => {
      // Invalidate any in-flight request so it cannot resurrect a URL after
      // the component is gone.
      fullPreviewRequestId.current += 1;
      if (fullPreviewUrlRef.current) {
        URL.revokeObjectURL(fullPreviewUrlRef.current);
        fullPreviewUrlRef.current = '';
      }
    };
  }, []);

  // Cycle the Gemini-style status messages while AI is processing
  useEffect(() => {
    if (!aiProcessing) return;
    setAiStatusIndex(0);
    const interval = setInterval(() => {
      setAiStatusIndex((i) => (i + 1) % AI_STATUSES.length);
    }, 950);
    return () => clearInterval(interval);
  }, [aiProcessing]);

  // Stable across renders so the effect below can depend on them without
  // refetching on every render. These are also called directly after a save /
  // rewrite / AI edit, which is why they are not effect-local.
  const fetchContent = useCallback(async () => {
    setLoadingContent(true);
    setContentError('');
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/content`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      if (!res.ok) {
        // FastAPI puts the text in `detail`; the hand-built 409 ambiguous-target
        // body uses `message`. Reading only `detail` turned "Page 1 has 2 images.
        // Which one should I replace?" into a generic failure.
        throw new Error(data.detail || data.message || 'The image could not be replaced.');
      }
      setContent(data.content);
      // Tables and images are additive fields; an older backend simply omits
      // them and the editor keeps working with paragraphs alone.
      setDocBlocks(data.blocks || null);
    } catch (err) {
      setContentError(err.message || 'Error loading content.');
    } finally {
      setLoadingContent(false);
    }
  }, [doc.id]);

  const fetchHeaderFooter = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/headers-footers`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      if (res.ok) {
        const toText = (v) => {
          if (v == null) return '';
          if (typeof v === 'string') return v;
          if (typeof v === 'object') return String(v.text ?? '') || String(v.section ?? '');
          return String(v);
        };
        setHeaderFooter({
          ...data,
          headers: (data.headers || []).map(toText),
          footers: (data.footers || []).map(toText)
        });
      }
    } catch {
      // non-fatal; header/footer display is best-effort
    }
  }, [doc.id]);

  useEffect(() => {
    fetchContent();
    fetchHeaderFooter();
  }, [fetchContent, fetchHeaderFooter]);

  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState('');
  const [downloadStage, setDownloadStage] = useState('');
  // Slide theme for PPTX export. Kept in step with the server's list, but with
  // a local default so the picker renders before (or without) that request.
  const [pptxTheme, setPptxTheme] = useState(PPTX_THEMES[0].id);
  const [pptxThemes, setPptxThemes] = useState(PPTX_THEMES);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetch(`${API_URL}/documents/export/themes`, { headers: getAuthHeaders() })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data?.themes?.length) return;
        const known = new Set(PPTX_THEMES.map((t) => t.id));
        const extra = data.themes
          .filter((id) => !known.has(id))
          .map((id) => ({ id, label: id.charAt(0).toUpperCase() + id.slice(1), hint: `${id} slide theme` }));
        if (extra.length) setPptxThemes((current) => [...current, ...extra]);
        if (data.default && known.has(data.default)) setPptxTheme(data.default);
      })
      .catch(() => {
        // Non-fatal: the built-in themes are still selectable.
      });
    return () => { cancelled = true; };
  }, [token]);

  // Track user text selection across the document workspace
  useEffect(() => {
    const handleSelection = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) return;
      const text = sel.toString().trim();
      if (text && text.length > 0) {
        setActiveSelection({ text, type: 'text' });
      }
    };
    document.addEventListener('selectionchange', handleSelection);
    return () => document.removeEventListener('selectionchange', handleSelection);
  }, []);

  // Auto-dismiss the "Changes applied" card and success result notice after 2 seconds
  useEffect(() => {
    const isChangeNotification =
      aiChanges.length > 0 ||
      (aiResult &&
        (aiResult.startsWith('Applied ') ||
          aiResult.startsWith('Updated ') ||
          aiResult.startsWith('Changed ') ||
          aiResult.startsWith('Done — ') ||
          aiResult.startsWith('Done - ') ||
          aiResult.includes('replaced successfully')));

    if (isChangeNotification) {
      const timer = setTimeout(() => {
        setAiChanges([]);
        setAiResult((prev) => (prev && !prev.startsWith('Error') ? '' : prev));
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [aiChanges, aiResult]);

  const handleDownload = async (format = 'original', theme) => {
    const chosen = format === 'pptx' ? (theme || pptxTheme) : '';
    if (chosen) setPptxTheme(chosen);
    setDownloadError('');
    setDownloading(format);
    try {
      await downloadDocument(token, doc.id, doc.name, format, chosen, (stage) => {
        setDownloadStage(stage);
      });
    } catch (err) {
      setDownloadError(err.message || 'Error downloading document.');
    } finally {
      setDownloading('');
      setDownloadStage('');
    }
  };

  /**
   * Download the summary currently on screen.
   *
   * The blob is saved through an object URL rather than a plain link so the
   * filename can come from the server's Content-Disposition header - a generated
   * one would not match what the export route decided to call it.
   */
  const handleExportSummary = async (format) => {
    if (!aiSummary?.summary) return;
    setSummaryExporting(format);
    setSummaryExportError('');
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/summary/export`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summary: aiSummary.summary,
          key_points: aiSummary.key_points || [],
          source: aiSummary.source,
          engine: aiSummary.engine,
          characters: aiSummary.characters,
          title: doc.name?.replace(/\.[^/.]+$/, '') || 'Summary',
          format,
        }),
      });
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'The summary could not be exported.');
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${(doc.name || 'document').replace(/\.[^/.]+$/, '')}-summary.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setSummaryExportError(err.message || 'The summary could not be exported.');
    } finally {
      setSummaryExporting(null);
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    setPreviewError('');
    try {
      const formData = new FormData();
      formData.append('doc_id', doc.id);

      const res = await fetch(`${API_URL}/docs/preview`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to generate PDF preview.');
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setPreviewUrl(url);
      setPreviewOpen(true);
    } catch (err) {
      setPreviewError(err.message || 'Error generating PDF preview.');
      setPreviewOpen(true);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSaveEdits = async () => {
    const entries = Object.values(pendingEdits);
    if (entries.length === 0) return;

    setSavingEdits(true);
    setSaveError('');
    try {
      let editsPayload = [];
      const nextSavedEdits = { ...savedEdits };
      if (doc.file_type === 'docx') {
        editsPayload = entries.map((edit) => {
          if (edit.kind === 'table_cell') {
            const { table_index, row, col, text } = edit;
            nextSavedEdits[cellKey(table_index, row, col)] = {
              old: findTableCellText(table_index, row, col),
              new: text,
            };
            return { kind: 'table_cell', table_index, row, col, text };
          }
          const { index, text } = edit;
          const oldText = (content || []).find((c) => c.index === index)?.text ?? '';
          nextSavedEdits[paraKey(index)] = { old: oldText, new: text };
          return { kind: 'paragraph', index, text };
        });
      } else {
        // PDF payload matches TextEditItem model
        editsPayload = entries;
        editsPayload.forEach((p) => {
          const key = pdfBlockKey(p.page_num, p.block_no);
          const pg = (content || []).find((x) => x.page_num === p.page_num);
          const oldText = pg?.blocks?.find((b) => b.block_no === p.block_no)?.text ?? '';
          nextSavedEdits[key] = { old: oldText, new: p.text };
        });
      }

      const res = await fetch(`${API_URL}/documents/${doc.id}/content`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ edits: editsPayload })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save edits');
      }
      setDoc(data);
      // Clearing through `replaceAll` keeps "save" as a single undo step, so a
      // mis-click can be taken back instead of losing the edits outright.
      replaceAllEdits({});
      setSavedEdits(nextSavedEdits);
      setEditingIndex(null);
      await fetchContent();
      await fetchHeaderFooter();
      await refreshDoc();
      await refreshFullPreview();
      setViewMode('full');
    } catch (err) {
      // Kept in-panel rather than an alert(): the pending edits are still intact
      // and the user needs to see the message next to the Save button they hit.
      const message = err?.message || 'Error saving changes.';
      setSaveError(message);
      if (err?.name === 'AbortError') return;
    } finally {
      setSavingEdits(false);
    }
  };

  /**
   * Double-click / hover "Replace" on an image: remember which one, then open
   * the OS file picker. The chosen index lives in a ref rather than state
   * because it is only read once, inside the change handler.
   */
  const requestImageReplace = (index) => {
    if (replacingImageIndex !== null) return;
    pendingImageIndexRef.current = index;
    imagePickInputRef.current?.click();
  };

  /**
   * Fetch full list of detected images in this document for the image module and resizing.
   */
  const fetchImageInventory = useCallback(async () => {
    setInventoryLoading(true);
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/images`, {
        headers: getAuthHeaders(),
      });
      if (isAuthExpired(res)) return [];
      const data = await res.json();
      if (res.ok) {
        const images = data.images || [];
        setImageInventory(images);
        return images;
      }
    } catch (err) {
      console.error('Failed to load image inventory:', err);
    } finally {
      setInventoryLoading(false);
    }
    return [];
  }, [doc.id]);

  /**
   * Hover "Resize" on an image: open the sizing dialog with the server's own
   * numbers. The inventory is fetched on demand and cached, because the drawn
   * size changes as soon as a resize is applied - it is dropped at the same time
   * `imagesVersion` is bumped.
   */
  const requestImageResize = async (index) => {
    const cached = imageInventory.find((img) => img.index === index);
    if (cached) {
      setResizeTarget(cached);
      return;
    }
    // Two quick hovers would otherwise fire two identical inventory requests.
    if (inventoryLoading) return;

    setInventoryLoading(true);
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/images`, {
        headers: getAuthHeaders(),
      });
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'The image list could not be loaded.');
      }
      const images = data.images || [];
      setImageInventory(images);
      const target = images.find((img) => img.index === index);
      if (!target) throw new Error('That image is no longer in this document.');
      setResizeTarget(target);
    } catch (err) {
      setImageReplaceNotice({ tone: 'error', text: err.message || 'The image could not be opened for resizing.' });
    } finally {
      setInventoryLoading(false);
    }
  };

  /**
   * Load the rollback timeline. Cheap enough to refetch after every edit, and
   * doing so is what keeps the list honest - a restore rewrites the timeline.
   */
  const loadVersions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/versions`, {
        headers: getAuthHeaders(),
      });
      if (isAuthExpired(res)) return;
      const data = await res.json();
      if (res.ok) setVersions(data.versions || []);
    } catch {
      // A missing timeline must not take the editor down with it.
    }
  }, [doc.id]);

  useEffect(() => { loadVersions(); }, [loadVersions]);

  const handleRestoreVersion = async (version) => {
    const id = version.is_original ? 'original' : version.version_id;
    setRestoringVersion(id);
    setVersionError('');
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/versions/${id}/restore`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'That version could not be restored.');
      }
      setVersions(data.versions || []);
      // The restored file is a different document: every tile, the preview and
      // the cached edit log all have to come back from the server.
      setImagesVersion((v) => v + 1);
      setImageInventory([]);
      setImageReplaceNotice({ tone: 'success', text: data.message || 'Version restored.' });
      setSavedEdits({});
      setPendingEdits({});
      setAiChanges([]);
      await refreshDoc();
      refreshFullPreview();
    } catch (err) {
      setVersionError(err.message || 'That version could not be restored.');
    } finally {
      setRestoringVersion(null);
    }
  };

  /** POST the picked file to /replace-image against an explicit index. */
  const uploadReplacementForIndex = async (index, file) => {
    setReplacingImageIndex(index);
    setImageReplaceNotice(null);
    try {
      const body = new FormData();
      body.append('image_file', file);
      body.append('image_index', String(index));
      body.append('size_mode', 'fit');

      const res = await fetch(`${API_URL}/documents/${doc.id}/replace-image`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body,
      });
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'The image could not be replaced.');
      }
      // Refetch every image: the endpoint is keyed by index, so this is the
      // only thing that makes the new bytes visible.
      setImagesVersion((v) => v + 1);
      setImageReplaceNotice({ tone: 'success', text: data.message || 'Image replaced.' });
      setAiResult(data.message || 'Image replaced.');
      refreshFullPreview();
    } catch (err) {
      setImageReplaceNotice({ tone: 'error', text: err.message || 'The image could not be replaced.' });
    } finally {
      setReplacingImageIndex(null);
    }
  };

  const handleImagePick = (e) => {
    const file = e.target.files?.[0];
    const index = pendingImageIndexRef.current;
    // Reset immediately so picking the same file twice still fires onchange.
    e.target.value = '';
    if (!file || index === null) return;
    uploadReplacementForIndex(index, file);
  };

  /** Prompt-bar attachment: preview it locally, upload only once a target is known. */
  const handlePromptImagePick = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (promptImage?.previewUrl) URL.revokeObjectURL(promptImage.previewUrl);
    setPromptImage({ file, previewUrl: URL.createObjectURL(file) });
    setShowImageModule(true);
    fetchImageInventory();
    if (!aiPrompt.trim() || aiPrompt === '/image') {
      setAiPrompt('replace the image 1 by this');
    }
  };

  /** Clipboard paste support for command bar */
  const handleCommandPaste = (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          e.preventDefault();
          if (promptImage?.previewUrl) URL.revokeObjectURL(promptImage.previewUrl);
          const ext = item.type.split('/')[1] || 'png';
          const namedFile = new File([file], `pasted-image-${Date.now()}.${ext}`, { type: item.type });
          setPromptImage({ file: namedFile, previewUrl: URL.createObjectURL(namedFile), isPasted: true });
          setShowImageModule(true);
          fetchImageInventory();
          if (!aiPrompt.trim() || aiPrompt === '/image') {
            setAiPrompt('replace the image 1 by this');
          }
          break;
        }
      }
    }
  };

  const clearPromptImage = () => {
    if (promptImage?.previewUrl) URL.revokeObjectURL(promptImage.previewUrl);
    setPromptImage(null);
  };

  useEffect(() => () => {
    if (promptImage?.previewUrl) URL.revokeObjectURL(promptImage.previewUrl);
  }, [promptImage]);

  /**
   * Upload the attached image against a target the backend has already
   * validated. A 409 means the phrase was ambiguous, so the server sent
   * candidates back and the user has to choose - one at a time, never all.
   */
  const uploadPromptReplacement = async (index, file, command) => {
    setReplacingImageIndex(index);
    setImageReplaceNotice(null);
    try {
      const body = new FormData();
      body.append('image_file', file);
      body.append('image_index', String(index));
      if (command) body.append('command', command);
      body.append('size_mode', 'fit');

      const res = await fetch(`${API_URL}/documents/${doc.id}/replace-image`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body,
      });
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      const data = await res.json();
      if (res.status === 409 && data.candidates?.length) {
        // The target became ambiguous between resolution and upload. Show the
        // picker rather than a dead end; the attachment is kept.
        setAiVariantGroups(data.candidates);
        setAiInteractiveMode('select_image');
        setAiResult(data.message || 'Which image should I replace?');
        return;
      }
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'The image could not be replaced.');
      }
      setImagesVersion((v) => v + 1);
      const text = data.message || `Image ${index + 1} replaced successfully.`;
      setImageReplaceNotice({ tone: 'success', text });
      setAiResult(text);
      setAiInteractiveMode('none');
      clearPromptImage();
      refreshFullPreview();
      fetchImageInventory();
    } catch (err) {
      setImageReplaceNotice({ tone: 'error', text: err.message || 'The image could not be replaced.' });
    } finally {
      setReplacingImageIndex(null);
    }
  };

  const handleAiSubmit = async (e) => {
    e?.preventDefault();
    const prompt = aiPrompt.trim();
    const attachedFile = promptImage?.file || null;
    if ((!prompt && !attachedFile) || aiProcessing) return;

    // Direct /image command support
    const lower = prompt.toLowerCase();
    if (lower === '/image' || lower === '/images' || lower === 'image' || lower === '/img') {
      setAiPrompt('');
      setShowImageModule(true);
      setAiProcessing(true);
      try {
        const imgs = await fetchImageInventory();
        const count = imgs.length;
        setAiResult(
          count > 0
            ? `📸 Image Module: Detected ${count} image${count !== 1 ? 's' : ''} (numbered 1 to ${count}) in this document. Paste or select an image to replace.`
            : 'No images detected in this document.'
        );
      } catch (err) {
        setAiResult(`Error loading images: ${err.message}`);
      } finally {
        setAiProcessing(false);
      }
      return;
    }

    // Direct "replace the image 1 by this" support when an image is attached/pasted
    if (attachedFile) {
      const match = prompt.match(/\b(?:replace|replce|swap|change|put)\s+(?:the\s+)?(?:image|picture|photo|#|number\s+|no\.?\s*)?(\d+)\b/i)
        || prompt.match(/\b(?:the\s+)?(?:image|picture|photo)\s+(?:#|number\s+|no\.?\s*)?(\d+)\b/i);

      if (match) {
        const num = parseInt(match[1], 10);
        if (num >= 1) {
          const targetIndex = num - 1;
          setAiProcessing(true);
          setAiPrompt('');
          setAiResult(`Replacing Image ${num} with uploaded picture...`);
          try {
            await uploadPromptReplacement(targetIndex, attachedFile, prompt);
          } finally {
            setAiProcessing(false);
          }
          return;
        }
      }
    }

    setAiProcessing(true);
    setAiPrompt('');
    setAiResult('');
    setAiInteractiveMode('none');
    setAiVariantGroups([]);
    setAiSelectedVariants([]);
    setAiChanges([]);
    setAiSummary(null);
    setAiQuestions(null);
    setQuizPicks({});
    setQuizMode(false);

    let imageBase64 = null;
    if (attachedFile) {
      try {
        imageBase64 = await new Promise((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => resolve(null);
          reader.readAsDataURL(attachedFile);
        });
      } catch (err) {
        console.warn('Failed to encode image to base64', err);
      }
    }

    try {
      const controller = new AbortController();
      const timeoutMs = 240000;
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
      const res = await fetch(`${API_URL}/documents/${doc.id}/ai-command`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          command: prompt,
          has_image_upload: !!attachedFile,
          image_base64: imageBase64,
          selection: activeSelection,
          history: commandHistory.slice(-8),
        }),
        signal: controller.signal
      }).finally(() => clearTimeout(timeoutId));
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'AI command failed');
      }

      // Record in conversation history for reference resolution
      setCommandHistory((prev) => [
        ...prev,
        { role: 'user', command: prompt },
        { role: 'assistant', action: data.action, result: data.message || '' },
      ]);

      if (data.action === 'image_module') {
        setShowImageModule(true);
        if (data.images) {
          setImageInventory(data.images);
        }
        setAiResult(data.message || `Detected ${data.count || 0} image(s).`);
      } else if (data.action === 'replace_image') {
        if (data.status === 'resolved' && attachedFile) {
          await uploadPromptReplacement(data.indexes[0], attachedFile, prompt);
        } else if (data.status === 'ambiguous' && attachedFile) {
          setAiVariantGroups(data.candidates || []);
          setAiInteractiveMode('select_image');
          setAiResult(data.message || 'Which image should I replace?');
        } else if (data.status === 'resolved') {
          setImageReplaceNotice({
            tone: 'success',
            text: `Image ${data.indexes[0] + 1} selected. Attach a picture to finish the replacement.`,
          });
        } else {
          setAiResult(data.message || 'Tell me which image to replace.');
        }
      } else if (data.action === 'image_replaced') {
        setAiResult(data.message || 'Done — replaced image.');
        clearPromptImage();
        setViewMode('full');
        await fetchContent();
        await fetchImageInventory();
        await refreshDoc();
        refreshFullPreview();
      } else if (data.action === 'replace_applied') {
        if (data.changes) {
          setAiChanges(data.changes);
        }
        setAiResult(data.message || `Done — replaced ${data.matches_replaced || 0} occurrence(s).`);
        setViewMode('full');
        await fetchContent();
        await refreshDoc();
        refreshFullPreview();
      } else if (data.action === 'replace') {
        if (data.total_matches === 0) {
          setAiResult(`I searched for "${data.find_text}" but found no matches.`);
        } else {
          setAiFindText(data.find_text);
          setAiReplaceText(data.replace_text);
          setAiVariantGroups(data.groups || []);
          setAiInteractiveMode('select_variants');
          setAiResult(
            `I found ${data.total_matches} occurrence(s) of "${data.find_text}" across ${data.groups.length} variant group(s). Select which to change:`
          );
        }
      } else if (data.action === 'header' || data.action === 'footer') {
        if (data.changes) {
          setAiChanges(data.changes);
        }
        setAiResult(data.message || `Updated the ${data.action}.`);
        setViewMode('full');
        await fetchContent();
        await fetchHeaderFooter();
        await refreshDoc();
        refreshFullPreview();
      } else if (data.action === 'style_headings' || data.action === 'style_document') {
        setAiResult(data.message || 'Done — applied formatting.');
        setViewMode('full');
        await fetchContent();
        await refreshDoc();
        refreshFullPreview();
      } else if (data.action === 'delete_column' || data.action === 'delete_row' || data.action === 'delete_table') {
        setAiResult(data.message || 'Done — updated table.');
        setViewMode('full');
        await fetchContent();
        await refreshDoc();
        refreshFullPreview();
      } else if (data.action === 'delete_image') {
        setAiResult(data.message || 'Done — removed image(s).');
        setViewMode('full');
        await fetchContent();
        await fetchImageInventory();
        await refreshDoc();
        refreshFullPreview();
      } else if (data.action === 'describe_image') {
        setAiSummary({
          summary: `# Image Analysis\n\n${data.description || data.message}`,
          source: 'image',
          engine: data.engine || 'gemini_vision',
        });
        setAiResult(data.description ? data.description.slice(0, 140) + '...' : data.message);
      } else if (data.action === 'summarize') {
        setAiSummary(data);
        setAiResult(
          data.length
            ? `Summary (${data.source}, ${data.length}):`
            : `Summary (${data.source}):`
        );
      } else if (data.action === 'generate_mcq') {
        setAiQuestions(data);
        setQuizPicks({});
        setQuizMode(false);
        const got = (data.questions || []).length;
        const from = data.source ? ` from ${data.source}` : '';
        setAiResult(
          got === 0
            ? 'I could not build any questions from this document.'
            : got < (data.requested || got)
              ? `Generated ${got} of ${data.requested} requested question(s)${from}.`
              : `Generated ${got} question(s)${from}.`
        );
      } else if (data.action === 'rewrite') {
        setAiResult(data.message || 'Rewritten text:');
        if (data.rewritten_text) {
          setAiSummary({
            summary: `# Rewritten Text\n\n${data.rewritten_text}`,
            source: data.source || 'document',
            engine: data.engine || 'local',
          });
        }
      } else if (data.action === 'qa_extract') {
        setAiSummary({
          summary: `# Document Analysis & Notes\n\n${data.answer || data.message}`,
          source: 'document',
          engine: data.engine || 'gemini',
        });
        setAiResult(data.message ? (data.message.length > 120 ? data.message.slice(0, 120) + '...' : data.message) : 'Done.');
      } else if (data.action === 'composite') {
        setAiResult(data.message || 'Done — processed all operations.');
        setViewMode('full');
        await fetchContent();
        await refreshDoc();
        refreshFullPreview();
        if (data.summary) {
          setAiSummary({
            summary: data.summary,
            source: 'document',
            engine: 'universal',
          });
        }
        if (data.questions) {
          setAiQuestions({
            questions: data.questions,
            requested: data.questions.length,
            engine: 'universal',
          });
          setQuizPicks({});
          setQuizMode(false);
        }
      } else {
        setAiResult(data.message || 'I scanned your document. Try e.g. \'Change print to not print\' or \'Change the header to RapidDoc Report\'.');
      }
    } catch (err) {
      setAiResult(`Error: ${err.message}`);
      if (err?.name !== 'AbortError') {
        setAiPrompt((current) => (current.trim() ? current : prompt));
      }
    } finally {
      setAiProcessing(false);
      setAiStatusIndex(0);
    }
  };

  const refreshDoc = async () => {
    try {
      const docRes = await fetch(`${API_URL}/documents`, {
        headers: getAuthHeaders()
      });
      const docList = await docRes.json();
      const updatedDoc = docList.find(d => d.id === doc.id);
      if (updatedDoc) {
        setDoc(updatedDoc);
      }
    } catch {
      // best-effort refresh
    }
  };

  const handleApplySelectedVariants = async () => {
    if (aiSelectedVariants.length === 0) {
      setAiResult('No variants selected. Nothing was changed.');
      return;
    }
    setAiProcessing(true);
    setAiChanges([]);
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/selective-replace`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          find_text: aiFindText,
          replace_text: aiReplaceText,
          selected_variants: aiSelectedVariants,
          case_sensitive: false
        })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Replace failed');
      }
      setAiChanges(data.changes || []);
      setAiInteractiveMode('none');
      setAiResult(
        data.matches_replaced > 0
          ? `Applied "${aiReplaceText}" to ${data.matches_replaced} occurrence(s). Changed text is highlighted below.`
          : 'No matches were replaced.'
      );
      setAiPrompt('');
      setViewMode('full');
      await fetchContent();
      await fetchHeaderFooter();
      await refreshDoc();
      await refreshFullPreview();
    } catch (err) {
      setAiResult(`Error: ${err.message}`);
    } finally {
      setAiProcessing(false);
      setAiStatusIndex(0);
    }
  };

  // Feature 3: highlight only the part of the text that actually changed
  const highlightDiff = (oldText, newText) => {
    if (!oldText && !newText) return '';
    if (!oldText) {
      return <mark className="bg-amber-200 text-amber-950 font-bold px-1 rounded">{newText}</mark>;
    }
    if (!newText) return newText;
    if (oldText === newText) return newText;

    let prefixLen = 0;
    while (prefixLen < oldText.length && prefixLen < newText.length && oldText[prefixLen] === newText[prefixLen]) {
      prefixLen++;
    }
    let suffixLen = 0;
    while (
      suffixLen < oldText.length - prefixLen &&
      suffixLen < newText.length - prefixLen &&
      oldText[oldText.length - 1 - suffixLen] === newText[newText.length - 1 - suffixLen]
    ) {
      suffixLen++;
    }
    const start = prefixLen;
    const end = newText.length - suffixLen;
    if (start >= end) {
      return <mark className="bg-amber-200 text-amber-950 font-semibold px-1 rounded">{newText}</mark>;
    }
    return (
      <>
        {newText.slice(0, start)}
        <mark className="bg-amber-200 text-amber-950 font-semibold px-1 py-0.5 rounded shadow-2xs">
          {newText.slice(start, end)}
        </mark>
        {newText.slice(end)}
      </>
    );
  };

  const handleRewriteBlock = async (source) => {
    const instruction = (rewriteInstruction || 'Improve this text. Keep its original meaning and formatting.').trim();
    const key = source.key;
    setRewriteBusy(true);
    setRewritingIndex(key);
    try {
      const body = { instruction, text: source.text || undefined };
      if (doc.file_type === 'docx') {
        body.index = source.index;
        delete body.page_num;
        delete body.block_no;
      } else {
        body.page_num = source.page_num;
        body.block_no = source.block_no;
        delete body.index;
      }
      const res = await fetch(`${API_URL}/documents/${doc.id}/rewrite`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'AI rewrite failed');
      }
      const rewritten = (data.rewritten_text ?? '').trim();
      if (!rewritten) {
        throw new Error('The AI returned an empty rewrite.');
      }
      if (doc.file_type === 'docx') {
        setPendingEdits((prev) => ({ ...prev, [source.index]: rewritten }));
      } else {
        setPendingEdits((prev) => ({
          ...prev,
          [key]: {
            page_num: source.page_num,
            block_no: source.block_no,
            bbox: source.bbox,
            text: rewritten
          }
        }));
      }
      const engineLabel = data.engine === 'gemini' ? 'Gemini (cloud fallback)' : data.engine === 'local' ? 'Local Brain Model' : 'RapidDoc AI';
      setAiResult(`Rewritten by ${engineLabel}. Review the highlighted text, then press Save Changes.`);
      setRewriteInstruction('');
    } catch (err) {
      setAiResult(`AI rewrite failed: ${err.message}`);
    } finally {
      setRewriteBusy(false);
      setRewritingIndex(null);
    }
  };

  const handleHfSaveSuccess = async (updatedDoc) => {
    if (updatedDoc) setDoc(updatedDoc);
    setPipelineStage(prev => Math.max(2, prev));
    setCompletionPercent(prev => Math.max(50, prev));
    await fetchHeaderFooter();
    await fetchContent();
    await refreshDoc();
    await refreshFullPreview();
  };

  const persistStage = async (stage) => {
    try {
      await fetch(`${API_URL}/documents/${doc.id}/pipeline`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          pipeline_stage: stage,
          completion_percent: Math.min(100, stage * 25),
          pipeline_status: stage === 4 ? 'Finalized' : 'In Progress',
          draft_edits: pendingEdits
        })
      });
    } catch {
      // best-effort persistence
    }
  };

  const handleSaveProgress = async () => {
    setSavingProgress(true);
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/pipeline`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          pipeline_stage: pipelineStage,
          completion_percent: completionPercent,
          pipeline_status: pipelineStage === 4 ? 'Finalized' : (pipelineStatus || 'In Progress'),
          draft_edits: pendingEdits
        })
      });
      if (!res.ok) {
        const msg = isAuthExpired(res) ? 'Your session has expired. Please sign in again.' : 'Failed to save pipeline checkpoint';
        throw new Error(msg);
      }
      if (onBack) onBack();
    } catch (err) {
      alert(err.message || 'Error saving progress');
    } finally {
      setSavingProgress(false);
    }
  };

  const handleFinalizePipeline = async () => {
    setSavingProgress(true);
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/pipeline`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          pipeline_stage: 4,
          completion_percent: 100,
          pipeline_status: 'Finalized',
          draft_edits: {}
        })
      });
      if (isAuthExpired(res)) {
        throw new Error('Your session has expired. Please sign in again.');
      }
      const data = await res.json();
      if (res.ok) {
        setPipelineStage(4);
        setCompletionPercent(100);
        setPipelineStatus('Finalized');
        setDoc(data);
      }
    } catch (err) {
      alert(err.message || 'Error finalizing pipeline');
    } finally {
      setSavingProgress(false);
    }
  };

  if (!doc) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 text-center">
        <div className="p-6 bg-white rounded-3xl shadow-card border border-borderline max-w-md w-full space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-bold text-ink">No Document Selected</h3>
          <p className="text-xs text-secondary">Please choose a document from your dashboard or upload a new one to start editing.</p>
          <div className="flex gap-2 justify-center pt-2">
            <button 
              onClick={onBack || onHome} 
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs rounded-xl shadow-xs cursor-pointer"
            >
              Go to Dashboard
            </button>
            <button 
              onClick={onHome} 
              className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-ink font-bold text-xs rounded-xl cursor-pointer"
            >
              Home
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-slate-50 overflow-hidden relative">
      {/* Slim Top Bar */}
      <div className="shrink-0 bg-white border-b border-slate-100 px-4 sm:px-6 py-2.5 flex justify-between items-center gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onBack || onHome}
            className="flex items-center gap-1.5 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-extrabold rounded-full text-xs transition border border-slate-200 shadow-xs shrink-0 cursor-pointer"
            title="Back to Dashboard"
          >
            <ArrowLeft className="w-4 h-4 text-slate-700" />
            <span>Back</span>
          </button>
          <div className={`p-2 rounded-xl shrink-0 ${
            doc.file_type === 'pdf' ? 'bg-red-50 text-red-600' : 'bg-blue-50 text-blue-600'
          }`}>
            <FileText className="w-4 h-4" />
          </div>
          <div className="text-left min-w-0">
            <h2 className="font-bold text-slate-800 text-sm truncate">{doc.name}</h2>
            <span className="text-[9px] uppercase font-bold text-slate-400">{doc.file_type} File</span>
            {doc.has_edited_version && (
              <span className="text-[8px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-md ml-1">
                Edited copy • original saved
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {downloadError && (
            <button
              onClick={() => setDownloadError('')}
              title={downloadError}
              className="flex items-center gap-1.5 px-3 py-2 bg-red-50 border border-red-200 text-red-700 font-semibold rounded-xl text-[10px] max-w-[220px] transition hover:bg-red-100"
            >
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">{downloadError}</span>
            </button>
          )}
          <button
            onClick={() => { setHfInitialSection('both'); setHfModalOpen(true); }}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-gradient-to-r from-blue-50 to-indigo-50 hover:from-blue-100 hover:to-indigo-100 border border-blue-200/80 text-blue-700 font-bold rounded-xl text-xs transition shadow-xs"
            title="Edit Document Header & Footer"
          >
            <FileSignature className="w-3.5 h-3.5 text-blue-600" />
            <span>Header & Footer</span>
            {(headerFooter.headers.length > 0 || headerFooter.footers.length > 0) && (
              <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
            )}
          </button>
          <button
            onClick={handlePreview}
            disabled={previewLoading}
            className="px-3.5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl text-xs flex items-center gap-2 shadow-sm transition"
            title="Generate a live PDF preview of this document"
          >
            {previewLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <ZoomIn className="w-3.5 h-3.5" />
            )}
            <span>{previewLoading ? 'Generating...' : 'Preview PDF'}</span>
          </button>
          <div className="relative">
            <button
              onClick={() => setDownloadMenuOpen(o => !o)}
              disabled={!!downloading}
              className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 disabled:cursor-wait text-white font-semibold rounded-xl text-xs flex items-center gap-2 shadow-sm transition"
              title="Download the document"
            >
              {downloading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              <span>
                {downloading
                  ? (downloadStage === 'preparing' ? 'Preparing…' : 'Downloading…')
                  : 'Download'}
              </span>
              {!downloading && <ChevronDown className={`w-3.5 h-3.5 transition ${downloadMenuOpen ? 'rotate-180' : ''}`} />}
            </button>
            {downloadMenuOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setDownloadMenuOpen(false)} />
                <div className="absolute right-0 top-full mt-2 z-50 w-60 bg-white rounded-2xl shadow-2xl border border-slate-100 p-1.5 animate-in fade-in zoom-in-95 duration-150 max-h-[70vh] overflow-y-auto">
                  <p className="px-3 py-1.5 text-[9px] font-bold uppercase tracking-widest text-slate-400">
                    Download as
                  </p>
                  {downloadFormats.map(f => (
                    <div key={f.id}>
                      <button
                        onClick={() => {
                          setDownloadMenuOpen(false);
                          handleDownload(f.id);
                        }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition text-left"
                      >
                        <Download className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span>{f.label}</span>
                      </button>
                      {f.id === 'pptx' && (
                        <div className="px-3 pb-2 -mt-1">
                          <p className="text-[9px] font-bold uppercase tracking-widest text-slate-400 mb-1">
                            Slide theme
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {pptxThemes.map((t) => (
                              <button
                                key={t.id}
                                onClick={() => handleDownload('pptx', t.id)}
                                title={t.hint}
                                className={`px-2 py-1 rounded-lg text-[10px] font-bold border transition ${
                                  pptxTheme === t.id
                                    ? 'bg-brand-600 text-white border-brand-600'
                                    : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100'
                                }`}
                              >
                                {t.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          <button
            onClick={() => setShowLogDrawer(!showLogDrawer)}
            className={`p-2 rounded-xl text-xs font-bold border transition ${
              showLogDrawer ? 'bg-blue-50 text-blue-600 border-blue-200' : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100'
            }`}
            title="Toggle Edit Log Sidebar"
          >
            <History className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main area: centered Word-style document + right logs sidebar */}
      <div className="flex-grow flex min-h-0">
        {/* Word-style document canvas */}
        <div className="flex-grow overflow-y-auto">
          <div className="max-w-6xl mx-auto w-full px-3 sm:px-6 py-4">
            {/* Editor/Content Area */}
            <div className="relative bg-slate-100 rounded-[24px] shadow-inner p-3 sm:p-5 flex flex-col min-h-[500px]">
              <div className="flex justify-between items-center gap-3 mb-3 pb-2 border-b border-slate-200">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    {viewMode === 'full' ? 'Live Document Preview' : 'Interactive Edit Mode'}
                  </span>
                  {doc.file_type === 'pdf' && (
                    <span className="text-[9px] text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md font-bold uppercase flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      <span>Bounding Box Constraints Active</span>
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => { setViewMode('full'); refreshFullPreview(); }}
                    className={`px-3 py-1.5 font-bold rounded-xl text-[11px] flex items-center gap-1.5 transition shrink-0 ${
                      viewMode === 'full'
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                        : 'bg-slate-200 hover:bg-slate-300 text-slate-700'
                    }`}
                  >
                    <ZoomIn className="w-3.5 h-3.5" />
                    <span>Live Document Preview</span>
                  </button>
                  <button
                    onClick={() => setViewMode('edit')}
                    className={`px-3 py-1.5 font-bold rounded-xl text-[11px] flex items-center gap-1.5 transition shrink-0 ${
                      viewMode === 'edit'
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                        : 'bg-slate-200 hover:bg-slate-300 text-slate-700'
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5" />
                    <span>Interactive Edit Mode</span>
                  </button>
                </div>
              </div>

            {viewMode === 'full' ? (
              <div className="flex-grow overflow-y-auto h-[calc(100vh-250px)] min-h-[500px] rounded-xl bg-slate-300/40 p-2 sm:p-3">
                {fullPreviewError ? (
                  <div className="flex flex-col items-center justify-center text-center p-6 min-h-[300px]">
                    <AlertTriangle className="w-8 h-8 text-red-500 mb-2" />
                    <p className="text-sm font-bold text-slate-800 mb-1">Preview unavailable</p>
                    <p className="text-xs text-slate-500 mb-4">{fullPreviewError}</p>
                    <button
                      onClick={refreshFullPreview}
                      className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs flex items-center gap-1.5 transition"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span>Retry</span>
                    </button>
                  </div>
                ) : fullPreviewLoading && !fullPreviewUrl ? (
                  <div className="flex flex-col items-center justify-center gap-2 min-h-[300px] text-slate-500">
                    <PreviewSkeleton />
                    <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      <span>
                        Rendering preview{fullPreviewElapsed > 0 ? ` - ${fullPreviewElapsed}s` : '...'}
                      </span>
                    </div>
                    {fullPreviewElapsed > 8 && (
                      <p className="text-[10px] text-slate-400 max-w-[240px] text-center">
                        First preview of a Word file takes a moment while it is
                        converted. It is cached, so reopening is instant.
                      </p>
                    )}
                  </div>
                ) : fullPreviewUrl ? (
                  <iframe
                    src={fullPreviewUrl}
                    title="Full Document"
                    className="w-full h-full min-h-[500px] bg-white rounded-lg shadow-lg border border-slate-200"
                  />
                ) : (
                  <PreviewSkeleton />
                )}
                {fullPreviewLoading && fullPreviewUrl && (
                  <div className="flex items-center justify-center gap-2 mt-2 text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Refreshing preview{fullPreviewElapsed > 0 ? ` - ${fullPreviewElapsed}s` : '...'}</span>
                  </div>
                )}
              </div>
            ) : loadingContent ? (
              <DocumentSkeleton />
            ) : contentError ? (
              <div className="flex-grow flex flex-col justify-center items-center text-center p-6">
                <AlertTriangle className="w-8 h-8 text-red-500 mb-2" />
                <h4 className="font-bold text-slate-800 text-sm mb-1">Failed to load content</h4>
                <p className="text-xs text-slate-500 mb-4">{contentError}</p>
                <button
                  onClick={fetchContent}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs flex items-center gap-1.5 transition"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Try Again</span>
                </button>
              </div>
            ) : content && doc.file_type === 'docx' ? (
              <div className="flex-grow overflow-hidden max-h-[640px] rounded-xl bg-slate-200/60 p-4 sm:p-6">
                <div className="bg-white shadow-xl shadow-slate-300/60 rounded-sm max-w-[680px] mx-auto h-[560px] p-8 sm:p-12 flex flex-col">
                  {/* Header band: fixed, shrink-0, capped - can never displace the body. */}
                  <PageBand
                    kind="header"
                    values={headerFooter.headers}
                    onEdit={() => { setHfInitialSection('header'); setHfModalOpen(true); }}
                  />

                  {/* Body is the only scrolling region. min-h-0 lets it actually
                      shrink inside the flex column instead of forcing the page
                      taller than its container. */}
                  <div className="flex-1 min-h-0 overflow-y-auto pr-1">
                    {docStream.length === 0 ? (
                      <p className="text-sm text-slate-400 italic">No content found in this DOCX file.</p>
                    ) : (
                      docStream.map((item) => {
                        if (item.kind === 'table') {
                          const { table } = item;
                          return (
                            <div
                              key={`tbl-${table.table_index}`}
                              className="my-3 overflow-x-auto border border-slate-200 rounded-lg bg-white"
                            >
                              <table className="w-full border-collapse text-[11px] text-slate-700">
                                <tbody>
                                  {table.rows.map((row, r) => (
                                    <tr key={r} className={r % 2 ? 'bg-slate-50/60' : ''}>
                                      {row.map((cell, c) => {
                                        const key = cellKey(table.table_index, r, c);
                                        const pending = pendingEdits[key];
                                        const isEditing = editingIndex === key;
                                        const hasUserEdit = pending !== undefined && pending.text !== cell;
                                        const savedEdit = savedEdits[key];
                                        const currentText = pending !== undefined ? pending.text : cell;

                                        return (
                                          <td
                                            key={c}
                                            onDoubleClick={() => { if (!isEditing) setEditingIndex(key); }}
                                            title={isEditing ? undefined : 'Double-click to edit this cell'}
                                            className={`border border-slate-200 px-2 py-1.5 align-top whitespace-pre-wrap leading-relaxed transition-colors ${
                                              isEditing
                                                ? 'bg-blue-50 ring-2 ring-inset ring-blue-400'
                                                : hasUserEdit
                                                  ? 'bg-amber-50/90 cursor-text'
                                                  : 'cursor-text hover:bg-blue-50/60'
                                            }`}
                                          >
                                            {isEditing ? (
                                              <textarea
                                                autoFocus
                                                value={currentText}
                                                onChange={(e) => setPendingEdits(
                                                  (prev) => ({ ...prev, [key]: { ...(prev[key] || {}), kind: 'table_cell', table_index: table.table_index, row: r, col: c, text: e.target.value } }),
                                                  key
                                                )}
                                                onKeyDown={(e) => {
                                                  if (e.key === 'Escape') {
                                                    e.stopPropagation();
                                                    setEditingIndex(null);
                                                  }
                                                }}
                                                className="w-full min-w-[120px] bg-white border border-blue-400 focus:border-blue-600 rounded-lg p-1.5 outline-none text-[11px] text-slate-800 resize-y shadow-sm whitespace-pre-wrap"
                                                style={{ fontFamily: fontName, fontSize: '11pt' }}
                                              />
                                            ) : (
                                              <>
                                                {currentText ? (
                                                  hasUserEdit && savedEdit
                                                    ? highlightDiff(savedEdit.old, currentText)
                                                    : currentText
                                                ) : (
                                                  <span className="text-slate-300 italic">empty</span>
                                                )}
                                                {hasUserEdit && (
                                                  <span className="block mt-1 text-[7px] font-bold text-amber-700 uppercase tracking-widest">
                                                    Edited
                                                  </span>
                                                )}
                                              </>
                                            )}
                                          </td>
                                        );
                                      })}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              <span className="block px-2 py-1 text-[7px] font-bold text-slate-400 uppercase bg-slate-50 border-t border-slate-100 rounded-b-lg">
                                Table {table.table_index + 1} &middot; {table.n_rows} rows &times; {table.n_cols} columns &middot; double-click a cell to edit
                              </span>
                            </div>
                          );
                        }

                        if (item.kind === 'image') {
                          return (
                            <EditableImageBlock
                              key={`img-${item.image.image_index}`}
                              docId={doc.id}
                              index={item.image.image_index}
                              maxHeight={280}
                              caption={
                                `Image ${item.image.image_index + 1}` +
                                (item.image.width_px ? ` · ${item.image.width_px}×${item.image.height_px}px` : '')
                              }
                              version={imagesVersion}
                              replacing={replacingImageIndex === item.image.image_index}
                              onRequestReplace={requestImageReplace}
                              onRequestResize={requestImageResize}
                            />
                          );
                        }

                        const p = item.paragraph;
                        const key = paraKey(p.index);
                        const isEditing = editingIndex === key;
                        const pending = pendingEdits[key];
                        const hasUserEdit = pending !== undefined && pending.text !== p.text;
                        const savedEdit = savedEdits[key];
                        const change = aiChanges.find(c => c.index === p.index);
                        const isHighlighted = hasUserEdit || !!change || !!savedEdit;
                        const currentText = pending !== undefined ? pending.text : p.text;
                        const oldText = savedEdit ? savedEdit.old : (change ? change.old_text : p.text);
                        const blockStyle = {
                          fontFamily: p.font_name || fontName,
                          fontSize: `${p.font_size || fontSize}pt`,
                          fontWeight: p.bold ? 'bold' : 'normal',
                          fontStyle: p.italic ? 'italic' : 'normal',
                          textDecoration: p.underline ? 'underline' : 'none',
                          color: p.color || undefined,
                          minHeight: '1.5rem'
                        };

                        return (
                          <div 
                            key={p.index} 
                            className={`group relative p-3.5 rounded-xl transition duration-200 text-left cursor-pointer ${
                              isHighlighted
                                ? 'bg-amber-50/90 border border-amber-200/90 shadow-2xs my-1'
                                : 'hover:bg-slate-50'
                            }`}
                            onDoubleClick={() => { if (!isEditing) setEditingIndex(key); }}
                          >
                            {isEditing ? (
                              <div className="space-y-2">
                                <textarea
                                  autoFocus
                                  value={currentText}
                                  onChange={(e) => setPendingEdits(
                                    (prev) => ({ ...prev, [key]: { kind: 'paragraph', index: p.index, text: e.target.value } }),
                                    key
                                  )}
                                  className="w-full bg-white border border-blue-400 focus:border-blue-600 rounded-lg p-2 outline-none text-slate-800 resize-y shadow-sm"
                                  style={{ fontFamily: p.font_name || fontName, fontSize: `${p.font_size || fontSize}pt`, fontWeight: p.bold ? 'bold' : 'normal', fontStyle: p.italic ? 'italic' : 'normal', textDecoration: p.underline ? 'underline' : 'none' }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Escape') setEditingIndex(null);
                                  }}
                                />
                                <div className="flex flex-wrap items-center gap-2">
                                  <input
                                    value={rewriteInstruction}
                                    onChange={(e) => setRewriteInstruction(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter') {
                                        e.preventDefault();
                                        handleRewriteBlock({ key: String(p.index), index: p.index, text: currentText });
                                      }
                                    }}
                                    placeholder="AI instruction: e.g. Fix grammar, Make formal..."
                                    className="flex-1 min-w-[180px] px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-[11px] text-slate-700 focus:border-blue-400 outline-none"
                                  />
                                  <button
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => handleRewriteBlock({ key: String(p.index), index: p.index, text: currentText })}
                                    disabled={rewriteBusy || !currentText}
                                    className="px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 disabled:opacity-40 text-white font-bold rounded-lg text-[11px] flex items-center gap-1.5 shadow-sm transition"
                                    title="Rewrite this paragraph with the local AI brain (Gemini fallback)"
                                  >
                                    {rewriteBusy && rewritingIndex === String(p.index) ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                      <Wand2 className="w-3.5 h-3.5" />
                                    )}
                                    <span>{rewriteBusy && rewritingIndex === String(p.index) ? 'Rewriting...' : 'AI Rewrite'}</span>
                                  </button>
                                  <button
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => setEditingIndex(null)}
                                    className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-lg text-[11px] transition"
                                  >
                                    Done
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <p 
                                className="text-slate-800 leading-relaxed break-words font-medium" 
                                style={blockStyle}
                              >
                                {currentText ? (isHighlighted ? highlightDiff(oldText, currentText) : currentText) : (
                                  <span className="text-slate-300 italic font-normal text-sm">Empty paragraph. Click to write...</span>
                                )}
                              </p>
                            )}
                            {isHighlighted && !isEditing && (
                              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                                <span className="inline-flex items-center gap-1 text-[8px] font-bold text-amber-800 uppercase tracking-widest bg-amber-100 border border-amber-300 px-2 py-0.5 rounded-md">
                                  <span>{hasUserEdit ? 'User Edit Highlighted' : savedEdit ? 'Edited Highlighted' : 'AI Edit Highlighted'}</span>
                                  {(change || savedEdit) && (
                                    <>
                                      <span className="line-through text-amber-600/70 ml-1">{change ? change.old_text : savedEdit.old}</span>
                                      <span className="text-amber-500">→</span>
                                      <span className="text-amber-900 font-extrabold">{change ? change.new_text : savedEdit.new}</span>
                                    </>
                                  )}
                                </span>
                              </div>
                            )}
                            {!isHighlighted && !isEditing && (
                              <span className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition text-[8px] font-bold text-blue-500 uppercase tracking-widest bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-md pointer-events-none">
                                Do you want to edit? (Double-click)
                              </span>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* Footer band: same fixed-band treatment as the header. */}
                  <PageBand
                    kind="footer"
                    values={headerFooter.footers}
                    onEdit={() => { setHfInitialSection('footer'); setHfModalOpen(true); }}
                  />
                </div>
              </div>
            ) : content && doc.file_type === 'pdf' ? (
              <div className="space-y-6 max-h-[500px] overflow-y-auto pr-2">
                {content.length === 0 ? (
                  <p className="text-sm text-slate-400 italic">No text blocks detected in this PDF.</p>
                ) : (
                  content.map((page) => (
                    <div key={page.page_num} className="bg-slate-50/50 border border-slate-100 p-5 rounded-3xl space-y-4">
                      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                        <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">Page {page.page_num + 1}</span>
                        <button
                          onClick={() => { setHfInitialSection('header'); setHfModalOpen(true); }}
                          className="text-[10px] font-bold text-blue-600 hover:text-blue-800 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-lg flex items-center gap-1 transition"
                        >
                          <FileSignature className="w-3 h-3" />
                          <span>Edit Page Header/Footer</span>
                        </button>
                      </div>

                      {/* PDF Page Header Action Strip */}
                      <div
                        onClick={() => { setHfInitialSection('header'); setHfModalOpen(true); }}
                        className="group p-2.5 bg-white hover:bg-blue-50/50 border border-dashed border-slate-200 hover:border-blue-300 rounded-xl cursor-pointer text-center transition flex items-center justify-between"
                      >
                        <span
                          className="text-[10px] font-semibold text-slate-500 truncate min-w-0 flex-1 text-left"
                          title={headerFooter.headers[0] || ''}
                        >
                          {headerFooter.headers[0] ? `Header: "${headerFooter.headers[0]}"` : 'Click to add/edit Header overlay'}
                        </span>
                        <span className="text-[8px] font-bold uppercase text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded shrink-0">Header</span>
                      </div>
                      
                      <div className="space-y-2.5">
                        {interleavePageItems(page).length === 0 ? (
                          <p className="text-xs text-slate-400 italic">
                            No text blocks or images on this page.
                          </p>
                        ) : (
                          interleavePageItems(page).map((item) => {
                            if (item.kind === 'image') {
                              return (
                                <EditableImageBlock
                                  key={`img-${item.image.image_index}`}
                                  docId={doc.id}
                                  index={item.image.image_index}
                                  maxHeight={260}
                                  alt={`Page ${page.page_num + 1} image ${item.image.image_index + 1}`}
                                  caption={`Image ${item.image.image_index + 1}`}
                                  version={imagesVersion}
                                  replacing={replacingImageIndex === item.image.image_index}
                                  onRequestReplace={requestImageReplace}
                                  onRequestResize={requestImageResize}
                                />
                              );
                            }
                            const block = item.block;
                            const blockKey = pdfBlockKey(page.page_num, block.block_no);
                            const isEditing = editingIndex === blockKey;
                            const hasUserEdit = pendingEdits[blockKey] !== undefined && pendingEdits[blockKey].text !== block.text;
                            const savedEdit = savedEdits[blockKey];
                            const isHighlighted = hasUserEdit || !!savedEdit;
                            const currentText = pendingEdits[blockKey] !== undefined ? pendingEdits[blockKey].text : block.text;
                            const saveOld = savedEdit ? savedEdit.old : block.text;
                            const pdfFamily = /times|garamond|georgia|serif/i.test(block.font || '') ? 'Times New Roman, serif'
                              : /courier|mono/i.test(block.font || '') ? 'Courier New, monospace'
                              : (block.font || fontName);
                            const pdfColor = Array.isArray(block.color) && block.color.length === 3
                              ? `rgb(${block.color[0]}, ${block.color[1]}, ${block.color[2]})` : undefined;
                            const pdfStyle = {
                              fontFamily: pdfFamily,
                              fontSize: `${Math.max(6, block.size || (fontSize - 2))}pt`,
                              color: pdfColor,
                              minHeight: '1.25rem'
                            };
                            return (
                              <div 
                                key={block.block_no}
                                onDoubleClick={() => { if (!isEditing) setEditingIndex(blockKey); }}
                                className={`group relative p-3 border rounded-xl transition cursor-pointer text-left ${
                                  isHighlighted
                                    ? 'bg-amber-50/90 border-amber-300 shadow-xs'
                                    : 'bg-white hover:bg-slate-50/50 border-slate-100 hover:border-amber-200'
                                }`}
                              >
                                {isEditing ? (
                                  <div className="space-y-2">
                                    <textarea
                                      autoFocus
                                      value={currentText}
                                      onChange={(e) => {
                                        setPendingEdits(
                                          (prev) => ({
                                            ...prev,
                                            [blockKey]: {
                                              kind: 'pdf_block',
                                              page_num: page.page_num,
                                              block_no: block.block_no,
                                              bbox: block.bbox,
                                              text: e.target.value
                                            }
                                          }),
                                          blockKey
                                        );
                                      }}
                                      className="w-full bg-white border border-amber-400 focus:border-amber-600 rounded-lg p-1.5 outline-none text-xs text-slate-800 resize-y shadow-sm"
                                      style={{ fontFamily: pdfFamily, fontSize: `${Math.max(6, block.size || (fontSize - 2))}pt` }}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Escape') setEditingIndex(null);
                                      }}
                                    />
                                    <div className="flex flex-wrap items-center gap-2">
                                      <input
                                        value={rewriteInstruction}
                                        onChange={(e) => setRewriteInstruction(e.target.value)}
                                        onKeyDown={(e) => {
                                          if (e.key === 'Enter') {
                                            e.preventDefault();
                                            handleRewriteBlock({ key: blockKey, page_num: page.page_num, block_no: block.block_no, bbox: block.bbox, text: currentText });
                                          }
                                        }}
                                        placeholder="AI instruction: e.g. Simplify this..."
                                        className="flex-1 min-w-[160px] px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-[11px] text-slate-700 focus:border-blue-400 outline-none"
                                      />
                                      <button
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={() => handleRewriteBlock({ key: blockKey, page_num: page.page_num, block_no: block.block_no, bbox: block.bbox, text: currentText })}
                                        disabled={rewriteBusy || !currentText}
                                        className="px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 disabled:opacity-40 text-white font-bold rounded-lg text-[11px] flex items-center gap-1.5 shadow-sm transition"
                                        title="Rewrite this block with the local AI brain (Gemini fallback)"
                                      >
                                        {rewriteBusy && rewritingIndex === blockKey ? (
                                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                        ) : (
                                          <Wand2 className="w-3.5 h-3.5" />
                                        )}
                                        <span>{rewriteBusy && rewritingIndex === blockKey ? 'Rewriting...' : 'AI Rewrite'}</span>
                                      </button>
                                      <button
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={() => setEditingIndex(null)}
                                        className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-lg text-[11px] transition"
                                      >
                                        Done
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <p 
                                    className="text-xs leading-relaxed font-medium"
                                    style={pdfStyle}
                                  >
                                    {currentText ? (isHighlighted ? highlightDiff(saveOld, currentText) : currentText) : (
                                      <span className="text-slate-300 italic">Empty text block. Click to write...</span>
                                    )}
                                  </p>
                                )}
                                {isHighlighted && !isEditing && (
                                  <span className="mt-1.5 inline-block text-[7px] font-bold text-amber-800 uppercase bg-amber-100 border border-amber-200 px-1.5 py-0.5 rounded">
                                    {hasUserEdit ? 'User Edit Highlighted' : 'Edited Highlighted'}
                                  </span>
                                )}
                                {!isHighlighted && !isEditing && (
                                  <span className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition text-[7px] font-bold text-amber-600 uppercase bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded pointer-events-none">
                                    Do you want to edit? (Double-click)
                                  </span>
                                )}
                              </div>
                            );
                          })
                        )}
                      </div>

                      {/* PDF Page Footer Action Strip */}
                      <div
                        onClick={() => { setHfInitialSection('footer'); setHfModalOpen(true); }}
                        className="group p-2.5 bg-white hover:bg-indigo-50/50 border border-dashed border-slate-200 hover:border-indigo-300 rounded-xl cursor-pointer text-center transition flex items-center justify-between"
                      >
                        <span
                          className="text-[10px] font-semibold text-slate-500 truncate min-w-0 flex-1 text-left"
                          title={headerFooter.footers[0] || ''}
                        >
                          {headerFooter.footers[0] ? `Footer: "${headerFooter.footers[0]}"` : 'Click to add/edit Footer overlay'}
                        </span>
                        <span className="text-[8px] font-bold uppercase text-indigo-600 bg-indigo-100 px-1.5 py-0.5 rounded shrink-0">Footer</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            ) : null}

            {/* Gemini-style AI processing overlay (transparent background) */}
            {aiProcessing && (
              <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 p-6 pointer-events-none">
                <div className="relative flex items-center justify-center">
                  <img
                    src={laodingEffect}
                    alt="RapidDoc AI loading"
                    className="w-14 h-14 sm:w-16 sm:h-16 object-contain animate-ai-zoom"
                  />
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-slate-700 flex items-center justify-center gap-1.5">
                    {AI_STATUSES[aiStatusIndex]}
                    <span className="inline-flex gap-0.5 items-center">
                      <span className="w-1 h-1 rounded-full bg-slate-500 animate-bounce" />
                      <span className="w-1 h-1 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-1 h-1 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </span>
                  </p>
                  <p className="mt-1.5 text-[10px] uppercase tracking-widest text-slate-400 font-bold flex items-center justify-center gap-1">
                    <Wand2 className="w-3 h-3" />
                    RapidDoc AI
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Right sidebar: live edit logs */}
      {showLogDrawer && (
        <div className="shrink-0 w-72 border-l border-slate-200 bg-white flex flex-col min-h-0 animate-in slide-in-from-right duration-200">
          <div className="shrink-0 px-4 py-3 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="w-3.5 h-3.5 text-blue-600" />
              <h3 className="font-bold text-slate-800 text-xs uppercase tracking-wider">Edit Log</h3>
            </div>
            <button
              onClick={() => setShowLogDrawer(false)}
              className="p-1 hover:bg-slate-100 rounded-lg text-slate-400"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex-grow overflow-y-auto p-3 space-y-2">
            {/* Rollback timeline: the entries that actually hold the file. */}
            <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3 space-y-2">
              <p className="text-[10px] font-bold text-blue-700 uppercase tracking-wider flex items-center gap-1">
                <History className="w-3 h-3" />
                Versions
              </p>
              {versionError && (
                <p className="text-[10px] font-semibold text-red-600">{versionError}</p>
              )}
              {versions.map((version, idx) => {
                const target = version.is_original ? 'original' : version.version_id;
                const busy = restoringVersion === target;
                return (
                  <div
                    key={`${target || 'current'}-${idx}`}
                    className={`flex items-center justify-between gap-2 bg-white border rounded-lg px-2 py-1.5 ${
                      version.is_current ? 'border-blue-300' : 'border-blue-100'
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="text-[11px] font-bold text-slate-700 truncate">
                        {version.label}
                        {version.is_current && (
                          <span className="ml-1 text-[9px] uppercase text-blue-600 bg-blue-50 px-1 py-0.5 rounded">
                            Live
                          </span>
                        )}
                      </p>
                      <p className="text-[9px] text-slate-400">
                        {version.created_at
                          ? new Date(version.created_at).toLocaleString()
                          : version.is_current
                            ? 'Unsaved edits'
                            : 'Kept automatically'}
                      </p>
                    </div>
                    {version.restorable && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleRestoreVersion(version)}
                        className="shrink-0 px-2 py-1 rounded-md bg-white border border-blue-200 text-blue-700 text-[9px] font-bold uppercase tracking-wide hover:bg-blue-600 hover:text-white transition disabled:opacity-50 flex items-center gap-1"
                      >
                        {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Undo2 className="w-3 h-3" />}
                        Restore
                      </button>
                    )}
                  </div>
                );
              })}
              {versions.length === 0 && (
                <p className="text-[11px] text-slate-400 italic">Loading versions…</p>
              )}
            </div>

            {aiChanges.length > 0 && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3 space-y-2">
                <p className="text-[10px] font-bold text-emerald-700 uppercase tracking-wider flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" />
                  Latest Changes
                </p>
                {aiChanges.map((c, idx) => (
                  <div key={idx} className="text-[11px] bg-white border border-emerald-100 rounded-lg px-2 py-1.5">
                    <p className="font-bold text-slate-500 text-[10px] uppercase tracking-wide mb-1">{c.paragraph}</p>
                    <p className="flex items-start gap-1.5 text-slate-600">
                      <span className="line-through text-slate-400">{c.old_text}</span>
                      <ArrowRight className="w-3 h-3 text-emerald-500 mt-0.5 shrink-0" />
                      <span className="bg-yellow-100 px-1 rounded font-semibold">{c.new_text}</span>
                    </p>
                  </div>
                ))}
              </div>
            )}
            {doc.edit_history && doc.edit_history.length > 0 ? (
              doc.edit_history.slice().reverse().map((entry, idx) => (
                <div key={idx} className="rounded-xl border border-slate-100 bg-slate-50/60 p-2.5">
                  <p className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">{entry.date}</p>
                  <p className="text-[11px] text-slate-700 mt-0.5">{entry.action}</p>
                </div>
              ))
            ) : (
              <p className="text-[11px] text-slate-400 italic p-2">No activity yet.</p>
            )}
          </div>
        </div>
      )}
    </div>

    {/* Bottom ChatGPT-style AI Chat Bar */}
      <div className="shrink-0 bg-white border-t border-slate-200 px-4 sm:px-6 py-3">
        <form onSubmit={handleAiSubmit} onPaste={handleCommandPaste} className="max-w-4xl mx-auto">
          {aiResult && (
            <div className={`mb-2 flex items-start gap-2 text-xs font-semibold ${
              aiResult.startsWith('Error') ? 'text-red-600' : 'text-emerald-700'
            }`}>
              {aiResult.startsWith('Error') ? (
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              )}
              <span>{aiResult}</span>
            </div>
          )}

          {/* Document Images Module */}
          {showImageModule && (
            <div className="mb-3 rounded-2xl border border-blue-200 bg-gradient-to-b from-blue-50/90 to-indigo-50/60 backdrop-blur-sm p-3.5 shadow-sm transition-all animate-in fade-in slide-in-from-bottom-2 duration-200">
              <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-blue-100">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-blue-600 text-white shadow-xs">
                    <ImageIcon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-800">Document Images Module</span>
                      <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-blue-100 text-blue-700 border border-blue-200">
                        {inventoryLoading ? 'Scanning…' : `${imageInventory.length} detected`}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500">
                      {promptImage
                        ? 'Image ready! Click "Replace" on any card below or type "replace the image 1 by this".'
                        : 'Inspect images (Image 1, 2, 3...) • Paste or attach an image in the command bar to replace.'}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => fetchImageInventory()}
                    disabled={inventoryLoading}
                    className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-100/60 rounded-lg transition"
                    title="Refresh detected images"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${inventoryLoading ? 'animate-spin text-blue-600' : ''}`} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowImageModule(false)}
                    className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition"
                    title="Close images module"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {inventoryLoading && imageInventory.length === 0 ? (
                <div className="flex items-center justify-center py-6 gap-2 text-xs font-medium text-slate-500">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                  <span>Scanning document for images…</span>
                </div>
              ) : imageInventory.length === 0 ? (
                <div className="py-6 text-center">
                  <ImageIcon className="w-8 h-8 text-slate-300 mx-auto mb-1.5" />
                  <p className="text-xs font-semibold text-slate-600">No images detected in this document</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">This document does not contain any embedded pictures.</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5 max-h-64 overflow-y-auto pr-1">
                  {imageInventory.map((img, i) => {
                    const imageNumber = i + 1;
                    const isReplacingThis = replacingImageIndex === img.index;
                    return (
                      <div
                        key={img.index}
                        className={`group/card relative rounded-xl border bg-white p-2.5 shadow-2xs transition-all hover:shadow-md ${
                          promptImage
                            ? 'border-blue-300 hover:border-blue-500 ring-2 ring-blue-100'
                            : 'border-slate-200 hover:border-slate-300'
                        }`}
                      >
                        {/* Numbering Header: Image 1, Image 2, etc. */}
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-600 text-white text-[11px] font-black tracking-wide shadow-2xs">
                            Image {imageNumber}
                          </span>
                          {img.page_num != null && (
                            <span className="text-[9px] font-semibold text-slate-400 bg-slate-50 border border-slate-100 px-1.5 py-0.5 rounded">
                              Page {img.page_num + 1}
                            </span>
                          )}
                        </div>

                        {/* Image Preview */}
                        <div className="h-24 w-full bg-slate-50 rounded-lg border border-slate-100 flex items-center justify-center overflow-hidden mb-2 relative">
                          {isReplacingThis ? (
                            <div className="flex flex-col items-center gap-1 text-[10px] text-blue-600 font-bold">
                              <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                              <span>Replacing…</span>
                            </div>
                          ) : (
                            <DocumentImage
                              docId={doc.id}
                              index={img.index}
                              maxHeight={86}
                              version={imagesVersion}
                              className="max-h-full max-w-full object-contain"
                            />
                          )}
                        </div>

                        {/* Image details */}
                        <p className="text-[10px] font-medium text-slate-600 truncate mb-2" title={img.label}>
                          {img.label || `Image ${imageNumber}`}
                        </p>

                        {/* Actions */}
                        {promptImage ? (
                          <button
                            type="button"
                            disabled={replacingImageIndex !== null}
                            onClick={() => uploadPromptReplacement(img.index, promptImage.file, `replace image ${imageNumber} by this`)}
                            className="w-full py-1.5 px-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white text-[10px] font-bold rounded-lg shadow-xs flex items-center justify-center gap-1 transition"
                          >
                            <Sparkles className="w-3 h-3" />
                            <span>Replace #{imageNumber}</span>
                          </button>
                        ) : (
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => {
                                pendingImageIndexRef.current = img.index;
                                imagePickInputRef.current?.click();
                              }}
                              className="flex-1 py-1 px-1.5 bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-slate-700 text-[10px] font-semibold rounded-md border border-slate-200 transition text-center truncate"
                            >
                              Upload
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setAiPrompt(`replace the image ${imageNumber} by this`);
                              }}
                              title={`Insert "replace the image ${imageNumber} by this" into command bar`}
                              className="py-1 px-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-[10px] font-bold rounded-md border border-blue-200 transition"
                            >
                              Select
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {aiInteractiveMode === 'select_image' && aiVariantGroups.length > 0 && (
            <div className="mb-2 flex flex-col gap-2 max-h-48 overflow-y-auto rounded-2xl border border-blue-200 bg-blue-50/60 p-3">
              <span className="text-xs font-bold text-slate-600 flex items-center gap-1.5">
                <ImageIcon className="w-3.5 h-3.5 text-blue-600" />
                Which image should I replace?
              </span>
              {aiVariantGroups.map((candidate) => (
                <button
                  key={candidate.index}
                  type="button"
                  disabled={replacingImageIndex !== null}
                  onClick={() => promptImage && uploadPromptReplacement(
                    candidate.index, promptImage.file, aiFindText
                  )}
                  className="flex items-center gap-3 px-3 py-2 bg-white border border-slate-200 hover:border-blue-400 disabled:opacity-50 rounded-lg text-left transition shadow-sm"
                >
                  <DocumentImage
                    docId={doc.id}
                    index={candidate.index}
                    maxHeight={48}
                    version={imagesVersion}
                    className="shrink-0"
                  />
                  <span className="min-w-0">
                    <span className="block text-xs font-bold text-slate-800">
                      {candidate.label}
                    </span>
                    {candidate.occurrences > 1 && (
                      <span className="block text-[10px] text-amber-600 font-semibold">
                        Replacing this also changes {candidate.occurrences - 1} other spot
                        {candidate.occurrences - 1 !== 1 ? 's' : ''}.
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          )}

          {aiInteractiveMode === 'select_variants' && aiVariantGroups.length > 0 && (
            <div className="mb-2 flex flex-col gap-2 max-h-48 overflow-y-auto rounded-2xl border border-blue-200 bg-blue-50/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-600">
                  Replacing "{aiFindText}" with "{aiReplaceText}"
                </span>
                <button
                  type="button"
                  onClick={() => setAiSelectedVariants(aiVariantGroups.map(g => g.variant))}
                  className="text-[10px] font-bold text-blue-600 hover:text-blue-800"
                >
                  Select all
                </button>
              </div>
              {aiVariantGroups.map((g, idx) => (
                <label
                  key={idx}
                  className="flex items-start gap-2 px-3 py-2 bg-white border border-slate-200 hover:border-blue-300 rounded-lg text-xs text-slate-700 transition shadow-sm cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={aiSelectedVariants.includes(g.variant)}
                    onChange={(e) => {
                      setAiSelectedVariants(prev =>
                        e.target.checked
                          ? [...prev, g.variant]
                          : prev.filter(v => v !== g.variant)
                      );
                    }}
                    className="mt-0.5 w-4 h-4 text-blue-600 border-slate-200 rounded focus:ring-blue-500 shrink-0"
                  />
                  <span className="flex flex-col min-w-0">
                    <span className="font-bold text-slate-800">
                      "{g.variant}" <span className="text-slate-400 font-semibold">({g.count} occurrence{g.count !== 1 ? 's' : ''})</span>
                    </span>
                    <span className="text-[10px] text-slate-400 truncate">
                      e.g. {g.locations[0]?.context}
                    </span>
                  </span>
                </label>
              ))}
              <button
                type="button"
                disabled={aiProcessing}
                onClick={handleApplySelectedVariants}
                className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold rounded-xl text-xs flex items-center justify-center gap-1.5 shadow-lg shadow-blue-500/20 transition"
              >
                <Wand2 className="w-3.5 h-3.5" />
                <span>Replace Selected ({aiSelectedVariants.length})</span>
              </button>
            </div>
          )}

          {aiChanges.length > 0 && (
            <div className="mb-2 flex flex-col gap-2 max-h-40 overflow-y-auto rounded-2xl border border-emerald-200 bg-emerald-50/60 p-3 transition-all duration-300 animate-in fade-in slide-in-from-bottom-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-600 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  Changes applied (highlighted in the document above)
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setAiChanges([]);
                    setAiResult((prev) => (prev && !prev.startsWith('Error') ? '' : prev));
                  }}
                  className="text-slate-400 hover:text-slate-600 p-0.5 rounded-md hover:bg-emerald-100/60 transition cursor-pointer"
                  title="Dismiss"
                  aria-label="Dismiss changes notification"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              {aiChanges.map((c, idx) => (
                <div key={idx} className="text-[11px] text-slate-600 bg-white border border-emerald-100 rounded-lg px-2.5 py-1.5 flex items-start gap-2">
                  <span className="font-bold text-emerald-700 shrink-0">{c.paragraph}:</span>
                  <span className="min-w-0">
                    <span className="line-through text-slate-400">{c.old_text}</span>
                    <span className="mx-1.5 text-emerald-500 font-bold">→</span>
                    <span className="bg-yellow-100 px-1 rounded font-semibold">{c.new_text}</span>
                  </span>
                </div>
              ))}
            </div>
          )}

          {aiSummary && (
            <div className="mb-2 rounded-2xl border border-indigo-200 bg-indigo-50/60 p-3">
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs font-bold text-slate-600 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                  Summary
                  <span className="font-semibold text-slate-400">
                    ({aiSummary.source}{aiSummary.length ? `, ${aiSummary.length}` : ''})
                  </span>
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(aiSummary.summary || '')}
                    className="text-[10px] font-bold text-indigo-500 hover:text-indigo-700 flex items-center gap-1"
                  >
                    <Copy className="w-3 h-3" />
                    Copy
                  </button>
                  {/* Keep the summary: exporting the text on screen rather than
                      asking the server to summarise again, because a second pass
                      would hand back different wording. */}
                  {SUMMARY_FORMATS.map((fmt) => (
                    <button
                      key={fmt.value}
                      type="button"
                      disabled={summaryExporting === fmt.value}
                      onClick={() => handleExportSummary(fmt.value)}
                      title={`Download as ${fmt.label}`}
                      className="text-[10px] font-bold text-indigo-500 hover:text-indigo-700 flex items-center gap-1 disabled:opacity-50"
                    >
                      {summaryExporting === fmt.value
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : <Download className="w-3 h-3" />}
                      {fmt.label}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      setAiSummary(null);
                      setSummaryExportError('');
                    }}
                    title="Close summary"
                    aria-label="Close summary"
                    className="rounded-lg border border-indigo-200/80 bg-white/80 p-1 text-slate-400 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-600 transition ml-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              </div>
              {summaryExportError && (
                <p className="mt-1.5 text-[10px] font-semibold text-red-600">
                  {summaryExportError}
                </p>
              )}
              {aiSummary.summary_source === 'conclusion' && !aiSummary.summary?.includes('## Conclusion') && (
                <div className="mt-1.5 mb-2 rounded-xl bg-white/70 border border-indigo-100 px-2.5 py-2">
                  <div className="text-[10px] font-bold uppercase tracking-wide text-indigo-500 mb-1">
                    From the conclusion
                  </div>
                  <ul className="space-y-1">
                    {(aiSummary.key_points || []).map((point, i) => (
                      <li
                        key={i}
                        className="text-[11px] leading-relaxed text-slate-700 flex gap-1.5"
                      >
                        <span className="text-indigo-400 font-bold shrink-0">•</span>
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="mt-2 text-slate-700 bg-white/90 rounded-2xl p-3.5 border border-indigo-100/90 shadow-2xs max-h-96 overflow-y-auto">
                <MarkdownRenderer content={aiSummary.summary} />
              </div>
            </div>
          )}

          {aiQuestions && (aiQuestions.questions || []).length > 0 && (() => {
            const questions = aiQuestions.questions;
            const pickFor = (qi) => quizPicks[qi];
            const answeredCount = questions.filter(
              (q, qi) => pickFor(qi) != null
            ).length;
            const correctCount = questions.filter((q, qi) => {
              const pick = pickFor(qi);
              return pick != null && pick === String(q.answer || '').toUpperCase();
            }).length;
            const allAnswered = answeredCount === questions.length;
            const typeLabel = {
              recall: 'Fill in the blank',
              definition: 'Definition',
              association: 'Related term',
              purpose: 'Purpose',
              cause: 'Cause / effect',
              numeric: 'Numbers',
              statement: 'True statement',
              model: 'Model generated',
            };
            return (
              <div className="mb-2 flex flex-col gap-2 max-h-72 overflow-y-auto rounded-2xl border border-amber-200 bg-amber-50/60 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-slate-600 flex items-center gap-1.5">
                    <ListOrdered className="w-3.5 h-3.5 text-amber-600" />
                    {questions.length} question(s)
                    {aiQuestions.requested > questions.length
                      ? ` requested ${aiQuestions.requested} - the document did not contain enough distinct content for the rest`
                      : ''}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {answeredCount > 0 && (
                      <span className="text-[10px] font-bold text-slate-600 tabular-nums">
                        {correctCount}/{answeredCount} correct
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        if (quizMode) {
                          setQuizMode(false);
                          setQuizPicks({});
                        } else {
                          setQuizMode(true);
                        }
                      }}
                      className="rounded-lg border border-amber-300 bg-white px-2 py-1 text-[10px] font-bold text-amber-700 hover:bg-amber-100"
                    >
                      {quizMode ? 'Show answers' : 'Take quiz'}
                    </button>
                    {quizMode && answeredCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setQuizPicks({})}
                        className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[10px] font-bold text-slate-600 hover:bg-slate-100"
                      >
                        Reset
                      </button>
                    )}
                    {/* Dismiss the generated set without clearing the rest of the
                        AI panel - there was previously no way to get rid of it. */}
                    <button
                      type="button"
                      onClick={() => {
                        setAiQuestions(null);
                        setQuizMode(false);
                        setQuizPicks({});
                      }}
                      title="Dismiss these questions"
                      aria-label="Dismiss generated questions"
                      className="rounded-lg border border-slate-300 bg-white p-1 text-slate-500 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-600 transition"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                {questions.map((q, qi) => {
                  const pick = pickFor(qi);
                  const correctLetter = String(q.answer || '').toUpperCase();
                  const reveal = !quizMode || pick != null;
                  return (
                    <div key={qi} className="rounded-xl border border-amber-100 bg-white px-2.5 py-2">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-[11px] font-bold text-slate-700">
                          {qi + 1}. {q.question}
                        </p>
                        {q.type && (
                          <span className="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-500">
                            {typeLabel[q.type] || q.type}
                          </span>
                        )}
                      </div>
                      <ol className="mt-1 flex flex-col gap-0.5">
                        {(q.options || []).map((opt, oi) => {
                          const letter = String.fromCharCode(65 + oi);
                          const isAnswer = correctLetter === letter;
                          const isPick = pick === letter;
                          const blank = !opt || String(opt).trim() === '';
                          // In quiz mode the correct answer is hidden until the
                          // question has been answered, so the user cannot
                          // pattern-match the highlighted row.
                          const markCorrect = reveal && isAnswer;
                          const markWrong = quizMode && isPick && !isAnswer;
                          const style = markCorrect
                            ? 'bg-emerald-50 font-bold text-emerald-700'
                            : markWrong
                            ? 'bg-rose-50 font-bold text-rose-600'
                            : isPick
                            ? 'bg-blue-50 font-semibold text-blue-700'
                            : 'text-slate-600';
                          const row = (
                            <>
                              <span className="font-bold shrink-0">{letter})</span>
                              <span className="min-w-0">{blank ? 'not produced' : opt}</span>
                            </>
                          );
                          return (
                            <li
                              key={oi}
                              className={`text-[11px] flex items-start gap-1.5 rounded px-1 py-0.5 ${style} ${
                                blank ? 'italic text-slate-300' : ''
                              }`}
                            >
                              {quizMode && !blank ? (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setQuizPicks((prev) => ({ ...prev, [qi]: letter }))
                                  }
                                  className="flex items-start gap-1.5 text-left w-full min-w-0"
                                >
                                  {row}
                                </button>
                              ) : (
                                row
                              )}
                            </li>
                          );
                        })}
                      </ol>
                      {reveal && (
                        <p className="mt-1 text-[10px] text-slate-400">
                          {quizMode && pick != null
                            ? pick === correctLetter
                              ? `Correct: ${correctLetter}`
                              : `Incorrect - the answer is ${correctLetter}`
                            : `Answer: ${correctLetter || 'not identified'}`}
                          {q.complete === false
                            ? ' - the model output was truncated for this one'
                            : ''}
                        </p>
                      )}
                    </div>
                  );
                })}

                {quizMode && allAnswered && (
                  <div className="rounded-xl border border-amber-200 bg-white px-2.5 py-2 text-[11px] font-bold text-slate-700">
                    {correctCount === questions.length
                      ? `Perfect score: ${correctCount}/${questions.length}.`
                      : `You scored ${correctCount} out of ${questions.length}.`}
                  </div>
                )}
              </div>
            );
          })()}

          {promptImage && (
            <div className="mb-2 flex items-center gap-3 rounded-2xl border border-blue-200 bg-blue-50/70 px-3 py-2 shadow-2xs">
              <img
                src={promptImage.previewUrl}
                alt="Replacement to upload"
                className="h-12 w-auto object-contain rounded-lg bg-white border border-slate-200 shadow-2xs"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-xs font-bold text-slate-700">
                  <span className="px-1.5 py-0.5 rounded bg-blue-600 text-white text-[9px] font-black tracking-wide">
                    {promptImage.isPasted ? 'PASTED' : 'ATTACHED'}
                  </span>
                  <span className="truncate">{promptImage.file.name}</span>
                </span>
                <span className="block text-[10px] text-slate-500 mt-0.5">
                  Ready to replace! Type &ldquo;replace the image 1 by this&rdquo; or click &ldquo;Replace&rdquo; on any image above.
                </span>
              </span>
              <button
                type="button"
                onClick={clearPromptImage}
                disabled={aiProcessing || replacingImageIndex !== null}
                className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition disabled:opacity-40"
                title="Remove attachment"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Slash Commands Dropdown */}
          {slashMenuOpen && (
            <div className="mb-2 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg flex flex-col gap-0.5 animate-in fade-in slide-in-from-bottom-2 duration-150">
              <span className="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Slash Commands</span>
              <button
                type="button"
                onClick={() => {
                  setAiPrompt('');
                  setSlashMenuOpen(false);
                  setShowImageModule(true);
                  fetchImageInventory();
                }}
                className="flex items-center gap-2 px-2.5 py-1.5 text-left rounded-lg hover:bg-blue-50 hover:text-blue-700 text-xs text-slate-700 font-medium transition"
              >
                <div className="p-1 rounded bg-blue-100 text-blue-600 font-bold text-[10px]">/image</div>
                <div>
                  <span className="font-bold">Image Module</span>
                  <span className="text-[10px] text-slate-400 ml-1.5">Detect, view & replace document images</span>
                </div>
              </button>
              <button
                type="button"
                onClick={() => {
                  setAiPrompt('Summarize this document');
                  setSlashMenuOpen(false);
                }}
                className="flex items-center gap-2 px-2.5 py-1.5 text-left rounded-lg hover:bg-indigo-50 hover:text-indigo-700 text-xs text-slate-700 font-medium transition"
              >
                <div className="p-1 rounded bg-indigo-100 text-indigo-600 font-bold text-[10px]">/summarize</div>
                <div>
                  <span className="font-bold">Summarize Document</span>
                  <span className="text-[10px] text-slate-400 ml-1.5">Create concise summary</span>
                </div>
              </button>
              <button
                type="button"
                onClick={() => {
                  setAiPrompt('Generate 5 MCQs');
                  setSlashMenuOpen(false);
                }}
                className="flex items-center gap-2 px-2.5 py-1.5 text-left rounded-lg hover:bg-amber-50 hover:text-amber-700 text-xs text-slate-700 font-medium transition"
              >
                <div className="p-1 rounded bg-amber-100 text-amber-600 font-bold text-[10px]">/quiz</div>
                <div>
                  <span className="font-bold">Quiz Generator</span>
                  <span className="text-[10px] text-slate-400 ml-1.5">5 interactive MCQs</span>
                </div>
              </button>
            </div>
          )}

          {/* Quick command chips */}
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 overflow-x-auto py-0.5">
              <button
                type="button"
                onClick={() => {
                  setShowImageModule((prev) => {
                    const next = !prev;
                    if (next) fetchImageInventory();
                    return next;
                  });
                }}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold transition border ${
                  showImageModule
                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300 hover:text-blue-600'
                }`}
              >
                <ImageIcon className="w-3.5 h-3.5" />
                <span>/image</span>
                {imageInventory.length > 0 && (
                  <span className={`px-1.5 py-0.2 rounded-full text-[9px] font-black ${
                    showImageModule ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-700'
                  }`}>
                    {imageInventory.length}
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={() => setAiPrompt('Summarize this document')}
                className="px-2.5 py-1 rounded-lg text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:border-indigo-300 hover:text-indigo-600 transition"
              >
                /summarize
              </button>
              <button
                type="button"
                onClick={() => setAiPrompt('Generate 5 MCQs')}
                className="px-2.5 py-1 rounded-lg text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:border-amber-300 hover:text-amber-600 transition"
              >
                /quiz
              </button>
            </div>
            <div className="flex items-center gap-2">
              {activeSelection && (
                <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-xs animate-in fade-in">
                  <span className="font-bold">Selection:</span>
                  <span className="truncate max-w-[220px] italic">"{activeSelection.text}"</span>
                  <button
                    type="button"
                    onClick={() => setActiveSelection(null)}
                    className="p-0.5 hover:bg-indigo-200/50 rounded-full text-indigo-500 transition"
                    title="Clear active selection"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              )}
              {promptImage && (
                <span className="text-[10px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
                  📋 Pasted Picture Ready
                </span>
              )}
            </div>
          </div>

          <div className="relative rounded-2xl border border-slate-200 bg-slate-50 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition shadow-sm">
            <input
              type="text"
              value={aiPrompt}
              onChange={(e) => {
                const val = e.target.value;
                setAiPrompt(val);
                if (val === '/') {
                  setSlashMenuOpen(true);
                } else if (slashMenuOpen && !val.startsWith('/')) {
                  setSlashMenuOpen(false);
                }
                if (val.trim().toLowerCase() === '/image' || val.trim().toLowerCase() === '/images') {
                  setShowImageModule(true);
                  fetchImageInventory();
                  setSlashMenuOpen(false);
                }
              }}
              onPaste={handleCommandPaste}
              placeholder={
                promptImage
                  ? 'Type e.g. "Replace the logo with this", "Use this as header image", or "Replace image 1"'
                  : activeSelection
                    ? `Command for selection: e.g. "Make this more professional", "Make this shorter", "Change heading to blue"`
                    : 'Universal Command Bar: "Change headings to blue", "Delete column 2", "Summarize in 5 points", "Replace X with Y"...'
              }
              disabled={aiProcessing}
              className="w-full bg-transparent py-3 pl-4 pr-24 outline-none text-sm text-slate-700 disabled:opacity-50 placeholder:text-slate-400"
            />
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
              <button
                type="button"
                onClick={() => promptImageInputRef.current?.click()}
                disabled={aiProcessing}
                title="Attach a picture to replace an image in the document"
                className={`p-2 rounded-xl transition disabled:opacity-40 ${
                  promptImage
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-slate-400 hover:text-blue-600 hover:bg-blue-50'
                }`}
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <button
                type="submit"
                disabled={aiProcessing || (!aiPrompt.trim() && !promptImage)}
                className="p-2.5 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-700 hover:to-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl flex items-center gap-1.5 shadow-md shadow-blue-500/20 transition"
              >
                {aiProcessing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Floating Save Edits Bar */}
      {pendingEditCount > 0 && viewMode === 'edit' && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-5 py-3.5 rounded-2xl shadow-2xl flex flex-col gap-2.5 z-50 border border-slate-800 animate-in fade-in slide-in-from-bottom-4 duration-300">
          {saveError && (
            <div className="flex items-start gap-2 text-[11px] font-semibold text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-2.5 py-1.5">
              <AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" />
              <span className="min-w-0 break-words">{saveError} Your changes are still unsaved.</span>
            </div>
          )}
          <div className="flex items-center gap-4">
            <div className="text-left">
              <p className="text-xs font-bold">{pendingEditCount} unsaved change{pendingEditCount === 1 ? '' : 's'}</p>
              <p className="text-[9px] text-slate-400">
                {undoDepth > 0 || redoDepth > 0
                  ? `Ctrl+Z to undo (${undoDepth} step${undoDepth === 1 ? '' : 's'} back)`
                  : 'Save changes to write back to the document file.'}
              </p>
            </div>
            <div className="flex gap-2">
              <div className="flex items-center rounded-xl bg-slate-800 overflow-hidden">
                <button
                  type="button"
                  onClick={undo}
                  disabled={!canUndo || savingEdits}
                  title="Undo (Ctrl+Z)"
                  aria-label="Undo last change"
                  className="px-2.5 py-2 text-slate-300 hover:text-white hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition"
                >
                  <Undo2 className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={redo}
                  disabled={!canRedo || savingEdits}
                  title="Redo (Ctrl+Shift+Z)"
                  aria-label="Redo last change"
                  className="px-2.5 py-2 text-slate-300 hover:text-white hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed border-l border-slate-700 transition"
                >
                  <Redo2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <button
                onClick={() => { replaceAllEdits({}); setEditingIndex(null); setSaveError(''); }}
                disabled={savingEdits}
                title="Discard all unsaved changes (this can be undone)"
                className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-semibold rounded-xl text-xs transition"
              >
                Discard
              </button>
              <button
                onClick={handleSaveEdits}
                disabled={savingEdits}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold rounded-xl text-xs flex items-center gap-2 shadow-lg shadow-blue-500/20 transition"
              >
                {savingEdits ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Save className="w-3.5 h-3.5" />
                    <span>Save Changes</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PDF Preview Modal */}
      {previewOpen && (
        <div className="fixed inset-0 z-[60] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-8">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 shrink-0">
              <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2 min-w-0">
                <FileText className="w-4 h-4 text-blue-600 shrink-0" />
                <span>PDF Preview</span>
                <span className="text-[10px] text-slate-400 font-semibold truncate">{doc.name}</span>
              </h3>
              <button
                onClick={() => setPreviewOpen(false)}
                className="p-2 hover:bg-slate-100 rounded-xl text-slate-500 transition"
                title="Close preview"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-grow bg-slate-100 relative min-h-0">
              {previewError ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-6">
                  <AlertTriangle className="w-8 h-8 text-red-500 mb-2" />
                  <p className="text-sm font-bold text-slate-800 mb-1">Preview unavailable</p>
                  <p className="text-xs text-slate-500 max-w-sm">{previewError}</p>
                </div>
              ) : (
                <iframe
                  src={previewUrl}
                  title="Document Preview"
                  className="w-full h-full"
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Image Resize Modal */}
      {resizeTarget && (
        <ImageResizeDialog
          document={doc}
          image={resizeTarget}
          version={imagesVersion}
          onClose={() => setResizeTarget(null)}
          onResized={(data) => {
            // The drawn size changed, so both the cached inventory and every
            // tile thumbnail are now stale.
            setImageInventory([]);
            setImagesVersion((v) => v + 1);
            const text = data.message || 'Image resized.';
            setImageReplaceNotice({ tone: 'success', text });
            setAiResult(text);
            refreshFullPreview();
          }}
        />
      )}

      {/* Header & Footer Manager Modal */}
      {hfModalOpen && (
        <HeaderFooterEditor
          document={doc}
          token={token}
          existingHeaders={headerFooter.headers}
          existingFooters={headerFooter.footers}
          variants={headerFooter}
          initialSection={hfInitialSection}
          onClose={() => setHfModalOpen(false)}
          onSaveSuccess={handleHfSaveSuccess}
        />
      )}

      {/* Hidden file pickers, triggered programmatically.
          Double-clicking an image has no <input> to attach to, so the click is
          forwarded to these instead of asking the user to find an upload button. */}
      <input
        ref={imagePickInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/bmp,image/tiff,image/webp"
        className="hidden"
        onChange={handleImagePick}
      />
      <input
        ref={promptImageInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/bmp,image/tiff,image/webp"
        className="hidden"
        onChange={handlePromptImagePick}
      />

      {/* Result of the last image swap. Kept in the panel rather than an alert()
          so it sits next to the document it describes. */}
      {imageReplaceNotice && (
        <div
          className={`fixed bottom-24 left-1/2 -translate-x-1/2 z-50 max-w-lg flex items-start gap-2 px-4 py-3 rounded-2xl shadow-2xl border text-xs font-semibold ${
            imageReplaceNotice.tone === 'error'
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-emerald-50 border-emerald-200 text-emerald-700'
          }`}
        >
          {imageReplaceNotice.tone === 'error' ? (
            <AlertTriangle className="w-4 h-4 shrink-0 mt-px" />
          ) : (
            <CheckCircle2 className="w-4 h-4 shrink-0 mt-px" />
          )}
          <span className="min-w-0 break-words">{imageReplaceNotice.text}</span>
          <button
            type="button"
            onClick={() => setImageReplaceNotice(null)}
            className="shrink-0 opacity-60 hover:opacity-100"
            title="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
};
