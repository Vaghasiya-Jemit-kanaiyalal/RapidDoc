import React, { useState, useEffect } from 'react';
import { StylingPanel } from './StylingPanel';
import { downloadDocument } from '../../utils/download';
import laodingEffect from '../../assets/laoding_effect.png';
import { 
  FileText, Download, History, 
  Search, RefreshCw, AlertTriangle, Save, Loader2, Info, CheckCircle2,
  Sparkles, Send, ZoomIn, X, Wand2, Home
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
  const [activeTab, setActiveTab] = useState('edit'); // 'edit', 'findReplace', 'details'
  
  // Dynamic Styling State (synchronized with StylingPanel)
  const [fontName, setFontName] = useState('Arial');
  const [fontSize, setFontSize] = useState(12);

  // Content state
  const [content, setContent] = useState(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState('');
  
  // Editing state
  const [editingIndex, setEditingIndex] = useState(null);
  const [pendingEdits, setPendingEdits] = useState({});
  const [savingEdits, setSavingEdits] = useState(false);

  // Find & Replace state
  const [findText, setFindText] = useState('');
  const [replaceText, setReplaceText] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(true);
  const [replacing, setReplacing] = useState(false);
  const [findReplaceResult, setFindReplaceResult] = useState('');

  // AI Assistant state
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiProcessing, setAiProcessing] = useState(false);
  const [aiStatusIndex, setAiStatusIndex] = useState(0);
  const [aiResult, setAiResult] = useState('');

  // Preview state
  const [canPreview, setCanPreview] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);

  // PDF preview modal state
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

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
      const res = await fetch(`http://localhost:8000/api/documents/${doc.id}/content`, {
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

  useEffect(() => {
    fetchContent();
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

      const res = await fetch('http://localhost:8000/api/docs/preview', {
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

  const handleSaveSuccess = (updatedDoc) => {
    setDoc(updatedDoc);
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

      const res = await fetch(`http://localhost:8000/api/documents/${doc.id}/content`, {
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
      setCanPreview(true);
    } catch (err) {
      alert(err.message || 'Error saving changes.');
    } finally {
      setSavingEdits(false);
    }
  };

  const handleFindReplace = async (e) => {
    e.preventDefault();
    if (!findText) return;
    setReplacing(true);
    setFindReplaceResult('');
    try {
      const res = await fetch(`http://localhost:8000/api/documents/${doc.id}/find-replace`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          find_text: findText,
          replace_text: replaceText,
          case_sensitive: caseSensitive
        })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Find and replace failed');
      }
      setFindReplaceResult(`Successfully replaced ${data.matches_replaced} occurrence(s)!`);
      setFindText('');
      setReplaceText('');
      await fetchContent();
      setCanPreview(true);
      
      // Refresh doc header history list
      const docRes = await fetch(`http://localhost:8000/api/documents`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const docList = await docRes.json();
      const updatedDoc = docList.find(d => d.id === doc.id);
      if (updatedDoc) {
        setDoc(updatedDoc);
      }
    } catch (err) {
      setFindReplaceResult(`Error: ${err.message}`);
    } finally {
      setReplacing(false);
    }
  };

  const handleAiSubmit = async (e) => {
    e.preventDefault();
    const prompt = aiPrompt.trim();
    if (!prompt) return;

    setAiProcessing(true);
    setAiResult('');
    setCanPreview(false);
    setPreviewMode(false);

    // Understand commands like: replace "old text" with "new text"
    const match = prompt.match(/^replace\s+(?:the\s+)?["'“”]?([^"'“”]+?)["'“”]?\s+(?:with|by|to)\s+["'“”]?([^"'“”]+?)["'“”]?\.?\s*$/i);
    const findText = match ? match[1].trim() : '';
    const replaceText = match ? match[2].trim() : '';

    try {
      // Keep the Gemini-style loading effect visible while AI works
      await new Promise((resolve) => setTimeout(resolve, 2600));

      if (findText && replaceText) {
        const res = await fetch(`http://localhost:8000/api/documents/${doc.id}/find-replace`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            find_text: findText,
            replace_text: replaceText,
            case_sensitive: false
          })
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'AI edit failed');
        }
        setAiResult(`Replaced "${findText}" with "${replaceText}" — ${data.matches_replaced} match(es) applied.`);
      } else {
        setAiResult('I scanned your document. Try a command like: replace "old text" with "new text" to apply an edit.');
      }
      setCanPreview(true);
      await fetchContent();
    } catch (err) {
      setAiResult(`Error: ${err.message}`);
    } finally {
      setAiProcessing(false);
      setAiStatusIndex(0);
    }
  };

  return (
    <div className="flex flex-col lg:flex-row h-screen bg-slate-50 overflow-hidden relative">
      {/* Viewport Area */}
      <div className="flex-grow flex flex-col p-6 overflow-y-auto pb-24">
        <div className="max-w-4xl mx-auto w-full flex-grow flex flex-col gap-6">
          {/* Top Bar info */}
          <div className="flex justify-between items-center bg-white p-4 rounded-2xl border border-slate-100 shadow-sm">
            <div className="flex items-center gap-3">
              <div className={`p-2.5 rounded-xl ${
                doc.file_type === 'pdf' ? 'bg-red-50 text-red-600' : 'bg-blue-50 text-blue-600'
              }`}>
                <FileText className="w-5 h-5" />
              </div>
              <div className="text-left">
                <h2 className="font-bold text-slate-800 text-sm truncate max-w-xs md:max-w-md">{doc.name}</h2>
                <span className="text-[10px] uppercase font-bold text-slate-400">{doc.file_type} File</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={onHome}
                className="flex items-center gap-1.5 px-3.5 py-2.5 bg-slate-50 hover:bg-blue-50 border border-slate-100 hover:border-blue-200 text-slate-500 hover:text-blue-600 font-bold rounded-xl text-xs transition"
                title="Go to Home"
              >
                <Home className="w-4 h-4" />
                <span>Home</span>
              </button>
              <button
                onClick={handlePreview}
                disabled={previewLoading}
                className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl text-xs flex items-center gap-2 shadow-sm transition"
                title="Generate a live PDF preview of this document"
              >
                {previewLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ZoomIn className="w-4 h-4" />
                )}
                <span>{previewLoading ? 'Generating...' : 'Preview PDF'}</span>
              </button>
              <button
                onClick={handleDownload}
                className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-xl text-xs flex items-center gap-2 shadow-sm transition"
              >
                <Download className="w-4 h-4" />
                <span>Download File</span>
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-2 bg-slate-200/60 p-1.5 rounded-2xl self-start">
            <button
              onClick={() => setActiveTab('edit')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'edit' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Document Editor</span>
            </button>
            <button
              onClick={() => setActiveTab('findReplace')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'findReplace' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Search className="w-3.5 h-3.5" />
              <span>Find & Replace</span>
            </button>
            <button
              onClick={() => setActiveTab('details')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'details' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Info className="w-3.5 h-3.5" />
              <span>Document Info</span>
            </button>
          </div>

          {/* AI Assistant Prompt Bar — easy to find */}
          {activeTab === 'edit' && (
            <form
              onSubmit={handleAiSubmit}
              className="relative rounded-3xl p-3 sm:p-4 border-2 border-blue-200 bg-gradient-to-r from-blue-50 via-indigo-50 to-purple-50 shadow-sm"
            >
              <div className="flex items-center gap-2.5 sm:gap-3">
                <div className="p-2.5 rounded-2xl bg-gradient-to-br from-brand-600 to-indigo-600 text-white shadow-lg shadow-blue-500/30 shrink-0">
                  <Sparkles className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder='Ask RapidDoc AI to edit... e.g. replace "sales" with "revenue"'
                  disabled={aiProcessing}
                  className="flex-grow min-w-0 px-3.5 sm:px-4 py-2.5 bg-white border border-blue-200 focus:border-brand-500 rounded-xl outline-none text-sm text-slate-700 shadow-inner disabled:opacity-50 transition"
                />
                <button
                  type="submit"
                  disabled={aiProcessing || !aiPrompt.trim()}
                  className="px-3 sm:px-5 py-2.5 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl text-xs flex items-center gap-1.5 shadow-lg shadow-blue-500/25 transition whitespace-nowrap"
                >
                  {aiProcessing ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  <span>{aiProcessing ? 'Thinking...' : 'Ask AI'}</span>
                </button>
              </div>

              {aiResult && (
                <div className={`mt-3 flex items-start gap-2 text-xs font-semibold ${
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
            </form>
          )}

          {/* Editor/Content Area */}
          <div className="relative flex-grow bg-white border border-slate-100 rounded-[32px] shadow-lg p-6 sm:p-8 flex flex-col min-h-[400px]">
            {activeTab === 'edit' && (
              <div className="flex-grow flex flex-col">
                <div className="flex justify-between items-center gap-3 mb-4 pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                      {previewMode ? 'Document Preview' : 'Interactive Body Canvas'}
                    </span>
                    {doc.file_type === 'pdf' && (
                      <span className="text-[9px] text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md font-bold uppercase flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" />
                        <span>Bounding Box Constraints Active</span>
                      </span>
                    )}
                  </div>
                  {canPreview && !previewMode && (
                    <button
                      onClick={() => setPreviewMode(true)}
                      className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl text-[11px] flex items-center gap-1.5 shadow-md shadow-blue-500/20 transition shrink-0"
                    >
                      <ZoomIn className="w-3.5 h-3.5" />
                      <span>Preview Edited Document</span>
                    </button>
                  )}
                  {previewMode && (
                    <button
                      onClick={() => setPreviewMode(false)}
                      className="px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold rounded-xl text-[11px] flex items-center gap-1.5 transition shrink-0"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Exit Preview</span>
                    </button>
                  )}
                </div>

                {previewMode ? (
                  content && doc.file_type === 'docx' ? (
                    <div className="flex-grow overflow-y-auto max-h-[500px] rounded-2xl bg-slate-100 p-4 sm:p-6">
                      <div className="bg-white shadow-lg rounded-lg max-w-[640px] mx-auto p-7 sm:p-10">
                        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 mb-1">{doc.name}</h1>
                        <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-4">{doc.file_type} document</p>
                        <div className="border-b border-slate-200 mb-5" />
                        {content.length === 0 ? (
                          <p className="text-sm text-slate-400 italic">No content to preview.</p>
                        ) : (
                          content.map((p) => (
                            p.text ? (
                              <p key={p.index} className="text-sm text-slate-800 leading-relaxed mb-3">{p.text}</p>
                            ) : (
                              <div key={p.index} className="h-3" />
                            )
                          ))
                        )}
                      </div>
                    </div>
                  ) : content && doc.file_type === 'pdf' ? (
                    <div className="flex-grow overflow-y-auto max-h-[500px] rounded-2xl bg-slate-100 p-4 sm:p-6">
                      {content.length === 0 ? (
                        <p className="text-sm text-slate-400 italic text-center pt-10">No pages to preview.</p>
                      ) : (
                        content.map((page) => (
                          <div key={page.page_num} className="bg-white shadow-lg rounded-lg max-w-[540px] mx-auto mb-6 p-7 sm:p-10 min-h-[680px] relative">
                            <p className="text-[9px] uppercase tracking-widest text-slate-300 font-bold mb-4">RapidDoc Preview</p>
                            {page.blocks.length === 0 ? (
                              <p className="text-xs text-slate-400 italic">This page appears to be blank.</p>
                            ) : (
                              page.blocks.map((block) => (
                                <p key={block.block_no} className="text-xs text-slate-800 leading-relaxed mb-2.5 text-justify">
                                  {block.text}
                                </p>
                              ))
                            )}
                            <span className="absolute bottom-3 right-5 text-[9px] text-slate-400 font-semibold">
                              Page {page.page_num + 1}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  ) : (
                    <div className="flex-grow flex flex-col justify-center items-center py-16">
                      <Loader2 className="w-8 h-8 text-blue-600 animate-spin mb-2" />
                      <span className="text-xs text-slate-400 font-semibold">Loading preview...</span>
                    </div>
                  )
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
                  <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2">
                    {content.length === 0 ? (
                      <p className="text-sm text-slate-400 italic">No paragraph items found in this DOCX file.</p>
                    ) : (
                      content.map((p) => {
                        const isEditing = editingIndex === p.index;
                        const currentText = pendingEdits[p.index] !== undefined ? pendingEdits[p.index] : p.text;
                        return (
                          <div 
                            key={p.index} 
                            className="group relative p-3.5 bg-slate-50/50 hover:bg-slate-50 border border-slate-100/50 hover:border-blue-100 rounded-2xl transition duration-200 text-left cursor-pointer"
                            onClick={() => { if (!isEditing) setEditingIndex(p.index); }}
                          >
                            {isEditing ? (
                              <textarea
                                autoFocus
                                value={currentText}
                                onChange={(e) => setPendingEdits({ ...pendingEdits, [p.index]: e.target.value })}
                                onBlur={() => setEditingIndex(null)}
                                className="w-full bg-white border border-blue-300 focus:border-blue-500 rounded-xl p-2 outline-none text-slate-800 resize-y shadow-sm"
                                style={{ fontFamily: fontName, fontSize: `${fontSize}pt` }}
                              />
                            ) : (
                              <p 
                                className="text-slate-800 leading-relaxed break-words" 
                                style={{ fontFamily: fontName, fontSize: `${fontSize}pt`, minHeight: '1.5rem' }}
                              >
                                {currentText || <span className="text-slate-300 italic font-normal text-sm">Empty paragraph. Click to write...</span>}
                              </p>
                            )}
                            {!isEditing && (
                              <span className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition text-[8px] font-bold text-blue-500 uppercase tracking-widest bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-md pointer-events-none">
                                Edit Paragraph
                              </span>
                            )}
                          </div>
                        );
                      })
                    )}
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
                          </div>
                          
                          <div className="space-y-2.5">
                            {page.blocks.length === 0 ? (
                              <p className="text-xs text-slate-400 italic">No text blocks on this page.</p>
                            ) : (
                              page.blocks.map((block) => {
                                const blockKey = `${page.page_num}_${block.block_no}`;
                                const isEditing = editingIndex === blockKey;
                                const currentText = pendingEdits[blockKey] !== undefined ? pendingEdits[blockKey].text : block.text;
                                return (
                                  <div 
                                    key={block.block_no}
                                    onClick={() => { if (!isEditing) setEditingIndex(blockKey); }}
                                    className="group relative p-3 bg-white hover:bg-slate-50/50 border border-slate-100 hover:border-amber-200 rounded-xl transition cursor-pointer text-left"
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
                                        className="w-full bg-white border border-amber-300 focus:border-amber-500 rounded-lg p-1.5 outline-none text-xs text-slate-800 resize-y shadow-sm"
                                      />
                                    ) : (
                                      <p 
                                        className="text-xs text-slate-700 leading-relaxed font-medium"
                                        style={{ fontFamily: fontName, fontSize: `${Math.max(8, fontSize - 2)}pt`, minHeight: '1.25rem' }}
                                      >
                                        {currentText || <span className="text-slate-300 italic">Empty text block. Click to write...</span>}
                                      </p>
                                    )}
                                    {!isEditing && (
                                      <span className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition text-[7px] font-bold text-amber-600 uppercase bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded pointer-events-none">
                                        Edit Block
                                      </span>
                                    )}
                                  </div>
                                );
                              })
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                ) : null}
              </div>
            )}

            {activeTab === 'findReplace' && (
              <div className="flex-grow flex flex-col justify-center max-w-lg mx-auto w-full py-8 text-left">
                <h3 className="text-lg font-bold text-slate-800 mb-2">Find & Replace text</h3>
                <p className="text-xs text-slate-400 mb-6">
                  Perform document-wide replacements. In PDFs, matched text is whited-out and redrawn in place. In DOCXs, edits apply to paragraphs and tables while preserving style runs.
                </p>

                {findReplaceResult && (
                  <div className={`mb-6 p-4 rounded-xl text-xs font-semibold flex items-center gap-2 border ${
                    findReplaceResult.startsWith('Error') 
                      ? 'bg-red-50 border-red-100 text-red-700' 
                      : 'bg-emerald-50 border-emerald-100 text-emerald-700'
                  }`}>
                    {findReplaceResult.startsWith('Error') ? <AlertTriangle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                    <span>{findReplaceResult}</span>
                  </div>
                )}

                <form onSubmit={handleFindReplace} className="space-y-4">
                  <div className="space-y-1">
                    <label className="block text-xs font-bold text-slate-500 uppercase">Text to Find</label>
                    <input
                      type="text"
                      required
                      value={findText}
                      onChange={(e) => setFindText(e.target.value)}
                      placeholder="e.g. Agreement Date"
                      className="w-full px-3.5 py-3 bg-slate-50 border border-slate-200 focus:border-blue-500 rounded-xl outline-none text-sm text-slate-700 transition"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-xs font-bold text-slate-500 uppercase">Replacement Text</label>
                    <input
                      type="text"
                      value={replaceText}
                      onChange={(e) => setReplaceText(e.target.value)}
                      placeholder="e.g. 2026-08-07"
                      className="w-full px-3.5 py-3 bg-slate-50 border border-slate-200 focus:border-blue-500 rounded-xl outline-none text-sm text-slate-700 transition"
                    />
                  </div>

                  <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 select-none cursor-pointer pt-2">
                    <input
                      type="checkbox"
                      checked={caseSensitive}
                      onChange={(e) => setCaseSensitive(e.target.checked)}
                      className="w-4 h-4 text-blue-600 border-slate-200 rounded focus:ring-blue-500"
                    />
                    <span>Case Sensitive Match</span>
                  </label>

                  <button
                    type="submit"
                    disabled={replacing || !findText}
                    className="w-full mt-6 py-3.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg shadow-blue-500/10 flex items-center justify-center gap-2 transition"
                  >
                    {replacing ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Replacing matches...</span>
                      </>
                    ) : (
                      <>
                        <Search className="w-4 h-4" />
                        <span>Search & Replace All</span>
                      </>
                    )}
                  </button>
                </form>
              </div>
            )}

            {activeTab === 'details' && (
              <div className="flex-grow flex flex-col justify-center text-center p-6 max-w-md mx-auto">
                <div className="relative mb-6 mx-auto">
                  <div className={`w-20 h-28 rounded-2xl border-2 flex flex-col justify-between p-3.5 bg-slate-50 shadow-md ${
                    doc.file_type === 'pdf' ? 'border-red-100 text-red-500' : 'border-blue-100 text-blue-500'
                  }`}>
                    <div className="flex justify-between items-start">
                      <FileText className="w-6 h-6" />
                      <span className="text-[7px] font-bold uppercase border px-1 rounded">{doc.file_type}</span>
                    </div>
                    <div className="space-y-1">
                      <div className="w-full h-1 bg-slate-200 rounded"></div>
                      <div className="w-[80%] h-1 bg-slate-200 rounded"></div>
                      <div className="w-[60%] h-1 bg-slate-200 rounded"></div>
                    </div>
                  </div>
                </div>

                <h3 className="text-lg font-bold text-slate-800 mb-1">{doc.name}</h3>
                <p className="text-xs text-slate-400 capitalize mb-6">{doc.file_type} document format</p>
                
                <div className="grid grid-cols-2 gap-4 w-full bg-slate-50 p-4 rounded-2xl border border-slate-100 text-left">
                  <div>
                    <span className="block text-[9px] text-slate-400 font-bold uppercase">Images Detected</span>
                    <span className="text-xs font-bold text-slate-700">{doc.images_count || 0} images</span>
                  </div>
                  <div>
                    <span className="block text-[9px] text-slate-400 font-bold uppercase">Uploaded Date</span>
                    <span className="text-xs font-bold text-slate-700">{doc.upload_date}</span>
                  </div>
                </div>
              </div>
            )}

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

          {/* Audit History Log */}
          <div className="bg-white border border-slate-100 rounded-3xl p-6 shadow-sm">
            <h4 className="font-bold text-slate-800 text-sm mb-4 flex items-center gap-2">
              <History className="w-4 h-4 text-slate-400" />
              <span>Version & Edit History</span>
            </h4>
            
            <div className="space-y-3 max-h-48 overflow-y-auto pr-2">
              {doc.edit_history && doc.edit_history.map((entry, index) => (
                <div key={index} className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl text-xs border border-slate-100">
                  <span className="font-semibold text-slate-400 bg-slate-200/50 px-2 py-0.5 rounded-md self-start">
                    {entry.date}
                  </span>
                  <p className="text-slate-600 font-medium flex-grow text-left">
                    {entry.action}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Floating Save Edits Bar */}
      {Object.keys(pendingEdits).length > 0 && !previewMode && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-6 z-50 border border-slate-800 animate-in fade-in slide-in-from-bottom-4 duration-300">
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

      {/* Right Sidebar Styling Controls */}
      <StylingPanel
        document={doc}
        token={token}
        onBack={onBack}
        onSaveSuccess={handleSaveSuccess}
        fontName={fontName}
        setFontName={setFontName}
        fontSize={fontSize}
        setFontSize={setFontSize}
      />
    </div>
  );
};

