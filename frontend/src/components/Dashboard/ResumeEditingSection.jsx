import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  Clock,
  FileText,
  Play,
  Sparkles,
} from 'lucide-react';

const isFinalized = (doc) => (
  (doc.pipeline_stage || 1) === 4 || doc.pipeline_status === 'Finalized'
);

const lastActivityAt = (doc) => String(
  doc.last_opened_at || doc.last_edited_date || doc.upload_date || ''
);

/**
 * Inline dashboard section showing the most recent in-progress document.
 * Always visible when there are active documents - not a dismissible popup.
 * Prioritizes the document that was most recently opened/edited.
 */
export const ResumeEditingSection = ({ documents = [], onSelectDocument }) => {
  const activeDocuments = useMemo(
    () => documents.filter((doc) => !isFinalized(doc)),
    [documents],
  );

  const recentDocument = useMemo(() => {
    if (activeDocuments.length === 0) return null;
    return [...activeDocuments].sort((a, b) => {
      const dateOrder = lastActivityAt(b).localeCompare(lastActivityAt(a));
      if (dateOrder !== 0) return dateOrder;
      // If timestamps are equal, prefer documents with more recent last_opened_at
      if (a.last_opened_at || b.last_opened_at) {
        const openOrder = String(b.last_opened_at || '').localeCompare(String(a.last_opened_at || ''));
        if (openOrder !== 0) return openOrder;
      }
      return String(b.id || '').localeCompare(String(a.id || ''));
    })[0];
  }, [activeDocuments]);

  if (!recentDocument) return null;

  const isPdf = recentDocument.file_type?.toLowerCase() === 'pdf';
  const completion = Math.max(
    5,
    Math.min(100, Number(recentDocument.completion_percent) || 25),
  );
  const lastEdited = lastActivityAt(recentDocument) || 'recently';
  const activeCount = activeDocuments.length;

  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4, duration: 0.5 }}
      className="space-y-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-secondary uppercase tracking-wider flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-brand-500" />
          Continue Where You Left Off
        </h3>
        <span className="text-[11px] font-semibold text-slate-400">
          {activeCount} document{activeCount !== 1 ? 's' : ''} in progress
        </span>
      </div>

      <div className="relative overflow-hidden rounded-2xl bg-white/80 backdrop-blur-xl border border-brand-100/80 shadow-card">
        <div className="absolute -right-8 -top-8 h-24 w-24 rounded-full bg-brand-500/5 blur-2xl" aria-hidden="true" />
        
        <div className="relative p-5 sm:p-6">
          <div className="flex items-start gap-4 sm:gap-5">
            <div className={`mt-0.5 flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border ${
              isPdf
                ? 'border-red-100 bg-red-50 text-red-600'
                : 'border-blue-100 bg-blue-50 text-blue-600'
            }`}>
              <FileText className="h-7 w-7" />
            </div>

            <div className="flex-1 min-w-0">
              <h4 className="text-base sm:text-lg font-extrabold text-ink truncate pr-4">
                {recentDocument.name}
              </h4>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] sm:text-xs font-semibold text-secondary">
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3 w-3 text-slate-400" />
                  {recentDocument.last_opened_at ? 'Opened' : 'Edited'} {lastEdited}
                </span>
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-100">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                  {recentDocument.pipeline_status || 'In Progress'}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => onSelectDocument(recentDocument)}
              className="flex-shrink-0 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-indigo-600 px-5 py-2.5 text-sm font-extrabold text-white shadow-soft-blue transition hover:from-brand-500 hover:to-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2"
            >
              <Play className="h-4 w-4 fill-current" />
              <span className="hidden sm:inline">Continue editing</span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </motion.section>
  );
};