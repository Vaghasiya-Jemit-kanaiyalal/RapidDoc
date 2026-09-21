import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

export const DynamicMorphingPipeline = () => {
  const [rotationY, setRotationY] = useState(0);
  const [frontDoc, setFrontDoc] = useState(0); // 0: PDF
  const [backDoc, setBackDoc] = useState(1);   // 1: Word
  const [activeTorchDoc, setActiveTorchDoc] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setRotationY((prevRot) => {
        const nextRot = prevRot + 180;
        const nextStep = Math.round(nextRot / 180);
        const nextDoc = nextStep % 3;
        setActiveTorchDoc(nextDoc);
        return nextRot;
      });
    }, 3800); // 2.8s showcase + 1.0s flip = 3.8s

    return () => clearInterval(timer);
  }, []);

  // When flip animation completes, update whichever face is now facing away / hidden
  const handleAnimationComplete = () => {
    const currentStep = Math.round(rotationY / 180);
    const isBackFacingUser = currentStep % 2 === 1;

    if (isBackFacingUser) {
      // Back face is visible to user (e.g., Word).
      // Front face is now hidden on the back — safely pre-load next upcoming document (AI)
      const upcomingDoc = (currentStep + 1) % 3;
      setFrontDoc(upcomingDoc);
    } else {
      // Front face is visible to user (e.g., PDF or AI).
      // Back face is now hidden on the back — safely pre-load next upcoming document
      const upcomingDoc = (currentStep + 1) % 3;
      setBackDoc(upcomingDoc);
    }
  };

  // Torch backlight styles based on current document
  const getTorchStyle = (idx) => {
    switch (idx) {
      case 0: // PDF: Warm soft rose torch
        return {
          beam: 'from-rose-500/50 via-rose-400/30 to-transparent',
          shadow: '0 0 50px 12px rgba(244, 63, 94, 0.35), 0 20px 50px rgba(0,0,0,0.12)',
          rimGlow: 'rgba(244, 63, 94, 0.4)',
        };
      case 1: // Word: Cool azure / sky-blue torch
        return {
          beam: 'from-sky-500/50 via-blue-400/30 to-transparent',
          shadow: '0 0 50px 12px rgba(56, 189, 248, 0.36), 0 20px 50px rgba(0,0,0,0.12)',
          rimGlow: 'rgba(56, 189, 248, 0.42)',
        };
      case 2: // AI: Luminous purple / violet torch
      default:
        return {
          beam: 'from-purple-500/55 via-indigo-400/35 to-transparent',
          shadow: '0 0 55px 14px rgba(168, 85, 247, 0.4), 0 20px 50px rgba(0,0,0,0.12)',
          rimGlow: 'rgba(168, 85, 247, 0.46)',
        };
    }
  };

  const activeTorch = getTorchStyle(activeTorchDoc);

  // Helper to render the clean white internal document contents
  const renderDocumentContent = (type) => {
    switch (type) {
      case 0: // PDF Document
        return (
          <>
            {/* Light Red / Rose Laser Scanning Line */}
            <motion.div
              animate={{ y: [0, 520, 0] }}
              transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-rose-400 to-transparent shadow-[0_0_14px_rgba(244,63,94,0.85)] z-20 pointer-events-none"
            />

            {/* Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-100 relative z-10">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-rose-600 text-white font-black text-sm flex items-center justify-center shadow-xs">
                  PDF
                </div>
                <div>
                  <div className="text-base font-extrabold text-slate-900">Original Document</div>
                  <div className="text-xs text-slate-500 font-medium">Portable Document Format (.pdf)</div>
                </div>
              </div>
              <div className="w-5 h-5 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center">
                <div className="w-2 h-2 rounded-full bg-slate-400" />
              </div>
            </div>

            {/* Document Metadata Badges */}
            <div className="flex gap-2 py-3 border-b border-slate-100 relative z-10">
              <span className="px-3 py-1 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold border border-slate-200">
                High Security
              </span>
              <span className="px-3 py-1 rounded-xl bg-slate-50 text-slate-600 text-xs font-medium border border-slate-200">
                Verified Layout
              </span>
              <span className="px-3 py-1 rounded-xl bg-slate-50 text-slate-600 text-xs font-medium border border-slate-200">
                Encrypted
              </span>
            </div>

            {/* Clean Neutral Body Content */}
            <div className="space-y-3 flex-1 py-3.5 relative z-10">
              <div className="h-3.5 bg-slate-200/90 rounded-full w-full" />
              <div className="h-3.5 bg-slate-100 rounded-full w-4/5" />
              <div className="h-3.5 bg-slate-200/60 rounded-full w-11/12" />

              {/* Formatted Content Preview Area */}
              <div className="h-24 bg-slate-50 rounded-2xl border border-dashed border-slate-200 p-3.5 flex items-center justify-between">
                <div className="space-y-2 flex-1 mr-3">
                  <div className="h-3 bg-slate-200 rounded-full w-3/4" />
                  <div className="h-2.5 bg-slate-200/70 rounded-full w-1/2" />
                  <div className="h-2.5 bg-slate-100 rounded-full w-2/3" />
                </div>
                <div className="w-12 h-12 rounded-2xl bg-slate-200/80 flex flex-col items-center justify-center text-xs text-slate-700 font-black">
                  PDF
                </div>
              </div>

              <div className="h-3.5 bg-slate-100 rounded-full w-3/5" />
              <div className="h-3.5 bg-slate-200/60 rounded-full w-5/6" />
            </div>

            {/* Footer */}
            <div className="flex justify-between items-center pt-3.5 border-t border-slate-100 relative z-10">
              <div className="h-2.5 bg-slate-200 rounded-full w-28" />
              <div className="h-2.5 bg-slate-300 rounded-full w-16" />
            </div>
          </>
        );

      case 1: // Word Document
        return (
          <>
            {/* Light Blue / Sky-Cyan Laser Scanning Line */}
            <motion.div
              animate={{ y: [0, 520, 0] }}
              transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-sky-400 to-transparent shadow-[0_0_14px_rgba(56,189,248,0.85)] z-20 pointer-events-none"
            />

            {/* Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-100 relative z-10">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-blue-600 text-white font-black text-sm flex items-center justify-center shadow-xs">
                  W
                </div>
                <div>
                  <div className="text-base font-extrabold text-slate-900">Word Document</div>
                  <div className="text-xs text-slate-500 font-medium">Editable Document Format (.docx)</div>
                </div>
              </div>
              <div className="w-5 h-5 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center">
                <div className="w-2 h-2 rounded-full bg-slate-400" />
              </div>
            </div>

            {/* Word Formatting Ribbon Toolbar */}
            <div className="flex items-center gap-1.5 p-1.5 bg-slate-50 rounded-xl border border-slate-200 my-1 relative z-10">
              <div className="h-6 bg-white rounded-lg px-2.5 text-xs font-bold text-slate-800 flex items-center shadow-xs border border-slate-200/60">Aa</div>
              <div className="h-6 bg-slate-900 rounded-lg px-2.5 text-xs font-bold text-white flex items-center">B</div>
              <div className="h-6 bg-white rounded-lg px-2.5 text-xs font-medium text-slate-700 flex items-center italic border border-slate-200/60">I</div>
              <div className="h-6 bg-white rounded-lg px-2.5 text-xs font-medium text-slate-700 flex items-center underline border border-slate-200/60">U</div>
              <div className="h-6 bg-slate-100 rounded-lg px-2 text-xs text-slate-700 font-bold ml-auto flex items-center">
                DOCX
              </div>
            </div>

            {/* Body Content */}
            <div className="space-y-3 flex-1 py-3 relative z-10">
              <div className="h-3.5 bg-slate-200/90 rounded-full w-full" />
              <div className="h-3.5 bg-slate-100 rounded-full w-4/5" />
              <div className="h-3.5 bg-slate-200/60 rounded-full w-11/12" />

              {/* Data Table / Structure Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="h-16 bg-slate-50 rounded-2xl border border-slate-200 flex flex-col justify-center px-3.5 space-y-1.5">
                  <div className="h-2.5 bg-slate-300 rounded-full w-full" />
                  <div className="h-2 bg-slate-200 rounded-full w-2/3" />
                </div>
                <div className="h-16 bg-slate-50 rounded-2xl border border-slate-200 flex flex-col justify-center px-3.5 space-y-1.5">
                  <div className="h-2.5 bg-slate-300 rounded-full w-4/5" />
                  <div className="h-2 bg-slate-200 rounded-full w-1/2" />
                </div>
              </div>

              <div className="h-3.5 bg-slate-100 rounded-full w-2/3" />
              <div className="h-3.5 bg-slate-200/60 rounded-full w-5/6" />
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between pt-3.5 border-t border-slate-100 relative z-10">
              <div className="h-2.5 bg-slate-200 rounded-full w-28" />
              <div className="h-2.5 bg-slate-300 rounded-full w-16" />
            </div>
          </>
        );

      case 2: // AI Document Engine
      default:
        return (
          <>
            {/* Light Purple / Violet Laser Scanning Line */}
            <motion.div
              animate={{ y: [0, 520, 0] }}
              transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-purple-400 to-transparent shadow-[0_0_16px_rgba(168,85,247,0.95)] z-20 pointer-events-none"
            />

            {/* Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-100 relative z-10">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-slate-900 text-white font-black text-sm flex items-center justify-center shadow-xs">
                  AI
                </div>
                <div>
                  <div className="text-base font-extrabold text-slate-900">AI Document Engine</div>
                  <div className="text-xs text-slate-500 font-medium flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    Pipeline Active • Lossless
                  </div>
                </div>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-bold border border-slate-200">
                99.9%
              </span>
            </div>

            {/* AI Intent Pills */}
            <div className="flex flex-wrap gap-2 py-3 border-b border-slate-100 relative z-10">
              <span className="px-3 py-1 rounded-xl bg-slate-100 text-slate-800 text-xs font-bold border border-slate-200">
                Smart Summary
              </span>
              <span className="px-3 py-1 rounded-xl bg-slate-50 text-slate-600 text-xs font-medium border border-slate-200">
                Auto-Rewrite
              </span>
              <span className="px-3 py-1 rounded-xl bg-slate-50 text-slate-600 text-xs font-medium border border-slate-200">
                Style Match
              </span>
            </div>

            {/* Body Content */}
            <div className="space-y-3 flex-1 py-3 relative z-10">
              <div className="h-3.5 bg-slate-200/90 rounded-full w-full" />
              <div className="h-3.5 bg-slate-100 rounded-full w-5/6" />
              <div className="h-3.5 bg-slate-200/60 rounded-full w-11/12" />

              {/* Clean Box */}
              <div className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200 space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-bold text-slate-800">AI Generated Preview</span>
                  <span className="text-[11px] text-slate-500 font-medium">Ready</span>
                </div>
                <div className="h-2.5 bg-slate-200 rounded-full w-4/5" />
                <div className="h-2.5 bg-slate-200/60 rounded-full w-2/3" />
              </div>

              <div className="h-3.5 bg-slate-100 rounded-full w-4/5" />
              <div className="h-3.5 bg-slate-200/60 rounded-full w-11/12" />
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between pt-3.5 border-t border-slate-100 relative z-10">
              <div className="h-2.5 bg-slate-200 rounded-full w-28" />
              <span className="text-xs font-bold text-slate-600">Export Ready</span>
            </div>
          </>
        );
    }
  };

  return (
    <div className="relative w-full max-w-[500px] min-h-[520px] sm:min-h-[560px] flex items-center justify-center select-none">

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* DENSE EXTERNAL TORCH / SPOTLIGHT ILLUMINATION (OUTSIDE)     */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="absolute inset-0 pointer-events-none flex items-center justify-center -z-20">
        <div
          className={`w-[420px] h-[480px] sm:w-[480px] sm:h-[540px] rounded-full blur-[80px] bg-gradient-to-tr ${activeTorch.beam} transition-all duration-1000`}
        />
      </div>

      {/* ═══════════════════════════════════════════════════════ */}
      {/* 3D FLIPPING DOCUMENT CONTAINER (STATIONARY IN PLACE)    */}
      {/* ═══════════════════════════════════════════════════════ */}
      <div className="relative flex items-center justify-center" style={{ perspective: 1600 }}>

        {/* ── Intense Outer Rim Torch Halo (Hugging the Card Borders) ── */}
        <div
          className="absolute -inset-4 sm:-inset-5 rounded-[36px] blur-xl transition-all duration-1000 -z-10 pointer-events-none"
          style={{
            background: `radial-gradient(circle at center, ${activeTorch.rimGlow} 0%, transparent 70%)`,
          }}
        />

        {/* ── Main 3D Card (Fixed Stationary Dimensions, Rotates Forward strictly on center Y axis) ── */}
        <motion.div
          animate={{
            rotateY: rotationY,
          }}
          onAnimationComplete={handleAnimationComplete}
          transition={{
            duration: 0.95,
            ease: [0.35, 0, 0.25, 1],
          }}
          className="w-[330px] h-[480px] sm:w-[360px] sm:h-[520px] md:w-[380px] md:h-[540px] relative"
          style={{
            transformStyle: 'preserve-3d',
            transformOrigin: 'center center',
            filter: `drop-shadow(${activeTorch.shadow})`,
          }}
        >

          {/* ══════════════════════════════════════════════════════ */}
          {/* FRONT FACE (0°, 360°, 720°...)                         */}
          {/* ══════════════════════════════════════════════════════ */}
          <div
            className="absolute top-0 left-0 w-full h-full rounded-[28px] bg-white p-6 sm:p-7 border border-slate-200/90 flex flex-col justify-between overflow-hidden shadow-2xs"
            style={{
              backfaceVisibility: 'hidden',
              WebkitBackfaceVisibility: 'hidden',
              transform: 'rotateY(0deg) translateZ(1px)',
            }}
          >
            {renderDocumentContent(frontDoc)}
          </div>

          {/* ══════════════════════════════════════════════════════ */}
          {/* BACK FACE (180°, 540°, 900°...)                        */}
          {/* ══════════════════════════════════════════════════════ */}
          <div
            className="absolute top-0 left-0 w-full h-full rounded-[28px] bg-white p-6 sm:p-7 border border-slate-200/90 flex flex-col justify-between overflow-hidden shadow-2xs"
            style={{
              backfaceVisibility: 'hidden',
              WebkitBackfaceVisibility: 'hidden',
              transform: 'rotateY(180deg) translateZ(1px)',
            }}
          >
            {renderDocumentContent(backDoc)}
          </div>

        </motion.div>

      </div>

    </div>
  );
};
