import React from 'react';
import { FileText, Download, Edit, Calendar, Image as ImageIcon, Play, CheckCircle2, Clock } from 'lucide-react';

export const DocumentList = ({ documents, onSelectDocument, onDownloadDocument }) => {
  if (!documents || documents.length === 0) {
    return (
      <div className="text-center py-12 bg-white/40 border border-dashed border-slate-200 rounded-3xl p-6">
        <FileText className="w-10 h-10 text-slate-300 mx-auto mb-3" />
        <h4 className="font-semibold text-slate-700">No documents found</h4>
        <p className="text-sm text-slate-400 mt-1">Upload a PDF or DOCX file to get started.</p>
      </div>
    );
  }

  const getStageLabel = (stage) => {
    switch (stage) {
      case 1: return 'Ingested';
      case 2: return 'Header/Footer';
      case 3: return 'Content Edit';
      case 4: return 'Finalized';
      default: return 'Ingested';
    }
  };

  return (
    <div className="overflow-hidden border border-slate-100 rounded-3xl bg-white/60 shadow-xl shadow-slate-100/40">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50/70 border-b border-slate-100">
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">File Name</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Type</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Pipeline Status</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Upload Date</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {documents.map((doc) => {
              const stage = doc.pipeline_stage || 1;
              const percent = doc.completion_percent || 25;
              const isFinalized = stage === 4 || doc.pipeline_status === 'Finalized';

              return (
                <tr key={doc.id} className="hover:bg-slate-50/50 transition">
                  <td className="p-4 flex items-center gap-3">
                    <div className={`p-2.5 rounded-xl ${
                      doc.file_type === 'pdf' 
                        ? 'bg-red-50 text-red-600' 
                        : 'bg-blue-50 text-blue-600'
                    }`}>
                      <FileText className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <span className="font-semibold text-slate-700 text-sm truncate block max-w-[200px] sm:max-w-xs" title={doc.name}>
                        {doc.name}
                      </span>
                      {doc.last_edited_date && (
                        <span className="text-[10px] text-slate-400 flex items-center gap-1 font-medium">
                          <Clock className="w-2.5 h-2.5" /> Edited {doc.last_edited_date}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="p-4">
                    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                      doc.file_type === 'pdf'
                        ? 'bg-red-100/70 text-red-700 border border-red-200/50'
                        : 'bg-blue-100/70 text-blue-700 border border-blue-200/50'
                    }`}>
                      {doc.file_type}
                    </span>
                  </td>
                  <td className="p-4">
                    <div className="space-y-1.5 max-w-[160px]">
                      <div className="flex justify-between items-center text-[10px] font-bold">
                        <span className={isFinalized ? 'text-emerald-700' : 'text-blue-700'}>
                          Stage {stage}/4: {getStageLabel(stage)}
                        </span>
                        <span className="text-slate-400">{percent}%</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden border border-slate-200">
                        <div 
                          className={`h-full rounded-full transition-all duration-300 ${
                            isFinalized ? 'bg-emerald-500' : 'bg-blue-600'
                          }`}
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-1.5 text-slate-500 text-sm">
                      <Calendar className="w-4 h-4 text-slate-400" />
                      <span>{doc.upload_date}</span>
                    </div>
                  </td>
                  <td className="p-4 text-right">
                    <div className="flex justify-end items-center gap-2">
                      <button
                        onClick={() => onSelectDocument(doc)}
                        className={`px-3 py-1.5 rounded-xl font-bold text-xs flex items-center gap-1.5 transition shadow-xs ${
                          isFinalized
                            ? 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                            : 'bg-blue-600 hover:bg-blue-700 text-white shadow-blue-500/20'
                        }`}
                        title="Resume Editing Pipeline"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        <span>{isFinalized ? 'Open' : 'Resume'}</span>
                      </button>
                      <button
                        onClick={() => onDownloadDocument(doc)}
                        className="p-2 text-emerald-600 hover:bg-emerald-50 border border-slate-100 rounded-xl transition shadow-xs bg-white"
                        title="Download File"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
