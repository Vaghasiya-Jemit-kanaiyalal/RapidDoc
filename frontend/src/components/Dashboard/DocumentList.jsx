import React from 'react';
import { FileText, Download, Edit, Calendar, Play, CheckCircle2, Clock, Sparkles, ChevronRight, FileSpreadsheet } from 'lucide-react';
import { motion } from 'framer-motion';
import { DocumentListSkeleton } from '../Editor/EditorSkeletons';

export const DocumentList = ({ documents, loading = false, onSelectDocument, onDownloadDocument }) => {
  // While the list is still loading, `documents` is an empty array - which is
  // indistinguishable from "the user really has no documents". Showing the empty
  // state there made a slow connection flash "No documents found" before the
  // real rows appeared. Wait for the fetch instead.
  if (loading) {
    return <DocumentListSkeleton rows={4} />;
  }

  if (!documents || documents.length === 0) {
    return (
      <div className="text-center py-16 bg-white/70 backdrop-blur-md border border-dashed border-borderline rounded-3xl p-8 shadow-card">
        <div className="w-16 h-16 rounded-2xl bg-brand-50 border border-brand-100/60 text-brand-600 flex items-center justify-center mx-auto mb-4 shadow-sm">
          <FileText className="w-8 h-8 text-brand-500" />
        </div>
        <h4 className="font-extrabold text-lg text-ink">No documents found</h4>
        <p className="text-sm text-secondary mt-1.5 max-w-sm mx-auto">
          Upload a PDF or DOCX file above to start analyzing and editing with AI.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden border border-borderline/80 rounded-3xl bg-white/80 backdrop-blur-xl shadow-card">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50/80 border-b border-borderline/60">
              <th className="p-4 sm:px-6 text-xs font-bold uppercase tracking-wider text-secondary">Document Name</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider text-secondary">Type</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider text-secondary">Uploaded</th>
              <th className="p-4 sm:px-6 text-xs font-bold uppercase tracking-wider text-secondary text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-borderline/40">
            {documents.map((doc) => {
              const isFinalized = (doc.pipeline_stage || 1) === 4 || doc.pipeline_status === 'Finalized';
              const isPdf = doc.file_type?.toLowerCase() === 'pdf';

              return (
                <tr 
                  key={doc.id} 
                  className="hover:bg-brand-50/30 transition-colors duration-200 group"
                >
                  <td className="p-4 sm:px-6 flex items-center gap-3.5">
                    <div className={`p-2.5 rounded-2xl shrink-0 ${
                      isPdf 
                        ? 'bg-red-50 border border-red-100 text-red-600' 
                        : 'bg-blue-50 border border-blue-100 text-blue-600'
                    }`}>
                      <FileText className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <span 
                        onClick={() => onSelectDocument(doc)}
                        className="font-bold text-ink text-sm truncate block max-w-[180px] sm:max-w-xs hover:text-brand-600 cursor-pointer transition" 
                        title={doc.name}
                      >
                        {doc.name}
                      </span>
                      {doc.last_edited_date && (
                        <span className="text-[11px] text-secondary flex items-center gap-1 font-medium mt-0.5">
                          <Clock className="w-3 h-3 text-slate-400" /> Edited {doc.last_edited_date}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="p-4">
                    <span className={`inline-block px-2.5 py-1 rounded-full text-[11px] font-extrabold uppercase tracking-wider ${
                      isPdf
                        ? 'bg-red-50 text-red-700 border border-red-200/60'
                        : 'bg-blue-50 text-blue-700 border border-blue-200/60'
                    }`}>
                      {doc.file_type}
                    </span>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-1.5 text-secondary text-xs font-medium">
                      <Calendar className="w-3.5 h-3.5 text-slate-400" />
                      <span>{doc.upload_date}</span>
                    </div>
                  </td>
                  <td className="p-4 sm:px-6 text-right">
                    <div className="flex justify-end items-center gap-2">
                      <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={() => onSelectDocument(doc)}
                        className={`px-3.5 py-1.5 rounded-xl font-bold text-xs flex items-center gap-1.5 transition cursor-pointer shadow-xs ${
                          isFinalized
                            ? 'bg-slate-100 hover:bg-slate-200 text-ink'
                            : 'bg-gradient-to-r from-brand-600 to-brand-700 hover:from-brand-500 hover:to-brand-600 text-white shadow-soft-blue'
                        }`}
                        title="Resume Editing Pipeline"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        <span>{isFinalized ? 'Open' : 'Resume'}</span>
                      </motion.button>
                      <motion.button
                        whileHover={{ scale: 1.08 }}
                        whileTap={{ scale: 0.92 }}
                        onClick={() => onDownloadDocument(doc)}
                        className="p-2 text-emerald-600 hover:bg-emerald-50 border border-borderline/60 rounded-xl transition shadow-xs bg-white cursor-pointer"
                        title="Download Document"
                      >
                        <Download className="w-4 h-4" />
                      </motion.button>
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
