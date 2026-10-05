import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, useInView, AnimatePresence } from 'framer-motion';
import { AuthProvider, useAuth } from './context/AuthContext';
import { safeFetchJson, API_URL, getAuthHeaders, AUTH_EXPIRED_EVENT } from './utils/api';
import { Login } from './components/Auth/Login';
import { Register } from './components/Auth/Register';
import { UploadZone } from './components/Dashboard/UploadZone';
import { DocumentList } from './components/Dashboard/DocumentList';
import { DocumentListSkeleton } from './components/Editor/EditorSkeletons';
import { DocumentWorkspace } from './components/Editor/DocumentWorkspace';
import { downloadDocument } from './utils/download';
import logo from './assets/logo.png';
import loadingEffect from './assets/laoding_effect.png';
import FloatingOrbs from './components/FloatingOrbs';
import { DynamicMorphingPipeline } from './components/Hero/DynamicMorphingPipeline';
import {
  Sparkles, FileText, ArrowRight, Play, LogOut,
  Home, Quote, Bold, Italic, Underline, Pen, Send, MessagesSquare, Image,
  BarChart2, Star, FileEdit, Brain, Lightbulb, Download, Upload, Zap, CheckCircle2,
  Shield, Globe, Search, Replace, Palette, Languages, BookOpen, HelpCircle,
  CreditCard, ExternalLink, MessageCircle, Globe as GlobeIcon, Mail, ChevronRight, Users, Clock,
  Target, Layers, MousePointerClick, Trash2, AlertCircle, FolderOpen, Activity
} from 'lucide-react';

/* ─── Scroll Reveal Wrapper ─── */
const ScrollReveal = ({ children, delay = 0, direction = 'up', className = '' }) => {
  const variants = {
    up:    { hidden: { opacity: 0, y: 60 },  visible: { opacity: 1, y: 0 } },
    down:  { hidden: { opacity: 0, y: -60 }, visible: { opacity: 1, y: 0 } },
    left:  { hidden: { opacity: 0, x: -60 }, visible: { opacity: 1, x: 0 } },
    right: { hidden: { opacity: 0, x: 60 },  visible: { opacity: 1, x: 0 } },
    scale: { hidden: { opacity: 0, scale: 0.8 }, visible: { opacity: 1, scale: 1 } },
    none:  { hidden: { opacity: 0 }, visible: { opacity: 1 } },
  };
  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
      variants={variants[direction]}
      className={className}
    >
      {children}
    </motion.div>
  );
};

/* ─── Animated Counter Hook ─── */
const useCountUp = (end, duration = 2000) => {
  const [count, setCount] = useState(0);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.5 });
  const hasAnimated = useRef(false);

  useEffect(() => {
    if (!isInView || hasAnimated.current) return;
    hasAnimated.current = true;
    const startTime = performance.now();
    const animate = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(eased * end));
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [isInView, end, duration]);

  return { count, ref };
};

/* ─── Stat Counter Component ─── */
const StatCounter = ({ value, suffix = '', label, icon: Icon }) => {
  const { count, ref } = useCountUp(value);
  return (
    <motion.div
      ref={ref}
      whileHover={{ y: -4, scale: 1.02 }}
      className="flex flex-col items-center gap-2 px-6 py-5"
    >
      <div className="w-12 h-12 rounded-2xl bg-brand-50 border border-brand-100 flex items-center justify-center mb-1">
        <Icon className="w-6 h-6 text-brand-600" />
      </div>
      <span className="text-3xl sm:text-4xl font-extrabold text-ink tabular-nums tracking-tight">
        {count.toLocaleString()}{suffix}
      </span>
      <span className="text-sm text-secondary font-medium">{label}</span>
    </motion.div>
  );
};

const LandingPage = ({ onNavigate }) => {
  const { user } = useAuth();
  const featurePills = [
    { 
      icon: Zap, 
      label: 'Edit Instantly', 
      detail: 'DOCX & PDF Engine',
      gradient: 'from-blue-500/10 via-indigo-500/5 to-transparent',
      border: 'border-blue-200/80 hover:border-blue-400',
      iconColor: 'text-blue-600',
      iconBg: 'bg-blue-50'
    },
    { 
      icon: Brain, 
      label: 'AI Understands', 
      detail: '24 Natural Intents',
      gradient: 'from-purple-500/10 via-indigo-500/5 to-transparent',
      border: 'border-purple-200/80 hover:border-purple-400',
      iconColor: 'text-purple-600',
      iconBg: 'bg-purple-50'
    },
    { 
      icon: Sparkles, 
      label: 'Smart Suggestions', 
      detail: 'Contextual AI Tuning',
      gradient: 'from-amber-500/10 via-orange-500/5 to-transparent',
      border: 'border-amber-200/80 hover:border-amber-400',
      iconColor: 'text-amber-600',
      iconBg: 'bg-amber-50'
    },
    { 
      icon: Shield, 
      label: 'Zero Format Loss', 
      detail: 'Lossless XML & Styles',
      gradient: 'from-emerald-500/10 via-teal-500/5 to-transparent',
      border: 'border-emerald-200/80 hover:border-emerald-400',
      iconColor: 'text-emerald-600',
      iconBg: 'bg-emerald-50'
    },
  ];

  // AI Showcase tab state
  const [activeAiTab, setActiveAiTab] = useState(0);
  const aiCapabilities = [
    { icon: Search, label: 'Find & Replace', desc: 'Smart find-and-replace across entire documents, including table cells. Case-sensitive matching with full report of changes made.', color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-100' },
    { icon: Brain, label: 'Summarization', desc: 'Generate concise, intelligent summaries of any document. Perfect for research papers, reports, and lengthy contracts.', color: 'text-purple-600', bg: 'bg-purple-50', border: 'border-purple-100' },
    { icon: Languages, label: 'Translation', desc: 'Translate documents across multiple languages while preserving formatting, structure, and document integrity.', color: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-100' },
    { icon: BookOpen, label: 'Study Notes', desc: 'Automatically generate structured study notes, flashcards, and key takeaways from academic documents.', color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-100' },
    { icon: HelpCircle, label: 'MCQ Generation', desc: 'Create multiple-choice questions from document content — ideal for educators, trainers, and self-study preparation.', color: 'text-rose-600', bg: 'bg-rose-50', border: 'border-rose-100' },
    { icon: Target, label: 'Keyword Extraction', desc: 'Extract critical keywords, phrases, and entities from your documents for indexing, tagging, and quick reference.', color: 'text-indigo-600', bg: 'bg-indigo-50', border: 'border-indigo-100' },
  ];

  // Features data
  const features = [
    { icon: Upload, title: 'Drag & Drop Upload', desc: 'Upload PDF and DOCX files instantly with our intuitive drag-and-drop interface. Supports up to 10 MB per file.', color: 'text-brand-600', bg: 'bg-brand-50', border: 'border-brand-100' },
    { icon: Pen, title: 'Inline Content Editing', desc: 'Edit paragraphs directly within the document view. Paragraph-level precision for DOCX and page-level for PDFs.', color: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-100' },
    { icon: Palette, title: 'Full Styling Control', desc: 'Change fonts, sizes, headers, footers, and swap images — all preserved perfectly in the original file format.', color: 'text-purple-600', bg: 'bg-purple-50', border: 'border-purple-100' },
    { icon: MessagesSquare, title: 'Natural Language AI', desc: 'Type plain-English commands like "replace sales with revenue" and watch AI execute edits automatically.', color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-100' },
    { icon: Shield, title: 'Zero Formatting Loss', desc: 'Built on python-docx and PyMuPDF engines. Your documents keep every style, run, and XML element intact.', color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-100' },
    { icon: Clock, title: 'Edit History Timeline', desc: 'Track every change — uploads, style updates, content edits, and find-replace actions — in a visual timeline.', color: 'text-rose-600', bg: 'bg-rose-50', border: 'border-rose-100' },
  ];

  // How it works steps
  const steps = [
    { num: '01', title: 'Upload Your Document', desc: 'Drag and drop any PDF or DOCX file into RapidDoc. Our engine instantly processes and extracts the content.', icon: Upload },
    { num: '02', title: 'Edit with AI Commands', desc: 'Use natural language to tell RapidDoc what to change. Or manually edit text, fonts, headers, footers, and images.', icon: MessagesSquare },
    { num: '03', title: 'Download & Share', desc: 'Export your edited document in its original format. Zero quality loss, ready for submission or sharing.', icon: Download },
  ];

  // Testimonials
  const testimonials = [
    { text: "RapidDoc has completely transformed our document workflow. The AI understands exactly what I need — I just type a command and it's done.", name: 'Priya Sharma', role: 'Research Associate', rating: 5 },
    { text: "The find-and-replace across table cells is a game changer. What used to take me hours now takes seconds. Absolutely love this tool.", name: 'Arjun Patel', role: 'Data Analyst', rating: 5 },
    { text: "As a professor, I use RapidDoc to edit exam papers and generate MCQs. The zero-formatting-loss feature means my documents always look perfect.", name: 'Dr. Meera Joshi', role: 'University Professor', rating: 5 },
  ];

  return (
    <div className="w-full min-h-screen bg-white text-ink relative overflow-x-clip">
      {/* Dynamic Animated Floating Canvas Background across Entire Page */}
      <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <FloatingOrbs />
      </div>

      {/* Background decorations — Clean & Elegant */}
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">
        {/* Soft radial gradients */}
        <div className="absolute inset-0 bg-[radial-gradient(at_18%_22%,rgba(54,92,255,0.07)_0px,transparent_50%),radial-gradient(at_85%_12%,rgba(54,92,255,0.05)_0px,transparent_45%),radial-gradient(at_72%_88%,rgba(139,92,246,0.04)_0px,transparent_50%)]" />
        {/* Soft blurred ambient glows */}
        <motion.div 
          animate={{ scale: [1, 1.1, 1], opacity: [0.3, 0.5, 0.3] }}
          transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute top-[-18%] left-[-12%] w-[620px] h-[620px] bg-brand-600/10 rounded-full blur-[120px]" 
        />
        <motion.div 
          animate={{ scale: [1, 1.15, 1], opacity: [0.25, 0.5, 0.25] }}
          transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
          className="absolute bottom-[-22%] right-[-15%] w-[720px] h-[720px] bg-indigo-400/10 rounded-full blur-[140px]" 
        />
        {/* Subtle decorative curved lines */}
        <svg className="absolute inset-0 w-full h-full opacity-[0.05]" viewBox="0 0 1440 900" fill="none" preserveAspectRatio="xMidYMid slice">
          <path d="M-50 180 C 300 40, 620 320, 900 180 S 1400 60, 1560 220" stroke="#365CFF" strokeWidth="2" />
          <path d="M-50 700 C 320 560, 700 820, 1050 660 S 1420 540, 1560 640" stroke="#365CFF" strokeWidth="2" />
        </svg>
      </div>

      {/* ═══════════════════════════════════════════════════ */}
      {/* FIXED TRANSPARENT GLASS NAVBAR (PINNED AT THE TOP)  */}
      {/* ═══════════════════════════════════════════════════ */}
      <nav className="fixed top-0 left-0 right-0 bg-white/25 backdrop-blur-2xl border-b border-white/40 shadow-[0_4px_30px_rgba(0,0,0,0.03)] z-50 transition-all duration-300">
        <div className="w-full px-4 sm:px-6 lg:px-8 h-[76px] flex items-center justify-between">
          <button
            onClick={() => onNavigate('landing', 'hero')}
            className="shrink-0 cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95 flex items-center gap-2.5 group"
            title="Go to Home"
            aria-label="RapidDoc Home"
          >
            <img src={loadingEffect} alt="RapidDoc Logo" className="w-[50px] h-[50px] sm:w-[56px] sm:h-[56px] object-contain drop-shadow-xs" />
            <span className="text-xl sm:text-2xl font-black tracking-tight text-slate-900 group-hover:text-brand-600 transition-colors select-none">
              Rapid<span className="text-brand-600">Doc</span>
            </span>
          </button>

          <div className="hidden md:flex items-center gap-1.5 p-1.5 rounded-2xl bg-white/50 backdrop-blur-md border border-slate-200/50 shadow-2xs">
            <button 
              onClick={() => onNavigate('landing', 'hero')} 
              className="px-4 py-2 rounded-xl text-sm font-bold text-slate-700 hover:text-brand-600 hover:bg-white/80 transition-all duration-200 cursor-pointer"
            >
              Home
            </button>
            <button 
              onClick={() => onNavigate('landing', 'features')} 
              className="px-4 py-2 rounded-xl text-sm font-bold text-slate-700 hover:text-brand-600 hover:bg-white/80 transition-all duration-200 cursor-pointer"
            >
              Features
            </button>
            <button 
              onClick={() => onNavigate('landing', 'how')} 
              className="px-4 py-2 rounded-xl text-sm font-bold text-slate-700 hover:text-brand-600 hover:bg-white/80 transition-all duration-200 cursor-pointer"
            >
              How It Works
            </button>
            <button 
              onClick={() => onNavigate('landing', 'ai')} 
              className="px-4 py-2 rounded-xl text-sm font-bold text-slate-700 hover:text-brand-600 hover:bg-white/80 transition-all duration-200 cursor-pointer"
            >
              AI Engine
            </button>
          </div>

          <div className="flex items-center gap-3">
            {user ? (
              <button
                onClick={() => onNavigate('dashboard')}
                className="h-[44px] px-6 rounded-xl bg-gradient-to-r from-brand-600 via-indigo-600 to-brand-700 hover:from-brand-500 hover:to-brand-600 text-white font-extrabold text-sm shadow-[0_4px_16px_rgba(54,92,255,0.35)] hover:shadow-[0_6px_22px_rgba(54,92,255,0.48)] hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 cursor-pointer flex items-center gap-2"
              >
                <span>Dashboard</span>
                <ArrowRight className="w-4 h-4 text-white/90" />
              </button>
            ) : (
              <>
                <button
                  onClick={() => onNavigate('login')}
                  className="h-[44px] px-6 rounded-xl bg-white/90 hover:bg-white text-slate-800 hover:text-brand-600 font-bold text-sm border border-slate-300/80 hover:border-brand-500 shadow-2xs hover:shadow-xs hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 cursor-pointer"
                >
                  Login
                </button>
                <button
                  onClick={() => onNavigate('register')}
                  className="group h-[44px] px-6 rounded-xl bg-gradient-to-r from-brand-600 via-indigo-600 to-brand-700 hover:from-brand-500 hover:to-brand-600 text-white font-extrabold text-sm shadow-[0_4px_16px_rgba(54,92,255,0.35)] hover:shadow-[0_6px_22px_rgba(54,92,255,0.48)] hover:scale-[1.03] active:scale-[0.98] transition-all duration-200 cursor-pointer flex items-center gap-2"
                >
                  <span>Get Started</span>
                  <ArrowRight className="w-4 h-4 text-white/90 group-hover:translate-x-0.5 transition-transform" />
                </button>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════════════ */}
      {/* SECTION 1: HERO                                    */}
      {/* ═══════════════════════════════════════════════════ */}
      <section id="hero" className="max-w-[1480px] mx-auto w-full px-6 lg:pl-6 lg:pr-10 min-h-[calc(100vh-76px)] grid lg:grid-cols-[1.2fr_1fr] gap-8 lg:gap-12 items-center pt-24 pb-6 sm:pt-[100px] sm:pb-8 z-10 scroll-mt-24">
        {/* Left Hero */}
        <motion.div 
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col items-start text-left w-full pt-5 sm:pt-8"
        >
          {/* Heading */}
          <h1 className="text-[32px] sm:text-[40px] lg:text-[46px] font-bold text-ink leading-[1.16] tracking-tight mb-4">
            Work Smarter, Not Harder.
            <br />
            <span className="font-script text-brand-600 relative inline-block mt-1">
              Let RapidDoc Handle It.
              <svg className="absolute left-0 -bottom-3 w-full h-[16px]" viewBox="0 0 420 20" fill="none" preserveAspectRatio="none" aria-hidden="true">
                <path d="M6 15 C 90 4, 240 3, 414 11" stroke="#365CFF" strokeWidth="7" strokeLinecap="round" opacity="0.45" />
                <path d="M10 17 C 120 8, 260 7, 410 13" stroke="#365CFF" strokeWidth="3" strokeLinecap="round" opacity="0.25" />
              </svg>
            </span>
          </h1>

          {/* Description */}
          <p className="text-[17px] sm:text-[18px] lg:text-[19px] leading-[1.6] text-[#4B5563] mb-5 w-full">
            Edit, <span className="text-brand-600 font-semibold">understand</span>, and{' '}
            <span className="text-brand-600 font-semibold">transform</span> your documents using the power of AI — with precision styling, smart summarization, and zero format loss.
          </p>

          {/* Creative 2x2 Capability Grid — Covering the left part whole */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5 w-full">
            {featurePills.map(({ icon: Icon, label, detail, gradient, border, iconColor, iconBg }, index) => (
              <motion.div 
                key={label}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.15 + index * 0.08 }}
                whileHover={{ scale: 1.02, y: -2 }}
                className={`group flex items-center gap-3 p-3 rounded-2xl bg-gradient-to-r ${gradient} bg-white/90 backdrop-blur-md border ${border} shadow-2xs hover:shadow-card transition-all duration-300 cursor-default w-full`}
              >
                <div className={`w-10 h-10 rounded-xl ${iconBg} ${iconColor} flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform duration-300`}>
                  <Icon className="w-5 h-5 stroke-[2.2]" />
                </div>
                <div className="text-left min-w-0 flex-1">
                  <div className="text-xs font-extrabold text-ink group-hover:text-brand-600 transition-colors truncate">{label}</div>
                  <div className="text-[10px] text-secondary font-medium truncate">{detail}</div>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Creative CTA Action Hub */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4 w-full">
            {/* Primary Gradient CTA */}
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => onNavigate(user ? 'dashboard' : 'register')}
              className="group relative overflow-hidden h-[50px] w-full px-6 rounded-2xl bg-gradient-to-r from-brand-600 via-indigo-600 to-brand-700 hover:from-brand-500 hover:to-brand-600 text-white font-extrabold text-sm sm:text-base shadow-[0_8px_25px_rgba(54,92,255,0.4)] hover:shadow-[0_12px_30px_rgba(54,92,255,0.5)] transition-all flex items-center justify-center gap-2.5 cursor-pointer"
            >
              <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-1000 bg-gradient-to-r from-transparent via-white/25 to-transparent pointer-events-none" />
              <Sparkles className="w-4 h-4 text-brand-200" />
              <span>{user ? 'Go to Dashboard' : 'Start for Free'}</span>
              <ArrowRight className="w-4 h-4 text-white group-hover:translate-x-1 transition-transform" />
            </motion.button>

            {/* Secondary Glassmorphic Upload / Workspace CTA */}
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => onNavigate(user ? 'dashboard' : 'register')}
              className="h-[50px] w-full px-6 rounded-2xl bg-white text-slate-800 hover:text-brand-600 hover:bg-brand-50/50 border-2 border-slate-200/90 hover:border-brand-500 font-extrabold text-sm sm:text-base flex items-center justify-center gap-2.5 shadow-2xs hover:shadow-card transition-all cursor-pointer"
              title="Upload a document and edit it with AI"
            >
              <div className="w-7 h-7 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center">
                <Upload className="w-4 h-4 stroke-[2.5]" />
              </div>
              <span>{user ? 'Open Your Documents' : 'Upload Document'}</span>
            </motion.button>
          </div>

          {/* Testimonial Card — Covering the left part whole */}
          <motion.div 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
            className="p-4 bg-white/95 backdrop-blur-sm rounded-2xl shadow-floating border border-borderline/60 w-full mt-3"
          >
            <Quote className="w-5 h-5 text-brand-600 mb-1.5" />
            <p className="text-[13px] text-ink/80 font-medium leading-relaxed mb-2.5">
              "RapidDoc has completely changed the way we work with documents. It's like having an
              AI assistant right inside our editor."
            </p>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center">
                <div className="flex -space-x-2">
                  <div className="w-5 h-5 rounded-full bg-slate-300 border-2 border-white"></div>
                  <div className="w-5 h-5 rounded-full bg-slate-400 border-2 border-white"></div>
                  <div className="w-5 h-5 rounded-full bg-blue-300 border-2 border-white"></div>
                  <div className="w-5 h-5 rounded-full bg-purple-300 border-2 border-white"></div>
                </div>
                <span className="ml-2.5 text-[11px] text-secondary font-bold">Loved by 1,000+ users worldwide</span>
              </div>
              <div className="flex gap-0.5 text-amber-400 shrink-0">
                {[0, 1, 2, 3, 4].map((i) => (
                  <Star key={i} className="w-2.5 h-2.5 fill-amber-400" />
                ))}
              </div>
            </div>
          </motion.div>
        </motion.div>

        {/* Right Hero — Dynamic 3D Morphing Document Pipeline Stage */}
        <motion.div 
          initial={{ opacity: 0, x: 30, scale: 0.95 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
          className="relative flex items-center justify-center w-full"
        >
          <DynamicMorphingPipeline />
        </motion.div>
      </section>

      {/* ═══════════════════════════════════════════════════ */}
      {/* SECTION 3: FEATURES GRID                            */}
      {/* ═══════════════════════════════════════════════════ */}
      <section id="features" className="relative z-10 py-24 scroll-mt-20">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
          {/* Section Header */}
          <ScrollReveal>
            <div className="text-center mb-16">
              <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-brand-50/90 border border-brand-100 text-brand-600 text-xs font-bold uppercase tracking-wider mb-4">
                <Layers className="w-3.5 h-3.5" />
                Features
              </span>
              <h2 className="text-3xl sm:text-4xl lg:text-[44px] font-bold text-ink tracking-tight mb-4">
                Everything You Need to{' '}
                <span className="text-brand-600">Master Your Documents</span>
              </h2>
              <p className="text-lg text-secondary max-w-2xl mx-auto leading-relaxed">
                From intelligent editing to complete style control — RapidDoc gives you the tools to work faster and smarter.
              </p>
            </div>
          </ScrollReveal>

          {/* Feature Cards */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, index) => (
              <ScrollReveal key={feature.title} delay={index * 0.1} direction="up">
                <motion.div
                  whileHover={{ y: -8, scale: 1.02 }}
                  transition={{ duration: 0.3 }}
                  className="group p-7 bg-white/75 backdrop-blur-md rounded-3xl border border-white/80 shadow-card hover:shadow-card-hover transition-all duration-300 h-full"
                >
                  <div className={`w-14 h-14 rounded-2xl ${feature.bg} border ${feature.border} flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300`}>
                    <feature.icon className={`w-7 h-7 ${feature.color}`} />
                  </div>
                  <h3 className="text-lg font-bold text-ink mb-2">{feature.title}</h3>
                  <p className="text-sm text-secondary leading-relaxed">{feature.desc}</p>
                </motion.div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════ */}
      {/* SECTION 4: HOW IT WORKS                            */}
      {/* ═══════════════════════════════════════════════════ */}
      <section id="how" className="relative z-10 py-24 bg-transparent scroll-mt-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          {/* Section Header */}
          <ScrollReveal>
            <div className="text-center mb-16">
              <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-50/90 border border-emerald-100 text-emerald-600 text-xs font-bold uppercase tracking-wider mb-4">
                <MousePointerClick className="w-3.5 h-3.5" />
                How It Works
              </span>
              <h2 className="text-3xl sm:text-4xl lg:text-[44px] font-bold text-ink tracking-tight mb-4">
                Three Simple Steps to{' '}
                <span className="text-brand-600">Document Intelligence</span>
              </h2>
              <p className="text-lg text-secondary max-w-2xl mx-auto leading-relaxed">
                No complicated setup. No learning curve. Upload, command, download.
              </p>
            </div>
          </ScrollReveal>

          {/* Steps */}
          <div className="relative">
            <div className="grid lg:grid-cols-3 gap-8 lg:gap-12">
              {steps.map((step, index) => (
                <ScrollReveal key={step.num} delay={index * 0.15} direction="up">
                  <div className="relative flex flex-col items-center text-center p-6 rounded-3xl bg-white/75 backdrop-blur-md border border-white/80 shadow-card hover:shadow-card-hover transition-all">
                    {/* Step Number Circle */}
                    <motion.div
                      whileHover={{ scale: 1.1, rotate: 5 }}
                      className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-extrabold text-xl shadow-soft-blue mb-6 z-10"
                    >
                      {step.num}
                      <div className="absolute -inset-2 rounded-3xl bg-brand-400/20 blur-lg -z-10" />
                    </motion.div>
                    {/* Icon */}
                    <div className="w-14 h-14 rounded-2xl bg-brand-50 border border-brand-100 flex items-center justify-center mb-4">
                      <step.icon className="w-7 h-7 text-brand-600" />
                    </div>
                    <h3 className="text-xl font-bold text-ink mb-3">{step.title}</h3>
                    <p className="text-sm text-secondary leading-relaxed max-w-xs">{step.desc}</p>

                    {/* Sleek Step Direction Arrow Connector — Centered exactly in the middle between both cards */}
                    {index < steps.length - 1 && (
                      <div className="hidden lg:flex absolute left-[calc(100%+16px)] lg:left-[calc(100%+24px)] top-1/2 -translate-x-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-white border border-slate-200/90 shadow-card items-center justify-center text-brand-600 pointer-events-none">
                        <ArrowRight className="w-4 h-4 stroke-[2.5]" />
                      </div>
                    )}
                  </div>
                </ScrollReveal>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════ */}
      {/* SECTION 5: AI CAPABILITIES SHOWCASE                */}
      {/* ═══════════════════════════════════════════════════ */}
      <section id="ai" className="relative z-10 py-24 scroll-mt-20">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          {/* Section Header */}
          <ScrollReveal>
            <div className="text-center mb-16">
              <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-purple-50/90 border border-purple-100 text-purple-600 text-xs font-bold uppercase tracking-wider mb-4">
                <Sparkles className="w-3.5 h-3.5" />
                AI Engine
              </span>
              <h2 className="text-3xl sm:text-4xl lg:text-[44px] font-bold text-ink tracking-tight mb-4">
                Powered by{' '}
                <span className="bg-gradient-to-r from-brand-600 via-purple-600 to-indigo-600 bg-clip-text text-transparent">
                  Intelligent AI
                </span>
              </h2>
              <p className="text-lg text-secondary max-w-2xl mx-auto leading-relaxed">
                RapidDoc's AI pipeline understands your documents deeply — from simple text edits to complex content generation.
              </p>
            </div>
          </ScrollReveal>

          {/* AI Tabs */}
          <ScrollReveal delay={0.1}>
            <div className="bg-white/80 backdrop-blur-md rounded-3xl border border-white/80 shadow-floating overflow-hidden">
              {/* Tab Navigation */}
              <div className="flex flex-wrap border-b border-borderline/40 px-4 pt-4 gap-1">
                {aiCapabilities.map((cap, index) => (
                  <button
                    key={cap.label}
                    onClick={() => setActiveAiTab(index)}
                    className={`flex items-center gap-2 px-4 py-3 rounded-t-xl text-sm font-semibold transition-all duration-300 ${
                      activeAiTab === index
                        ? 'bg-brand-50 text-brand-600 border border-borderline/60 border-b-white -mb-px'
                        : 'text-secondary hover:text-ink hover:bg-slate-50'
                    }`}
                  >
                    <cap.icon className="w-4 h-4" />
                    <span className="hidden sm:inline">{cap.label}</span>
                  </button>
                ))}
              </div>

              {/* Tab Content */}
              <motion.div
                key={activeAiTab}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="p-8 lg:p-12"
              >
                <div className="flex flex-col lg:flex-row items-start gap-8">
                  <div className={`w-20 h-20 rounded-3xl ${aiCapabilities[activeAiTab].bg} border ${aiCapabilities[activeAiTab].border} flex items-center justify-center shrink-0`}>
                    {React.createElement(aiCapabilities[activeAiTab].icon, {
                      className: `w-10 h-10 ${aiCapabilities[activeAiTab].color}`
                    })}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-2xl font-bold text-ink mb-3">{aiCapabilities[activeAiTab].label}</h3>
                    <p className="text-base text-secondary leading-relaxed mb-6">{aiCapabilities[activeAiTab].desc}</p>
                    <div className="flex items-center gap-3">
                      <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 text-xs font-bold">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Available Now
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-50 text-brand-700 text-xs font-bold">
                        <Zap className="w-3.5 h-3.5" />
                        AI-Powered
                      </span>
                    </div>
                  </div>
                </div>
              </motion.div>
            </div>
          </ScrollReveal>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════ */}
      {/* SECTION 6: TESTIMONIALS                            */}
      {/* ═══════════════════════════════════════════════════ */}
      <section id="testimonials" className="relative z-10 py-24 bg-transparent scroll-mt-20">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          {/* Section Header */}
          <ScrollReveal>
            <div className="text-center mb-16">
              <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-amber-50/90 border border-amber-100 text-amber-600 text-xs font-bold uppercase tracking-wider mb-4">
                <Star className="w-3.5 h-3.5 fill-amber-500" />
                Testimonials
              </span>
              <h2 className="text-3xl sm:text-4xl lg:text-[44px] font-bold text-ink tracking-tight mb-4">
                Loved by{' '}
                <span className="text-brand-600">Students & Professionals</span>
              </h2>
              <p className="text-lg text-secondary max-w-2xl mx-auto leading-relaxed">
                See what our users have to say about their experience with RapidDoc.
              </p>
            </div>
          </ScrollReveal>

          {/* Testimonial Cards */}
          <div className="grid md:grid-cols-3 gap-6">
            {testimonials.map((testimonial, index) => (
              <ScrollReveal key={testimonial.name} delay={index * 0.12} direction="up">
                <motion.div
                  whileHover={{ y: -6 }}
                  className="p-7 bg-white/75 backdrop-blur-md rounded-3xl border border-white/80 shadow-card hover:shadow-card-hover transition-all duration-300 h-full flex flex-col"
                >
                  {/* Stars */}
                  <div className="flex gap-1 mb-4">
                    {Array.from({ length: testimonial.rating }).map((_, i) => (
                      <Star key={i} className="w-4 h-4 text-amber-400 fill-amber-400" />
                    ))}
                  </div>
                  {/* Quote */}
                  <Quote className="w-8 h-8 text-brand-100 mb-3" />
                  <p className="text-sm text-ink/80 leading-relaxed mb-6 flex-1">{testimonial.text}</p>
                  {/* Author */}
                  <div className="flex items-center gap-3 pt-4 border-t border-borderline/40">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-400 to-indigo-500 flex items-center justify-center text-white font-bold text-sm">
                      {testimonial.name.charAt(0)}
                    </div>
                    <div>
                      <div className="text-sm font-bold text-ink">{testimonial.name}</div>
                      <div className="text-xs text-secondary">{testimonial.role}</div>
                    </div>
                  </div>
                </motion.div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════ */}
      {/* SECTION 7: CTA BANNER                              */}
      {/* ═══════════════════════════════════════════════════ */}
      <section className="relative z-10 py-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <ScrollReveal direction="scale">
            <div className="relative overflow-hidden rounded-[32px] bg-gradient-to-b from-[#F2F6FF] to-[#EBF2FF] border border-[#D5E3FC] p-12 sm:p-14 lg:p-16 text-center shadow-[0_20px_60px_-15px_rgba(54,92,255,0.07)]">
              {/* Subtle ambient light accents */}
              <div className="absolute top-0 right-0 w-80 h-80 bg-blue-400/10 rounded-full blur-3xl pointer-events-none -translate-y-1/2 translate-x-1/2" />
              <div className="absolute bottom-0 left-0 w-80 h-80 bg-indigo-400/10 rounded-full blur-3xl pointer-events-none translate-y-1/2 -translate-x-1/2" />

              <div className="relative z-10">
                <h2 className="text-4xl sm:text-5xl lg:text-[56px] font-black text-slate-900 mb-4 tracking-tight leading-[1.12]">
                  Ready to Transform<br className="hidden sm:inline" /> Your <span className="text-[#1D61FF]">Documents?</span>
                </h2>
                <p className="text-base sm:text-lg text-slate-600 max-w-xl mx-auto mb-8 leading-relaxed">
                  Join thousands of users who are already working smarter with RapidDoc's AI-powered document intelligence.
                </p>
                <div className="flex flex-wrap items-center justify-center gap-4">
                  <motion.button
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => onNavigate(user ? 'dashboard' : 'register')}
                    className="h-[50px] sm:h-[52px] px-8 rounded-2xl bg-[#1D61FF] hover:bg-[#1554E6] text-white font-extrabold text-sm sm:text-base shadow-[0_4px_16px_rgba(29,97,255,0.25)] hover:shadow-[0_6px_22px_rgba(29,97,255,0.38)] flex items-center gap-2.5 transition-all duration-200 cursor-pointer"
                  >
                    <span>{user ? 'Go to Dashboard' : 'Get Started'}</span>
                    <ArrowRight className="w-4 h-4 text-white" />
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => { const el = document.getElementById('features'); if (el) el.scrollIntoView({ behavior: 'smooth' }); }}
                    className="h-[50px] sm:h-[52px] px-8 rounded-2xl bg-white/60 hover:bg-white border border-[#1D61FF] text-[#1D61FF] hover:text-[#1554E6] font-extrabold text-sm sm:text-base flex items-center gap-2.5 shadow-2xs hover:shadow-xs transition-all duration-200 cursor-pointer"
                  >
                    <span>Explore Features</span>
                    <ArrowRight className="w-4 h-4 text-[#1D61FF]" />
                  </motion.button>
                </div>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════ */}
      {/* FOOTER                                             */}
      {/* ═══════════════════════════════════════════════════ */}
      <footer className="relative z-10 bg-white border-t border-slate-200/70 overflow-hidden">
        {/* Soft background ambient glow accents */}
        <div className="absolute top-0 left-0 w-80 h-80 bg-blue-500/5 rounded-full blur-3xl pointer-events-none -translate-x-1/2 -translate-y-1/2" />
        <div className="absolute bottom-0 right-0 w-80 h-80 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none translate-x-1/4 translate-y-1/4" />

        <div className="relative max-w-6xl mx-auto px-6 sm:px-8 lg:px-10 pt-16 pb-10">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10 lg:gap-8 mb-12">
            {/* Brand */}
            <div className="sm:col-span-2 lg:col-span-1">
              <div className="flex items-center gap-2.5 mb-4">
                <img src={loadingEffect} alt="RapidDoc Logo" className="w-8 h-8 sm:w-9 sm:h-9 object-contain drop-shadow-xs" />
                <span className="text-xl sm:text-2xl font-black tracking-tight text-slate-900 select-none">
                  Rapid<span className="text-[#365CFF]">Doc</span>
                </span>
              </div>
              <p className="text-sm text-slate-500 leading-relaxed max-w-xs">
                AI-Powered Document Intelligence & Editing Platform. Upload, edit, and transform your documents with the power of AI.
              </p>
            </div>

            {/* Links: Product */}
            <div>
              <h4 className="text-xs font-black text-slate-900 uppercase tracking-wider">PRODUCT</h4>
              <div className="w-6 h-[2.5px] bg-[#365CFF] rounded-full mt-1.5 mb-4"></div>
              <ul className="space-y-3">
                <li><a href="#features" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Features</a></li>
                <li><a href="#how" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">How It Works</a></li>
                <li><a href="#ai" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">AI Engine</a></li>
                <li><a href="#testimonials" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Testimonials</a></li>
              </ul>
            </div>

            {/* Links: Resources */}
            <div>
              <h4 className="text-xs font-black text-slate-900 uppercase tracking-wider">RESOURCES</h4>
              <div className="w-6 h-[2.5px] bg-[#365CFF] rounded-full mt-1.5 mb-4"></div>
              <ul className="space-y-3">
                <li><a href="#" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Documentation</a></li>
                <li><a href="#" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">API Reference</a></li>
                <li><a href="#help" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Help Center</a></li>
                <li><a href="#" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Changelog</a></li>
              </ul>
            </div>

            {/* Links: Legal */}
            <div>
              <h4 className="text-xs font-black text-slate-900 uppercase tracking-wider">LEGAL</h4>
              <div className="w-6 h-[2.5px] bg-[#365CFF] rounded-full mt-1.5 mb-4"></div>
              <ul className="space-y-3">
                <li><a href="#privacy" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Privacy Policy</a></li>
                <li><a href="#terms" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Terms of Service</a></li>
                <li><a href="#" className="text-sm text-slate-600 hover:text-[#365CFF] transition-colors font-medium">Cookie Policy</a></li>
              </ul>
            </div>
          </div>

          {/* Bottom Bar */}
          <div className="flex flex-col sm:flex-row justify-between items-center pt-8 border-t border-slate-200/80 gap-4">
            <span className="text-xs sm:text-sm text-slate-500 font-medium">
              © 2026 RapidDoc. All rights reserved.
            </span>
            <div className="flex items-center gap-3">
              <a 
                href="https://github.com/Vaghasiya-Jemit-kanaiyalal/RapidDoc" 
                target="_blank" 
                rel="noopener noreferrer" 
                className="w-10 h-10 rounded-xl bg-slate-100/80 hover:bg-slate-200/80 border border-slate-200/70 flex items-center justify-center text-slate-500 hover:text-[#365CFF] hover:border-blue-200 shadow-2xs hover:scale-105 active:scale-95 transition-all duration-200"
                aria-label="GitHub Repository"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
              <a 
                href="#" 
                className="w-10 h-10 rounded-xl bg-slate-100/80 hover:bg-slate-200/80 border border-slate-200/70 flex items-center justify-center text-slate-500 hover:text-[#365CFF] hover:border-blue-200 shadow-2xs hover:scale-105 active:scale-95 transition-all duration-200"
                aria-label="Community Discussions"
              >
                <MessageCircle className="w-4 h-4" />
              </a>
              <a 
                href="#" 
                className="w-10 h-10 rounded-xl bg-slate-100/80 hover:bg-slate-200/80 border border-slate-200/70 flex items-center justify-center text-slate-500 hover:text-[#365CFF] hover:border-blue-200 shadow-2xs hover:scale-105 active:scale-95 transition-all duration-200"
                aria-label="Global Network"
              >
                <GlobeIcon className="w-4 h-4" />
              </a>
              <a 
                href="mailto:support@rapiddoc.ai" 
                className="w-10 h-10 rounded-xl bg-slate-100/80 hover:bg-slate-200/80 border border-slate-200/70 flex items-center justify-center text-slate-500 hover:text-[#365CFF] hover:border-blue-200 shadow-2xs hover:scale-105 active:scale-95 transition-all duration-200"
                aria-label="Email Support"
              >
                <Mail className="w-4 h-4" />
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

const Dashboard = ({ token, user, onLogout, onSelectDocument, onHome }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);

  const fetchDocuments = async () => {
    try {
      const data = await safeFetchJson(`${API_URL}/documents`, {
        headers: getAuthHeaders()
      });
      setDocuments(data);
    } catch (err) {
      setError(err.message || 'Could not load your documents.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [token]);

  // Direct-open: after upload, immediately open the document in workspace
  const handleUploadSuccess = (newDoc) => {
    setDocuments([newDoc, ...documents]);
    // Jump straight to workspace with the newly uploaded document
    onSelectDocument(newDoc);
  };

  const handleDownload = async (doc) => {
    try {
      await downloadDocument(token, doc.id, doc.name);
    } catch (err) {
      setError(err.message || 'Error downloading document.');
    }
  };

  const handleClearHistory = async () => {
    setClearingHistory(true);
    try {
      const res = await fetch(`${API_URL}/documents/history`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });
      if (!res.ok) {
        throw new Error(res.status === 404
          ? 'Clear history is not available on the server. Restart the backend and try again.'
          : 'Could not clear your document history on the server.');
      }
      setDocuments([]);
    } catch (err) {
      setError(err.message || 'Error clearing document history.');
    } finally {
      setClearingHistory(false);
      setShowClearConfirm(false);
    }
  };

  const activePipelines = documents.filter(d => (d.pipeline_stage || 1) < 4 || d.pipeline_status === 'In Progress');
  const finalizedCount = documents.filter(d => (d.pipeline_stage || 1) === 4 || d.pipeline_status === 'Finalized').length;
  const latestActive = activePipelines[0];

  // Stat card data with brand-consistent colors
  const statCards = [
    {
      label: 'Total Documents',
      value: documents.length,
      icon: FolderOpen,
      gradient: 'from-brand-600 to-indigo-600',
      lightBg: 'bg-brand-50',
      lightBorder: 'border-brand-100',
      textColor: 'text-brand-700',
      accentBar: 'bg-gradient-to-r from-brand-500 to-indigo-500',
    },
    {
      label: 'In Progress',
      value: activePipelines.length,
      icon: Activity,
      gradient: 'from-indigo-600 to-purple-600',
      lightBg: 'bg-indigo-50',
      lightBorder: 'border-indigo-100',
      textColor: 'text-indigo-700',
      accentBar: 'bg-gradient-to-r from-indigo-500 to-purple-500',
    },
    {
      label: 'Finalized',
      value: finalizedCount,
      icon: CheckCircle2,
      gradient: 'from-emerald-500 to-teal-600',
      lightBg: 'bg-emerald-50',
      lightBorder: 'border-emerald-100',
      textColor: 'text-emerald-700',
      accentBar: 'bg-gradient-to-r from-emerald-400 to-teal-500',
    },
  ];

  return (
    <div className="min-h-screen bg-white flex flex-col text-ink font-sans relative">
      {/* Background ambient gradients matching landing page */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute inset-0 bg-[radial-gradient(at_18%_22%,rgba(54,92,255,0.06)_0px,transparent_50%),radial-gradient(at_85%_12%,rgba(54,92,255,0.04)_0px,transparent_45%),radial-gradient(at_72%_88%,rgba(139,92,246,0.03)_0px,transparent_50%)]" />
        <motion.div 
          animate={{ scale: [1, 1.1, 1], opacity: [0.2, 0.35, 0.2] }}
          transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute top-[-15%] left-[-8%] w-[500px] h-[500px] bg-brand-600/8 rounded-full blur-[100px]" 
        />
        <motion.div 
          animate={{ scale: [1, 1.15, 1], opacity: [0.15, 0.3, 0.15] }}
          transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
          className="absolute bottom-[-15%] right-[-10%] w-[550px] h-[550px] bg-indigo-400/8 rounded-full blur-[120px]" 
        />
      </div>

      {/* Header */}
      <header className="bg-white/80 backdrop-blur-xl border-b border-borderline/40 sticky top-0 z-30">
        <div className="w-full px-4 sm:px-6 lg:px-8 h-[72px] flex justify-between items-center">
          <button
            onClick={onHome}
            className="shrink-0 cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95 flex items-center gap-2.5 group"
            title="Go to Home"
            aria-label="RapidDoc Home"
          >
            <img src={loadingEffect} alt="RapidDoc Logo" className="w-[46px] h-[46px] object-contain drop-shadow-xs" />
            <span className="text-xl font-black tracking-tight text-slate-900 group-hover:text-brand-600 transition-colors hidden sm:inline select-none">
              Rapid<span className="text-brand-600">Doc</span>
            </span>
          </button>

          <div className="flex items-center gap-2.5">
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={onHome}
              className="flex items-center gap-1.5 px-3.5 py-2 text-secondary hover:text-brand-600 bg-white border border-borderline/60 hover:border-brand-200 rounded-xl text-xs font-bold transition shadow-2xs cursor-pointer"
              title="Go to Home"
            >
              <Home className="w-3.5 h-3.5" />
              <span>Home</span>
            </motion.button>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-borderline/60 rounded-xl text-xs font-bold text-ink shadow-2xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="max-w-[120px] truncate">{user ? user.name : 'User'}</span>
            </div>
            <motion.button 
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onLogout}
              className="p-2 text-secondary hover:text-red-600 bg-white border border-borderline/60 hover:border-red-200 rounded-xl transition shadow-2xs cursor-pointer"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </motion.button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex-grow space-y-7 relative z-10">
        
        {/* ── Page Title Row with Clear History ── */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 text-left">
          <div>
            <motion.h2 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-3xl font-extrabold text-ink tracking-tight"
            >
              Your Document Hub
            </motion.h2>
            <motion.p 
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 }}
              className="text-sm text-secondary mt-1"
            >
              Upload, edit, and transform your documents with AI-powered intelligence.
            </motion.p>
          </div>

          {/* Clear History Button */}
          {documents.length > 0 && (
            <motion.button
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => setShowClearConfirm(true)}
              className="flex items-center gap-1.5 px-4 py-2 text-secondary hover:text-red-600 bg-white border border-borderline/60 hover:border-red-200 rounded-xl text-xs font-bold transition shadow-2xs cursor-pointer shrink-0"
              title="Clear document history"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear History</span>
            </motion.button>
          )}
        </div>

        {/* ── Glassmorphic Stats Cards ── */}
        <motion.div 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 sm:grid-cols-3 gap-4"
        >
          {statCards.map((card, index) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + index * 0.08 }}
              whileHover={{ y: -4, scale: 1.02 }}
              className={`relative overflow-hidden rounded-2xl bg-white/90 backdrop-blur-md border ${card.lightBorder} shadow-card hover:shadow-card-hover transition-all duration-300 p-5`}
            >
              <div className="flex flex-col">
                <p className="text-[11px] uppercase font-bold text-secondary tracking-wider mb-3.5 text-left">{card.label}</p>
                <div className="flex items-center justify-between">
                  <div className={`w-12 h-12 rounded-2xl ${card.lightBg} border ${card.lightBorder} flex items-center justify-center shrink-0`}>
                    <card.icon className={`w-6 h-6 ${card.textColor}`} />
                  </div>
                  <p className={`text-3xl font-extrabold ${card.textColor} tabular-nums tracking-tight`}>{card.value}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>

        {/* ── Active Pipeline Resume Banner ── */}
        {latestActive && (
          <motion.section 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-gradient-to-r from-brand-600 via-indigo-600 to-brand-700 rounded-2xl p-5 sm:p-6 text-white shadow-soft-blue relative overflow-hidden"
          >
            {/* Background decoration */}
            <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
              <div className="absolute -top-10 -right-10 w-40 h-40 bg-white/10 rounded-full blur-[50px]" />
              <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(white 1px, transparent 1px)', backgroundSize: '20px 20px' }} />
            </div>

            <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="space-y-2 text-left">
                <div className="flex items-center gap-2">
                  <span className="bg-white/20 text-white text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-0.5 rounded-full backdrop-blur-md">
                    Active Pipeline
                  </span>
                  <span className="text-xs text-blue-100 font-bold">
                    Stage {latestActive.pipeline_stage || 1} of 4 ({latestActive.completion_percent || 25}%)
                  </span>
                </div>
                <h3 className="text-lg font-extrabold text-white truncate max-w-md">{latestActive.name}</h3>
                <div className="w-full sm:w-64 bg-white/20 rounded-full h-2 overflow-hidden border border-white/15">
                  <div 
                    className="h-full bg-emerald-400 rounded-full transition-all duration-500" 
                    style={{ width: `${latestActive.completion_percent || 25}%` }}
                  />
                </div>
              </div>

              <motion.button
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.96 }}
                onClick={() => onSelectDocument(latestActive)}
                className="px-5 py-2.5 bg-white text-brand-700 hover:bg-brand-50 font-extrabold rounded-xl text-sm flex items-center gap-2 shadow-lg transition duration-200 shrink-0 cursor-pointer"
              >
                <Play className="w-4 h-4 fill-brand-700" />
                <span>Resume</span>
              </motion.button>
            </div>
          </motion.section>
        )}

        {/* ── Upload Zone ── */}
        <motion.section 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="space-y-3 text-left"
        >
          <h3 className="text-xs font-bold text-secondary uppercase tracking-wider flex items-center gap-1.5">
            <Upload className="w-3 h-3" />
            Upload New Document
          </h3>
          <UploadZone token={token} onUploadSuccess={handleUploadSuccess} />
        </motion.section>

        {/* ── Document List ── */}
        <motion.section 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="space-y-3 text-left pb-10"
        >
          <h3 className="text-xs font-bold text-secondary uppercase tracking-wider flex items-center gap-1.5">
            <FileText className="w-3 h-3" />
            Your Documents
          </h3>
          {loading ? (
            <DocumentListSkeleton rows={4} />
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-2xl font-medium flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          ) : (
            <DocumentList 
              documents={documents} 
              onSelectDocument={onSelectDocument}
              onDownloadDocument={handleDownload}
            />
          )}
        </motion.section>
      </main>

      {/* ── Clear History Confirmation Modal ── */}
      <AnimatePresence>
        {showClearConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowClearConfirm(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white rounded-2xl shadow-floating border border-borderline/60 p-6 max-w-sm w-full space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-50 border border-red-100 flex items-center justify-center shrink-0">
                  <Trash2 className="w-5 h-5 text-red-500" />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-ink">Clear Document History</h3>
                  <p className="text-xs text-secondary mt-0.5">This will remove all your uploaded documents. This action cannot be undone.</p>
                </div>
              </div>

              <div className="flex items-center gap-2.5 pt-2">
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="flex-1 px-4 py-2.5 text-sm font-bold text-secondary bg-slate-100 hover:bg-slate-200 rounded-xl transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleClearHistory}
                  disabled={clearingHistory}
                  className="flex-1 px-4 py-2.5 text-sm font-bold text-white bg-red-500 hover:bg-red-600 rounded-xl transition shadow-sm flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60"
                >
                  {clearingHistory ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <>
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Clear All</span>
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('App ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 text-center">
          <div className="p-8 bg-white rounded-3xl shadow-card border border-borderline max-w-lg w-full space-y-5">
            <div className="w-14 h-14 rounded-2xl bg-red-50 text-red-600 flex items-center justify-center mx-auto">
              <Sparkles className="w-7 h-7" />
            </div>
            <h2 className="text-xl font-extrabold text-ink">Something went wrong</h2>
            <p className="text-xs text-secondary leading-relaxed">
              We encountered an unexpected view state. Don't worry, your documents and session are safe.
            </p>
            <div className="flex gap-3 justify-center pt-2">
              <button
                onClick={() => {
                  this.setState({ hasError: false });
                  window.location.href = '/';
                }}
                className="px-5 py-2.5 bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs rounded-xl shadow-xs transition cursor-pointer"
              >
                Return to Home
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const parseRouteFromUrl = () => {
  const path = window.location.pathname.replace(/^\/+|\/+$/g, '').toLowerCase();
  const hash = window.location.hash.replace(/^#\/?/, '').toLowerCase();
  
  if (hash === 'login' || path === 'login') return { view: 'login' };
  if (hash === 'register' || path === 'register' || hash === 'signup' || path === 'signup') return { view: 'register' };
  if (hash === 'dashboard' || path === 'dashboard') return { view: 'dashboard' };
  if (hash === 'workspace' || path === 'workspace') return { view: 'workspace' };
  
  // Hash sections for landing page (features, how, ai, testimonials)
  return { view: 'landing', section: hash || '' };
};

const MainApp = () => {
  const { user, token, loading, logout } = useAuth();
  const [currentView, setCurrentView] = useState(() => parseRouteFromUrl().view);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [sessionNotice, setSessionNotice] = useState('');

  // When the backend rejects a request with 401 (expired/invalid token),
  // clear the session and send the user back to the login view with a notice.
  useEffect(() => {
    const handleAuthExpired = () => {
      logout();
      setSelectedDoc(null);
      setSessionNotice('Your session has expired. Please sign in again to continue.');
      setCurrentView('login');
      window.history.replaceState({ view: 'login' }, '', '/#login');
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, [logout]);

  // Sync URL changes with current view (supports browser back/forward, direct URL typing)
  useEffect(() => {
    const handleUrlChange = () => {
      const route = parseRouteFromUrl();
      
      // If user navigates to workspace but has no selected doc, go to dashboard or landing
      if (route.view === 'workspace' && !selectedDoc) {
        setCurrentView(token ? 'dashboard' : 'landing');
        return;
      }
      
      setCurrentView(route.view);
      
      if (route.view === 'landing') {
        if (route.section) {
          setTimeout(() => {
            const el = document.getElementById(route.section);
            if (el) el.scrollIntoView({ behavior: 'smooth' });
          }, 100);
        } else {
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      }
    };

    // Listen to browser navigation
    window.addEventListener('popstate', handleUrlChange);
    window.addEventListener('hashchange', handleUrlChange);

    // Initial check on mount
    handleUrlChange();

    return () => {
      window.removeEventListener('popstate', handleUrlChange);
      window.removeEventListener('hashchange', handleUrlChange);
    };
  }, [token, selectedDoc]);

  const handleNavigate = (view, section = '') => {
    let targetUrl = '/';
    if (view === 'login') targetUrl = '/#login';
    else if (view === 'register') targetUrl = '/#register';
    else if (view === 'dashboard') targetUrl = '/#dashboard';
    else if (view === 'workspace') targetUrl = '/#workspace';
    else if (section && section !== 'hero') targetUrl = `/#${section}`;

    try {
      window.history.pushState({ view, section }, '', targetUrl);
    } catch (e) {
      window.location.hash = (section && section !== 'hero') ? section : view;
    }
    
    setCurrentView(view);

    if (view === 'landing') {
      if (section && section !== 'hero') {
        setTimeout(() => {
          const el = document.getElementById(section);
          if (el) {
            el.scrollIntoView({ behavior: 'smooth' });
          }
        }, 60);
      } else {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handleSelectDocument = (doc) => {
    setSelectedDoc(doc);
    handleNavigate('workspace');
  };

  const handleBackToDashboard = () => {
    setSelectedDoc(null);
    handleNavigate('dashboard');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col justify-center items-center">
        {/* Loading Spinner with loading_effect style */}
        <div className="relative w-16 h-16 mb-4">
          <div className="absolute inset-0 border-4 border-brand-600 border-t-transparent rounded-full animate-spin"></div>
          <div className="absolute inset-2 bg-brand-50 rounded-full flex items-center justify-center">
            <FileText className="w-5 h-5 text-brand-600" />
          </div>
        </div>
        <p className="text-sm font-semibold text-secondary">Initializing RapidDoc...</p>
      </div>
    );
  }

  switch (currentView) {
    case 'login':
      return <Login notice={sessionNotice} onNoticeDismiss={() => setSessionNotice('')} onToggleMode={handleNavigate} onSuccess={() => { setSessionNotice(''); handleNavigate('dashboard'); }} />;
    case 'register':
      return <Register onToggleMode={handleNavigate} onSuccess={() => handleNavigate('dashboard')} />;
    case 'dashboard':
      if (!token) {
        return <Login notice={sessionNotice} onNoticeDismiss={() => setSessionNotice('')} onToggleMode={handleNavigate} onSuccess={() => { setSessionNotice(''); handleNavigate('dashboard'); }} />;
      }
      return (
        <Dashboard 
          token={token} 
          user={user} 
          onLogout={logout} 
          onHome={() => handleNavigate('landing')}
          onSelectDocument={handleSelectDocument} 
        />
      );
    case 'workspace':
      if (!selectedDoc) {
        if (!token) {
          return <LandingPage onNavigate={handleNavigate} />;
        }
        return (
          <Dashboard 
            token={token} 
            user={user} 
            onLogout={logout} 
            onHome={() => handleNavigate('landing')}
            onSelectDocument={handleSelectDocument} 
          />
        );
      }
      return (
        <DocumentWorkspace 
          document={selectedDoc} 
          token={token} 
          onBack={handleBackToDashboard}
          onHome={() => handleNavigate('landing')}
        />
      );
    case 'landing':
    default:
      return <LandingPage onNavigate={handleNavigate} />;
  }
};

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <MainApp />
      </AuthProvider>
    </ErrorBoundary>
  );
}
