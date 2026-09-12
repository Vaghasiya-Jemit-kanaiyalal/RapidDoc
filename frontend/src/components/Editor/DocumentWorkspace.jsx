import React, { useState, useEffect } from 'react';
import { downloadDocument } from '../../utils/download';
import laodingEffect from '../../assets/laoding_effect.png';
import { HeaderFooterEditor } from './HeaderFooterEditor';
import { PipelineStepper } from './PipelineStepper';
import { 
  FileText, Download, 
  RefreshCw, AlertTriangle, Save, Loader2, CheckCircle2,
  Send, ZoomIn, X, Wand2, Home, History, ArrowRight, FileSignature, ArrowLeft
} from 'lucide-react';

const AI_STATUSES = [
  'Initializing RapidDoc AI',
  'Scanning your document',
  'Finding text blocks',
  'Analyzing content',
  'Applying changes'
];

export const DocumentWorkspace = ({ document: initialDoc, token, onBack, onHome }) => {
  const [doc, setDoc] = useState(initialDoc);
  
  // Pipeline state
  const [pipelineStage, setPipelineStage] = useState(initialDoc.pipeline_stage || 1);
  const [completionPercent, setCompletionPercent] = useState(initialDoc.completion_percent || 25);
  const [pipelineStatus, setPipelineStatus] = useState(initialDoc.pipeline_status || 'In Progress');
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
  const [headerFooter, setHeaderFooter] = useState({ headers: [], footers: [] });
  
  // Header & Footer Modal State
  const [hfModalOpen, setHfModalOpen] = useState(false);
  const [hfInitialSection, setHfInitialSection] = useState('both');
  
  // Editing state
  const [editingIndex, setEditingIndex] = useState(null);
  const [pendingEdits, setPendingEdits] = useState({});
  const [savingEdits, setSavingEdits] = useState(false);

  useEffect(() => {
    if (initialDoc && initialDoc.draft_edits && Object.keys(initialDoc.draft_edits).length > 0) {
      setPendingEdits(initialDoc.draft_edits);
    }
  }, [initialDoc]);

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

  const refreshFullPreview = async () => {
    setFullPreviewLoading(true);
    setFullPreviewError('');
    try {
      const formData = new FormData();
      formData.append('doc_id', doc.id);
      const res = await fetch('/api/docs/preview', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to render document preview.');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setFullPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch (err) {
      setFullPreviewError(err.message || 'Error rendering document preview.');
    } finally {
      setFullPreviewLoading(false);
    }
  };

  useEffect(() => {
    refreshFullPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.id]);

  // Revoke the generated object URL when it changes or on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  // Cycle the Gemini-style status messages while AI is processing
  useEffect(() => {
    if (!aiProcessing) return;
    setAiStatusIndex(0);
    const interval = setInterval(() => {
      setAiStatusIndex((i) => (i + 1) % AI_STATUSES.length);
    }, 950);
    return () => clearInterval(interval);
  }, [aiProcessing]);

  const fetchContent = async () => {
    setLoadingContent(true);
    setContentError('');
    try {
      const res = await fetch(`/api/documents/${doc.id}/content`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to fetch content');
      }
      setContent(data.content);
    } catch (err) {
      setContentError(err.message || 'Error loading content.');
    } finally {
      setLoadingContent(false);
    }
  };

  const fetchHeaderFooter = async () => {
    try {
      const res = await fetch(`/api/documents/${doc.id}/headers-footers`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await res.json();
      if (res.ok) {
        setHeaderFooter({ headers: data.headers || [], footers: data.footers || [] });
      }
    } catch {
      // non-fatal; header/footer display is best-effort
    }
  };

  useEffect(() => {
    fetchContent();
    fetchHeaderFooter();
  }, [doc.id]);

  const handleDownload = async () => {
    try {
      await downloadDocument(token, doc.id, doc.name);
    } catch (err) {
      alert(err.message || 'Error downloading document.');
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    setPreviewError('');
    try {
      const formData = new FormData();
      formData.append('doc_id', doc.id);

      const res = await fetch('/api/docs/preview', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
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
    setSavingEdits(true);
    try {
      let editsPayload = [];
      if (doc.file_type === 'docx') {
        editsPayload = Object.entries(pendingEdits).map(([index, text]) => ({
          index: parseInt(index),
          text
        }));
      } else {
        // PDF payload matches TextEditItem model
        editsPayload = Object.values(pendingEdits);
      }

      const res = await fetch(`/api/documents/${doc.id}/content`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ edits: editsPayload })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save edits');
      }
      setDoc(data);
      setPendingEdits({});
      await fetchContent();
      await fetchHeaderFooter();
      await refreshDoc();
      await refreshFullPreview();
      setViewMode('full');
    } catch (err) {
      alert(err.message || 'Error saving changes.');
    } finally {
      setSavingEdits(false);
    }
  };

  const handleAiSubmit = async (e) => {
    e.preventDefault();
    const prompt = aiPrompt.trim();
    if (!prompt) return;

    setAiProcessing(true);
    setAiResult('');
    setAiInteractiveMode('none');
    setAiVariantGroups([]);
    setAiSelectedVariants([]);
    setAiChanges([]);

    try {
      const res = await fetch(`/api/documents/${doc.id}/ai-command`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ command: prompt })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'AI command failed');
      }

      if (data.action === 'replace') {
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
        await refreshFullPreview();
      } else {
        setAiResult(data.message || 'I scanned your document. Try e.g. \'Change print to not print\' or \'Change the header to RapidDoc Report\'.');
      }
    } catch (err) {
      setAiResult(`Error: ${err.message}`);
    } finally {
      setAiProcessing(false);
      setAiStatusIndex(0);
    }
  };

  const refreshDoc = async () => {
    try {
      const docRes = await fetch(`/api/documents`, {
        headers: { 'Authorization': `Bearer ${token}` }
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
      const res = await fetch(`/api/documents/${doc.id}/selective-replace`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
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

  const handleHfSaveSuccess = async (updatedDoc) => {
    if (updatedDoc) setDoc(updatedDoc);
    setPipelineStage(prev => Math.max(2, prev));
    setCompletionPercent(prev => Math.max(50, prev));
    await fetchHeaderFooter();
    await fetchContent();
    await refreshDoc();
    await refreshFullPreview();
  };

  const handleSaveProgress = async () => {
    setSavingProgress(true);
    try {
      const res = await fetch(`/api/documents/${doc.id}/pipeline`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          pipeline_stage: pipelineStage,
          completion_percent: completionPercent,
          pipeline_status: 'In Progress',
          draft_edits: pendingEdits
        })
      });
      if (!res.ok) {
        throw new Error('Failed to save pipeline checkpoint');
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
      const res = await fetch(`/api/documents/${doc.id}/pipeline`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          pipeline_stage: 4,
          completion_percent: 100,
          pipeline_status: 'Finalized',
          draft_edits: {}
        })
      });
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
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
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
          <button
            onClick={handleDownload}
            className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-xl text-xs flex items-center gap-2 shadow-sm transition"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download</span>
          </button>
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

      {/* Interactive Pipeline Stepper Header */}
      <PipelineStepper
        currentStage={pipelineStage}
        completionPercent={completionPercent}
        pipelineStatus={pipelineStatus}
        onSelectStage={(stage) => {
          setPipelineStage(stage);
          if (stage === 2) setHfModalOpen(true);
        }}
        onSaveProgress={handleSaveProgress}
        onFinalize={handleFinalizePipeline}
        savingProgress={savingProgress}
      />

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
                  <div className="flex flex-col justify-center items-center py-24">
                    <Loader2 className="w-8 h-8 text-blue-600 animate-spin mb-2" />
                    <span className="text-xs text-slate-400 font-semibold">Rendering live document preview...</span>
                  </div>
                ) : fullPreviewUrl ? (
                  <iframe
                    src={fullPreviewUrl}
                    title="Full Document"
                    className="w-full h-full min-h-[500px] bg-white rounded-lg shadow-lg border border-slate-200"
                  />
                ) : (
                  <div className="flex flex-col justify-center items-center py-16">
                    <Loader2 className="w-8 h-8 text-blue-600 animate-spin mb-2" />
                    <span className="text-xs text-slate-400 font-semibold">Loading document...</span>
                  </div>
                )}
                {fullPreviewLoading && fullPreviewUrl && (
                  <div className="flex items-center justify-center gap-2 mt-2 text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Refreshing preview...</span>
                  </div>
                )}
              </div>
            ) : loadingContent ? (
              <div className="flex-grow flex flex-col justify-center items-center py-16">
                <Loader2 className="w-8 h-8 text-blue-600 animate-spin mb-2" />
                <span className="text-xs text-slate-400 font-semibold">Extracting document text blocks...</span>
              </div>
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
              <div className="flex-grow overflow-y-auto max-h-[560px] rounded-xl bg-slate-200/60 p-4 sm:p-6">
                <div className="bg-white shadow-xl shadow-slate-300/60 rounded-sm max-w-[680px] mx-auto min-h-[700px] p-8 sm:p-12 flex flex-col">
                  {/* Interactive Header Zone */}
                  <div 
                    onClick={() => { setHfInitialSection('header'); setHfModalOpen(true); }}
                    className="group relative text-center text-xs border-b-2 border-dashed border-slate-200 hover:border-blue-400 p-2.5 mb-4 rounded-xl cursor-pointer hover:bg-blue-50/50 transition duration-150"
                  >
                    {headerFooter.headers.length > 0 ? (
                      headerFooter.headers.map((h, i) => (
                        <div key={`eh-${i}`} className="whitespace-pre-wrap font-medium text-slate-700 text-[11px]">
                          {h}
                        </div>
                      ))
                    ) : (
                      <span className="text-slate-400 italic text-[11px]">Click to add / edit Document Header...</span>
                    )}
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition text-[8px] font-bold text-blue-600 uppercase bg-blue-100 border border-blue-200 px-2 py-0.5 rounded-md pointer-events-none flex items-center gap-1 shadow-xs">
                      <FileSignature className="w-3 h-3" /> Edit Header
                    </span>
                  </div>

                  <div className="flex-grow">
                    {content.length === 0 ? (
                      <p className="text-sm text-slate-400 italic">No paragraph items found in this DOCX file.</p>
                    ) : (
                      content.map((p) => {
                        const isEditing = editingIndex === p.index;
                        const hasUserEdit = pendingEdits[p.index] !== undefined && pendingEdits[p.index] !== p.text;
                        const change = aiChanges.find(c => c.index === p.index);
                        const isHighlighted = hasUserEdit || !!change;
                        const currentText = pendingEdits[p.index] !== undefined ? pendingEdits[p.index] : p.text;
                        const oldText = change ? change.old_text : p.text;

                        return (
                          <div 
                            key={p.index} 
                            className={`group relative p-3.5 rounded-xl transition duration-200 text-left cursor-pointer ${
                              isHighlighted
                                ? 'bg-amber-50/90 border border-amber-200/90 shadow-2xs my-1'
                                : 'hover:bg-slate-50'
                            }`}
                            onClick={() => { if (!isEditing) setEditingIndex(p.index); }}
                          >
                            {isEditing ? (
                              <textarea
                                autoFocus
                                value={currentText}
                                onChange={(e) => setPendingEdits({ ...pendingEdits, [p.index]: e.target.value })}
                                onBlur={() => setEditingIndex(null)}
                                className="w-full bg-white border border-blue-400 focus:border-blue-600 rounded-lg p-2 outline-none text-slate-800 resize-y shadow-sm"
                                style={{ fontFamily: fontName, fontSize: `${fontSize}pt` }}
                              />
                            ) : (
                              <p 
                                className="text-slate-800 leading-relaxed break-words font-medium" 
                                style={{ fontFamily: fontName, fontSize: `${fontSize}pt`, minHeight: '1.5rem' }}
                              >
                                {currentText ? (isHighlighted ? highlightDiff(oldText, currentText) : currentText) : (
                                  <span className="text-slate-300 italic font-normal text-sm">Empty paragraph. Click to write...</span>
                                )}
                              </p>
                            )}
                            {isHighlighted && !isEditing && (
                              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                                <span className="inline-flex items-center gap-1 text-[8px] font-bold text-amber-800 uppercase tracking-widest bg-amber-100 border border-amber-300 px-2 py-0.5 rounded-md">
                                  <span>{hasUserEdit ? 'User Edit Highlighted' : 'AI Edit Highlighted'}</span>
                                  {change && (
                                    <>
                                      <span className="line-through text-amber-600/70 ml-1">{change.old_text}</span>
                                      <span className="text-amber-500">→</span>
                                      <span className="text-amber-900 font-extrabold">{change.new_text}</span>
                                    </>
                                  )}
                                </span>
                              </div>
                            )}
                            {!isHighlighted && !isEditing && (
                              <span className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition text-[8px] font-bold text-blue-500 uppercase tracking-widest bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-md pointer-events-none">
                                Edit Paragraph
                              </span>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* Interactive Footer Zone */}
                  <div 
                    onClick={() => { setHfInitialSection('footer'); setHfModalOpen(true); }}
                    className="group relative text-center text-xs border-t-2 border-dashed border-slate-200 hover:border-indigo-400 p-2.5 mt-4 rounded-xl cursor-pointer hover:bg-indigo-50/50 transition duration-150"
                  >
                    {headerFooter.footers.length > 0 ? (
                      headerFooter.footers.map((f, i) => (
                        <div key={`ef-${i}`} className="whitespace-pre-wrap font-medium text-slate-700 text-[11px]">
                          {f}
                        </div>
                      ))
                    ) : (
                      <span className="text-slate-400 italic text-[11px]">Click to add / edit Document Footer...</span>
                    )}
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition text-[8px] font-bold text-indigo-600 uppercase bg-indigo-100 border border-indigo-200 px-2 py-0.5 rounded-md pointer-events-none flex items-center gap-1 shadow-xs">
                      <FileSignature className="w-3 h-3" /> Edit Footer
                    </span>
                  </div>
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
                        <span className="text-[10px] font-semibold text-slate-500">
                          {headerFooter.headers[0] ? `Header: "${headerFooter.headers[0]}"` : 'Click to add/edit Header overlay'}
                        </span>
                        <span className="text-[8px] font-bold uppercase text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded">Header</span>
                      </div>
                      
                      <div className="space-y-2.5">
                        {page.blocks.length === 0 ? (
                          <p className="text-xs text-slate-400 italic">No text blocks on this page.</p>
                        ) : (
                          page.blocks.map((block) => {
                            const blockKey = `${page.page_num}_${block.block_no}`;
                            const isEditing = editingIndex === blockKey;
                            const hasUserEdit = pendingEdits[blockKey] !== undefined && pendingEdits[blockKey].text !== block.text;
                            const currentText = pendingEdits[blockKey] !== undefined ? pendingEdits[blockKey].text : block.text;
                            return (
                              <div 
                                key={block.block_no}
                                onClick={() => { if (!isEditing) setEditingIndex(blockKey); }}
                                className={`group relative p-3 border rounded-xl transition cursor-pointer text-left ${
                                  hasUserEdit
                                    ? 'bg-amber-50/90 border-amber-300 shadow-xs'
                                    : 'bg-white hover:bg-slate-50/50 border-slate-100 hover:border-amber-200'
                                }`}
                              >
                                {isEditing ? (
                                  <textarea
                                    autoFocus
                                    value={currentText}
                                    onChange={(e) => {
                                      setPendingEdits({
                                        ...pendingEdits,
                                        [blockKey]: {
                                          page_num: page.page_num,
                                          block_no: block.block_no,
                                          bbox: block.bbox,
                                          text: e.target.value
                                        }
                                      });
                                    }}
                                    onBlur={() => setEditingIndex(null)}
                                    className="w-full bg-white border border-amber-400 focus:border-amber-600 rounded-lg p-1.5 outline-none text-xs text-slate-800 resize-y shadow-sm"
                                  />
                                ) : (
                                  <p 
                                    className="text-xs text-slate-700 leading-relaxed font-medium"
                                    style={{ fontFamily: fontName, fontSize: `${Math.max(8, fontSize - 2)}pt`, minHeight: '1.25rem' }}
                                  >
                                    {currentText ? (hasUserEdit ? highlightDiff(block.text, currentText) : currentText) : (
                                      <span className="text-slate-300 italic">Empty text block. Click to write...</span>
                                    )}
                                  </p>
                                )}
                                {hasUserEdit && !isEditing && (
                                  <span className="mt-1.5 inline-block text-[7px] font-bold text-amber-800 uppercase bg-amber-100 border border-amber-200 px-1.5 py-0.5 rounded">
                                    User Edit Highlighted
                                  </span>
                                )}
                                {!isEditing && !hasUserEdit && (
                                  <span className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition text-[7px] font-bold text-amber-600 uppercase bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded pointer-events-none">
                                    Edit Block
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
                        <span className="text-[10px] font-semibold text-slate-500">
                          {headerFooter.footers[0] ? `Footer: "${headerFooter.footers[0]}"` : 'Click to add/edit Footer overlay'}
                        </span>
                        <span className="text-[8px] font-bold uppercase text-indigo-600 bg-indigo-100 px-1.5 py-0.5 rounded">Footer</span>
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
        <form onSubmit={handleAiSubmit} className="max-w-4xl mx-auto">
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
            <div className="mb-2 flex flex-col gap-2 max-h-40 overflow-y-auto rounded-2xl border border-emerald-200 bg-emerald-50/60 p-3">
              <span className="text-xs font-bold text-slate-600 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                Changes applied (highlighted in the document above)
              </span>
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

          <div className="relative rounded-2xl border border-slate-200 bg-slate-50 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition shadow-sm">
            <input
              type="text"
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder='Ask RapidDoc AI to edit... e.g. "Change 24DCS044 to 145" or "Change the header to RapidDoc Report"'
              disabled={aiProcessing}
              className="w-full bg-transparent px-4 py-3 pr-14 outline-none text-sm text-slate-700 disabled:opacity-50 placeholder:text-slate-400"
            />
            <button
              type="submit"
              disabled={aiProcessing || !aiPrompt.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-2.5 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-700 hover:to-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl flex items-center gap-1.5 shadow-md shadow-blue-500/20 transition"
            >
              {aiProcessing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Floating Save Edits Bar */}
      {Object.keys(pendingEdits).length > 0 && viewMode === 'edit' && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-6 z-50 border border-slate-800 animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="text-left">
            <p className="text-xs font-bold">{Object.keys(pendingEdits).length} unsaved text change(s)</p>
            <p className="text-[9px] text-slate-400">Save changes to write back to the document file.</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPendingEdits({})}
              disabled={savingEdits}
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

      {/* Header & Footer Manager Modal */}
      {hfModalOpen && (
        <HeaderFooterEditor
          document={doc}
          token={token}
          existingHeaders={headerFooter.headers}
          existingFooters={headerFooter.footers}
          initialSection={hfInitialSection}
          onClose={() => setHfModalOpen(false)}
          onSaveSuccess={handleHfSaveSuccess}
        />
      )}
    </div>
  );
};
