import React, { useState } from 'react';
import { 
  CheckCircle2, Clock, Play, Save, ChevronRight, 
  FileSignature, FileText, Download, Sparkles, Check, Send, SendHorizontal, ArrowRight
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const STAGES = [
  { id: 1, label: '1. Ingested', title: 'Uploaded & Parsed', desc: 'File parsed & ready' },
  { id: 2, label: '2. Header & Footer', title: 'Header & Footer', desc: 'Page styling & layout' },
  { id: 3, label: '3. Content Edit', title: 'AI & Content Edit', desc: 'Text & AI transformations' },
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
  const [flyingPlane, setFlyingPlane] = useState(false);
  const [activeStageSplash, setActiveStageSplash] = useState(null);

  const handleSaveAndResume = async () => {
    setFlyingPlane(true);
    if (onSaveProgress) {
      await onSaveProgress();
    }
    setTimeout(() => {
      setFlyingPlane(false);
    }, 1600);
  };

  const handleStageClick = (stageId) => {
    setActiveStageSplash(stageId);
    setTimeout(() => setActiveStageSplash(null), 1000);
    if (onSelectStage) {
      onSelectStage(stageId);
    }
  };

  return (
    <div className="w-full bg-white/85 backdrop-blur-xl border-b border-borderline/60 px-4 sm:px-6 py-3 shadow-xs relative overflow-hidden">
      {/* Paper Plane Flight Overlay Animation */}
      <AnimatePresence>
        {flyingPlane && (
          <div className="fixed inset-0 pointer-events-none z-50 flex items-center justify-center">
            {/* Trail Particles */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 1, 0] }}
              transition={{ duration: 1.4 }}
              className="absolute w-full h-full"
            >
              {[...Array(8)].map((_, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0.8, x: window.innerWidth * 0.4 + i * 15, y: window.innerHeight * 0.5 - i * 10, scale: 1 }}
                  animate={{ opacity: 0, scale: 0.2, x: window.innerWidth * 0.4 - i * 30, y: window.innerHeight * 0.5 + i * 20 }}
                  transition={{ duration: 0.8, delay: i * 0.05 }}
                  className="absolute w-2 h-2 rounded-full bg-brand-400/80 blur-xs"
                />
              ))}
            </motion.div>

            {/* Flying Paper Plane */}
            <motion.div
              initial={{ x: -100, y: 100, scale: 0.6, rotate: -25, opacity: 0 }}
              animate={{
                x: [ -100, window.innerWidth * 0.1, window.innerWidth * 0.5, window.innerWidth + 200 ],
                y: [ 100, -20, -120, -window.innerHeight * 0.6 ],
                scale: [ 0.6, 1.3, 1.1, 0.4 ],
                rotate: [ -25, 10, 35, 55 ],
                opacity: [ 0, 1, 1, 0 ],
              }}
              transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
              className="absolute p-4 rounded-3xl bg-gradient-to-tr from-brand-600 to-indigo-600 text-white shadow-2xl flex items-center justify-center"
            >
              <SendHorizontal className="w-10 h-10 text-white" />
            </motion.div>

            {/* Notification Toast */}
            <motion.div
              initial={{ opacity: 0, y: 30, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.9 }}
              transition={{ duration: 0.4, delay: 0.2 }}
              className="px-6 py-3.5 bg-ink/90 backdrop-blur-md text-white rounded-2xl shadow-floating text-sm font-bold flex items-center gap-2.5 border border-white/20"
            >
              <Sparkles className="w-4 h-4 text-brand-400" />
              <span>Document progress saved! Resuming anytime from Hub...</span>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 relative z-10">
        {/* Left: Stage Stepper Pills */}
        <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto w-full md:w-auto pb-1 md:pb-0 scrollbar-none">
          {STAGES.map((s, idx) => {
            const isCompleted = currentStage > s.id;
            const isCurrent = currentStage === s.id;
            const hasSplash = activeStageSplash === s.id;

            return (
              <React.Fragment key={s.id}>
                <div className="relative">
                  <motion.button
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    type="button"
                    onClick={() => handleStageClick(s.id)}
                    className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition shrink-0 cursor-pointer ${
                      isCurrent
                        ? 'bg-gradient-to-r from-brand-600 to-indigo-600 text-white shadow-soft-blue'
                        : isCompleted
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/60 hover:bg-emerald-100/60'
                        : 'bg-slate-100/80 text-secondary hover:bg-slate-200/80 hover:text-ink'
                    }`}
                  >
                    <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-extrabold shrink-0 ${
                      isCurrent
                        ? 'bg-white text-brand-700'
                        : isCompleted
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-200 text-secondary'
                    }`}>
                      {isCompleted ? <Check className="w-3 h-3 stroke-[3]" /> : s.id}
                    </span>
                    <span className="truncate max-w-[130px]">{s.title}</span>
                  </motion.button>

                  {/* Stage Activation Splash Burst */}
                  <AnimatePresence>
                    {hasSplash && (
                      <div className="absolute inset-0 pointer-events-none flex items-center justify-center z-20">
                        {[0, 1, 2, 3, 4, 5].map((p) => {
                          const angle = (p / 6) * Math.PI * 2;
                          return (
                            <motion.div
                              key={p}
                              initial={{ opacity: 1, scale: 0.2, x: 0, y: 0 }}
                              animate={{
                                opacity: 0,
                                scale: 1,
                                x: Math.cos(angle) * 32,
                                y: Math.sin(angle) * 32,
                              }}
                              exit={{ opacity: 0 }}
                              transition={{ duration: 0.6 }}
                              className="absolute w-1.5 h-1.5 rounded-full bg-brand-400"
                            />
                          );
                        })}
                      </div>
                    )}
                  </AnimatePresence>
                </div>

                {idx < STAGES.length - 1 && (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Right: Progress bar + Action Buttons */}
        <div className="flex items-center gap-4 shrink-0 w-full md:w-auto justify-between md:justify-end border-t md:border-t-0 pt-2 md:pt-0 border-borderline/40">
          {/* Progress gauge */}
          <div className="flex items-center gap-2.5 min-w-[140px]">
            <div className="flex-grow bg-slate-100 rounded-full h-2 overflow-hidden border border-borderline/40">
              <div 
                className="h-full bg-gradient-to-r from-brand-500 to-indigo-600 transition-all duration-500 rounded-full"
                style={{ width: `${completionPercent}%` }}
              />
            </div>
            <span className="text-[11px] font-extrabold text-ink">{completionPercent}%</span>
          </div>

          {/* Action buttons with Next Step & Paper Plane trigger */}
          <div className="flex items-center gap-2">
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={handleSaveAndResume}
              disabled={savingProgress || flyingPlane}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-ink hover:bg-slate-800 disabled:opacity-50 text-white font-bold rounded-xl text-xs shadow-xs transition cursor-pointer"
              title="Save current progress with paper plane flight animation"
            >
              <SendHorizontal className="w-3.5 h-3.5 text-brand-300" />
              <span>{flyingPlane ? 'Flying...' : savingProgress ? 'Saving...' : 'Save & Resume'}</span>
            </motion.button>

            {currentStage < 4 ? (
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => {
                  const nextStage = currentStage + 1;
                  handleStageClick(nextStage);
                  if (nextStage === 4 && onFinalize) {
                    onFinalize();
                  }
                }}
                className="flex items-center gap-1.5 px-3.5 py-1.5 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-700 hover:to-indigo-700 text-white font-bold rounded-xl text-xs shadow-soft-blue transition cursor-pointer"
                title={`Advance to next step: ${STAGES[currentStage]?.title || 'Next'}`}
              >
                <span>Next Step</span>
                <ArrowRight className="w-3.5 h-3.5 text-brand-200" />
              </motion.button>
            ) : (
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={onFinalize}
                className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl text-xs shadow-xs transition cursor-pointer"
                title="Mark document pipeline as 100% complete"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Finalized</span>
              </motion.button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
