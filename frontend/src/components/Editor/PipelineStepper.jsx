import React from 'react';
import { 
  CheckCircle2, Clock, Play, Save, ChevronRight, 
  FileSignature, FileText, Download, Sparkles, Check
} from 'lucide-react';

const STAGES = [
  { id: 1, label: '1. Ingested', title: 'Uploaded & Parsed', desc: 'File parsed & ready' },
  { id: 2, label: '2. Header & Footer', title: 'Header / Footer Config', desc: 'Page styling & layout' },
  { id: 3, label: '3. Content Edit', title: 'Content & AI Editing', desc: 'Text & AI transformations' },
  { id: 4, label: '4. Finalized', title: 'Review & Export', desc: 'Final export & download' },
];

export const PipelineStepper = ({ 
  currentStage = 1, 
  completionPercent = 25,
  pipelineStatus = 'In Progress',
  onSelectStage, 
  onSaveProgress, 
  onFinalize,
  savingProgress 
}) => {
  return (
    <div className="w-full bg-white border-b border-slate-200/80 px-4 sm:px-6 py-3 shadow-xs">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Left: Stage Stepper Pills */}
        <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto w-full md:w-auto pb-1 md:pb-0 scrollbar-none">
          {STAGES.map((s, idx) => {
            const isCompleted = currentStage > s.id;
            const isCurrent = currentStage === s.id;
            return (
              <React.Fragment key={s.id}>
                <button
                  type="button"
                  onClick={() => onSelectStage && onSelectStage(s.id)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold transition shrink-0 ${
                    isCurrent
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                      : isCompleted
                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100'
                      : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                  }`}
                >
                  <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-extrabold shrink-0 ${
                    isCurrent
                      ? 'bg-white text-blue-700'
                      : isCompleted
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-200 text-slate-600'
                  }`}>
                    {isCompleted ? <Check className="w-3 h-3 stroke-[3]" /> : s.id}
                  </span>
                  <span className="truncate max-w-[120px]">{s.title}</span>
                </button>
                {idx < STAGES.length - 1 && (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Right: Progress bar + Save Progress Resume Button */}
        <div className="flex items-center gap-4 shrink-0 w-full md:w-auto justify-between md:justify-end border-t md:border-t-0 pt-2 md:pt-0 border-slate-100">
          {/* Progress gauge */}
          <div className="flex items-center gap-2.5 min-w-[140px]">
            <div className="flex-grow bg-slate-100 rounded-full h-2 overflow-hidden border border-slate-200">
              <div 
                className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 transition-all duration-500 rounded-full"
                style={{ width: `${completionPercent}%` }}
              />
            </div>
            <span className="text-[11px] font-extrabold text-slate-700">{completionPercent}%</span>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={onSaveProgress}
              disabled={savingProgress}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white font-bold rounded-xl text-xs shadow-sm transition"
              title="Save current progress and resume editing anytime from Dashboard"
            >
              <Save className="w-3.5 h-3.5 text-blue-400" />
              <span>{savingProgress ? 'Saving...' : 'Save & Resume Later'}</span>
            </button>

            {currentStage < 4 && (
              <button
                onClick={onFinalize}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl text-xs shadow-sm transition"
                title="Mark document pipeline as 100% complete"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Mark Final</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
