import React from 'react';
import { FileText, Download, Edit, Calendar, Image as ImageIcon } from 'lucide-react';

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

  return (
    <div className="overflow-hidden border border-slate-100 rounded-3xl bg-white/60 shadow-xl shadow-slate-100/40">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50/70 border-b border-slate-100">
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">File Name</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Type</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Images</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Upload Date</th>
              <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-400 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {documents.map((doc) => (
              <tr key={doc.id} className="hover:bg-slate-50/50 transition">
                <td className="p-4 flex items-center gap-3">
                  <div className={`p-2.5 rounded-xl ${
                    doc.file_type === 'pdf' 
                      ? 'bg-red-50 text-red-600' 
                      : 'bg-blue-50 text-blue-600'
                  }`}>
                    <FileText className="w-5 h-5" />
                  </div>
                  <span className="font-semibold text-slate-700 text-sm truncate max-w-[200px] sm:max-w-xs" title={doc.name}>
                    {doc.name}
                  </span>
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
                  <div className="flex items-center gap-1 text-slate-500 text-sm">
                    <ImageIcon className="w-4 h-4 text-slate-400" />
                    <span>{doc.images_count || 0}</span>
                  </div>
                </td>
                <td className="p-4">
                  <div className="flex items-center gap-1.5 text-slate-500 text-sm">
                    <Calendar className="w-4 h-4 text-slate-400" />
                    <span>{doc.upload_date}</span>
                  </div>
                </td>
                <td className="p-4 text-right">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => onSelectDocument(doc)}
                      className="p-2 text-blue-600 hover:bg-blue-50 border border-transparent hover:border-blue-100 rounded-xl transition shadow-sm bg-white"
                      title="Edit Styling"
                    >
                      <Edit className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => onDownloadDocument(doc)}
                      className="p-2 text-emerald-600 hover:bg-emerald-50 border border-transparent hover:border-emerald-100 rounded-xl transition shadow-sm bg-white"
                      title="Download File"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
