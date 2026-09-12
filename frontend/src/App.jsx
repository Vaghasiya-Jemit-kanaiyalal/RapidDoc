import React, { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { safeFetchJson } from './utils/api';
import { Login } from './components/Auth/Login';
import { Register } from './components/Auth/Register';
import { UploadZone } from './components/Dashboard/UploadZone';
import { DocumentList } from './components/Dashboard/DocumentList';
import { DocumentWorkspace } from './components/Editor/DocumentWorkspace';
import { downloadDocument } from './utils/download';
import logo from './assets/logo.png';
import rightHome from './assets/right_home.png';
import {
  Sparkles, FileText, ArrowRight, Play, LogOut,
  Home, Quote, Bold, Italic, Underline, Pen, Send, MessagesSquare, Image,
  BarChart2, Star, FileEdit, Brain, Lightbulb, Download, Upload
} from 'lucide-react';

const LandingPage = ({ onNavigate }) => {
  const { user } = useAuth();
  const featurePills = [
    { icon: FileEdit, label: 'Edit Instantly' },
    { icon: Brain, label: 'AI Understands' },
    { icon: Lightbulb, label: 'Smart Suggestions' },
    { icon: Download, label: 'Export Anywhere' },
  ];

  return (
    <div className="min-h-screen bg-white text-ink relative overflow-hidden flex flex-col">
      {/* Background decorations */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        {/* Soft radial gradients */}
        <div className="absolute inset-0 bg-[radial-gradient(at_18%_22%,rgba(54,92,255,0.08)_0px,transparent_50%),radial-gradient(at_85%_12%,rgba(54,92,255,0.06)_0px,transparent_45%),radial-gradient(at_72%_88%,rgba(139,92,246,0.05)_0px,transparent_50%)]" />
        {/* Blurred blue glows */}
        <div className="absolute top-[-18%] left-[-12%] w-[620px] h-[620px] bg-brand-600/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-22%] right-[-15%] w-[720px] h-[720px] bg-indigo-300/8 rounded-full blur-[140px]" />
        <div className="absolute top-[30%] right-[16%] w-[440px] h-[440px] bg-brand-600/6 rounded-full blur-[110px]" />
        {/* Light blue decorative shapes */}
        <div className="absolute top-[24%] right-[4%] w-24 h-24 border border-brand-200/40 rounded-3xl rotate-12" />
        <div className="absolute bottom-[26%] left-[6%] w-16 h-16 bg-brand-100/40 rounded-full" />
        <div className="absolute top-[40%] left-[45%] w-10 h-10 bg-brand-50 rounded-2xl -rotate-12 border border-brand-100" />
        {/* Thin curved lines */}
        <svg className="absolute inset-0 w-full h-full opacity-[0.06]" viewBox="0 0 1440 900" fill="none" preserveAspectRatio="xMidYMid slice">
          <path d="M-50 180 C 300 40, 620 320, 900 180 S 1400 60, 1560 220" stroke="#365CFF" strokeWidth="2" />
          <path d="M-50 700 C 320 560, 700 820, 1050 660 S 1420 540, 1560 640" stroke="#365CFF" strokeWidth="2" />
          <path d="M200 -40 C 260 200, 140 380, 260 560" stroke="#365CFF" strokeWidth="1.5" />
        </svg>
      </div>

      {/* Navigation */}
      <nav className="max-w-7xl mx-auto w-full px-6 lg:px-8 h-[88px] flex items-center justify-between z-10 shrink-0">
        <button
          onClick={() => onNavigate('landing')}
          className="shrink-0 cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95"
          title="Go to Home"
          aria-label="RapidDoc Home"
        >
          <img src={logo} alt="RapidDoc Logo" className="w-[80px] h-[80px] object-contain" />
        </button>

        <div className="hidden md:flex items-center gap-8 text-sm font-semibold text-secondary">
          <a href="#" className="nav-link nav-link-active text-brand-600">Home</a>
          <a href="#features" className="nav-link">Features</a>
          <a href="#how" className="nav-link">How It Works</a>
          <a href="#about" className="nav-link">About Us</a>
          <a href="#pricing" className="nav-link">Pricing</a>
        </div>

        <div className="flex items-center gap-3">
          {user ? (
            <button
              onClick={() => onNavigate('dashboard')}
              className="h-[42px] px-7 rounded-xl bg-gradient-to-r from-brand-500 to-brand-700 text-white font-bold text-sm shadow-soft-blue hover:scale-[1.03] active:scale-[0.98] transition duration-300"
            >
              Go to Dashboard
            </button>
          ) : (
            <>
              <button
                onClick={() => onNavigate('login')}
                className="h-[42px] w-[96px] border border-brand-500 rounded-xl text-brand-600 font-semibold text-sm hover:bg-brand-50 transition duration-300"
              >
                Login
              </button>
              <button
                onClick={() => onNavigate('register')}
                className="h-[42px] px-7 rounded-xl bg-gradient-to-r from-brand-500 to-brand-700 text-white font-bold text-sm shadow-soft-blue hover:scale-[1.03] active:scale-[0.98] transition duration-300"
              >
                Get Started
              </button>
            </>
          )}
        </div>
      </nav>

      {/* Hero Section — fits one viewport */}
      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 min-h-[calc(100vh-88px)] grid lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)] gap-8 lg:gap-10 items-center py-8 z-10">
        {/* Left Hero */}
        <div className="flex flex-col items-start text-left">
          {/* Heading */}
          <h1 className="text-[42px] sm:text-[52px] lg:text-[58px] font-bold text-ink leading-[1.12] tracking-tight mb-6">
            Work Smarter.
            <br />
            Not Harder.
            <br />
            <span className="font-script text-brand-600 relative inline-block mt-2">
              Let RapidDoc Handle It.
              <svg className="absolute left-0 -bottom-3 w-full h-[16px]" viewBox="0 0 420 20" fill="none" preserveAspectRatio="none" aria-hidden="true">
                <path d="M6 15 C 90 4, 240 3, 414 11" stroke="#365CFF" strokeWidth="7" strokeLinecap="round" opacity="0.45" />
                <path d="M10 17 C 120 8, 260 7, 410 13" stroke="#365CFF" strokeWidth="3" strokeLinecap="round" opacity="0.25" />
              </svg>
            </span>
          </h1>

          {/* Description */}
          <p className="text-[18px] sm:text-[20px] lg:text-[22px] leading-[1.6] text-[#4B5563] mb-6 max-w-md">
            Edit, <span className="text-brand-600 font-medium">understand</span>, and{' '}
            <span className="text-brand-600 font-medium">transform</span> your documents using the
            power of AI — all within one seamless platform.
          </p>

          {/* Feature Pills — one horizontal row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 lg:gap-3 mb-7 w-full max-w-xl">
            {featurePills.map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center justify-center gap-2.5 px-4 py-2.5 bg-white border border-borderline rounded-xl text-secondary text-[13px] font-semibold whitespace-nowrap">
                <Icon className="w-3.5 h-3.5 text-brand-600 shrink-0" />
                {label}
              </div>
            ))}
          </div>

          {/* CTA Buttons */}
          <div className="flex flex-wrap items-center gap-4">
            <button
              onClick={() => onNavigate(user ? 'dashboard' : 'register')}
              className="h-[50px] px-7 rounded-2xl bg-white border-2 border-brand-500 text-brand-600 font-bold text-sm flex items-center gap-2 hover:bg-brand-50 hover:scale-[1.03] active:scale-[0.98] transition duration-300"
              title="Upload a document and edit it with AI"
            >
              <Upload className="w-4 h-4" />
              <span>{user ? 'Open Your Documents' : 'Upload Document'}</span>
            </button>
            <button
              onClick={() => onNavigate(user ? 'dashboard' : 'register')}
              className="h-[50px] px-7 rounded-2xl bg-gradient-to-r from-brand-500 to-brand-700 text-white font-bold text-sm shadow-soft-blue flex items-center gap-2 hover:scale-[1.03] active:scale-[0.98] transition duration-300"
            >
              <span>{user ? 'Go to Dashboard' : 'Start for Free'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => alert("RapidDoc uses advanced NLP and PDF/DOCX styling engines. Simply sign in, upload a file, and change headers/footers/fonts instantly!")}
              className="h-[50px] px-7 rounded-2xl border border-borderline bg-white text-secondary font-bold text-sm flex items-center gap-2.5 hover:scale-[1.03] hover:border-brand-300 transition duration-300"
            >
              <span className="w-7 h-7 rounded-full bg-brand-50 flex items-center justify-center">
                <Play className="w-3.5 h-3.5 text-brand-600 fill-brand-600" />
              </span>
              See How It Works
            </button>
          </div>

          {/* Testimonial Card */}
          <div className="p-5 bg-white rounded-3xl shadow-floating border border-borderline/60 max-w-md mt-9">
            <Quote className="w-6 h-6 text-brand-600 mb-2.5" />
            <p className="text-[13px] text-ink/80 font-medium leading-relaxed mb-3">
              "RapidDoc has completely changed the way we work with documents. It's like having an
              AI assistant right inside our editor."
            </p>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center">
                <div className="flex -space-x-2.5">
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
          </div>
        </div>

        {/* Right Hero — Medical Dashboard Mockup */}
        {/* Right Hero — Mockup Image */}
        <div className="relative flex items-center justify-center lg:justify-end w-full lg:min-h-[760px]">
          {/* Soft blue glow behind the image */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[820px] h-[820px] bg-gradient-to-tr from-brand-600/15 via-indigo-600/5 to-transparent rounded-full blur-[100px] pointer-events-none" />

          {/* Dotted Grid Background */}
          <div 
            className="absolute inset-0 opacity-40 pointer-events-none" 
            style={{ 
              backgroundImage: 'radial-gradient(#365CFF 1.5px, transparent 1.5px)', 
              backgroundSize: '24px 24px' 
            }} 
          />

          {/* RapidDoc right home page image mockup */}
          <img 
            src={rightHome} 
            alt="RapidDoc Dashboard Mockup" 
            className="relative z-10 w-full max-w-[860px] lg:max-w-[980px] xl:max-w-[1120px] h-auto object-contain lg:-mr-6"
          />
        </div>
      </main>

      {/* Footer — below the fold */}
      <footer className="max-w-7xl mx-auto w-full px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center text-xs text-secondary gap-4 py-6 border-t border-borderline/50 z-10 shrink-0">
        <span>© 2026 RapidDoc. All rights reserved.</span>
        <div className="flex gap-6">
          <a href="#privacy" className="hover:text-brand-600 transition">Privacy Policy</a>
          <a href="#terms" className="hover:text-brand-600 transition">Terms of Service</a>
          <a href="#help" className="hover:text-brand-600 transition">Help</a>
        </div>
      </footer>
    </div>
  );
};

const Dashboard = ({ token, user, onLogout, onSelectDocument, onHome }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchDocuments = async () => {
    try {
      const data = await safeFetchJson('/api/documents', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
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

  const handleUploadSuccess = (newDoc) => {
    setDocuments([newDoc, ...documents]);
  };

  const handleDownload = async (doc) => {
    try {
      await downloadDocument(token, doc.id, doc.name);
    } catch (err) {
      setError(err.message || 'Error downloading document.');
    }
  };

  const activePipelines = documents.filter(d => (d.pipeline_stage || 1) < 4 || d.pipeline_status === 'In Progress');
  const latestActive = activePipelines[0];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-100 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-[88px] flex justify-between items-center">
          <button
            onClick={onHome}
            className="shrink-0 cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95"
            title="Go to Home"
            aria-label="RapidDoc Home"
          >
            <img src={logo} alt="RapidDoc Logo" className="w-[80px] h-[80px] object-contain" />
          </button>

          <div className="flex items-center gap-3">
            <button
              onClick={onHome}
              className="flex items-center gap-2 px-4 py-2 text-slate-500 hover:text-blue-600 bg-slate-50 border border-slate-100 hover:border-blue-200 rounded-xl text-xs font-bold transition"
              title="Go to Home"
            >
              <Home className="w-4 h-4" />
              <span>Home</span>
            </button>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-100 rounded-xl text-xs font-semibold text-slate-600">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-ping"></span>
              <span>{user ? user.name : 'User'}</span>
            </div>
            <button 
              onClick={onLogout}
              className="p-2 text-slate-400 hover:text-red-600 bg-slate-50 border border-slate-100 hover:border-red-100 rounded-xl transition"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-10 flex-grow space-y-8">
        <div className="text-left">
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">Your Document Hub</h2>
          <p className="text-sm text-slate-500 mt-1">Upload a document today and resume editing anytime across sessions.</p>
        </div>

        {/* Active Pipeline Resume Banner */}
        {latestActive && (
          <section className="bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 rounded-3xl p-6 text-white shadow-xl shadow-blue-500/20 relative overflow-hidden">
            <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="space-y-2 text-left">
                <div className="flex items-center gap-2">
                  <span className="bg-white/20 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full backdrop-blur-md">
                    Active Pipeline • Resume Work
                  </span>
                  <span className="text-xs text-blue-100 font-semibold">
                    Stage {latestActive.pipeline_stage || 1} of 4 ({latestActive.completion_percent || 25}%)
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white truncate max-w-md">{latestActive.name}</h3>
                <div className="w-full sm:w-64 bg-white/20 rounded-full h-2 overflow-hidden border border-white/20">
                  <div 
                    className="h-full bg-emerald-400 rounded-full transition-all duration-500" 
                    style={{ width: `${latestActive.completion_percent || 25}%` }}
                  />
                </div>
              </div>

              <button
                onClick={() => onSelectDocument(latestActive)}
                className="px-6 py-3 bg-white text-blue-700 hover:bg-blue-50 font-extrabold rounded-2xl text-xs flex items-center gap-2 shadow-lg transition hover:scale-[1.03] active:scale-[0.98] shrink-0"
              >
                <Play className="w-4 h-4 fill-blue-700" />
                <span>Resume Pipeline</span>
              </button>
            </div>
          </section>
        )}

        {/* Upload Zone */}
        <section className="space-y-3 text-left">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Upload New Document</h3>
          <UploadZone token={token} onUploadSuccess={handleUploadSuccess} />
        </section>

        {/* Document List */}
        <section className="space-y-3 text-left pb-10">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Your Documents</h3>
          {loading ? (
            <div className="flex justify-center items-center py-12">
              <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
            </div>
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-100 text-red-700 text-sm rounded-xl">
              {error}
            </div>
          ) : (
            <DocumentList 
              documents={documents} 
              onSelectDocument={onSelectDocument}
              onDownloadDocument={handleDownload}
            />
          )}
        </section>
      </main>
    </div>
  );
};

const MainApp = () => {
  const { user, token, loading, logout } = useAuth();
  const [currentView, setCurrentView] = useState('landing'); // 'landing', 'login', 'register', 'dashboard', 'workspace'
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [initialized, setInitialized] = useState(false);

  // Sync auth state with current view
  useEffect(() => {
    if (!loading) {
      if (token && user) {
        // On first load send the user to their dashboard; afterwards let them
        // navigate freely (including back to the Home/landing page).
        if (!initialized && currentView === 'landing') {
          setCurrentView('dashboard');
        }
        setInitialized(true);
        if (currentView === 'login' || currentView === 'register') {
          setCurrentView('dashboard');
        }
      } else {
        if (currentView !== 'landing' && currentView !== 'login' && currentView !== 'register') {
          setCurrentView('landing');
        }
      }
    }
  }, [user, token, loading, currentView, initialized]);

  const handleNavigate = (view) => {
    setCurrentView(view);
  };

  const handleSelectDocument = (doc) => {
    setSelectedDoc(doc);
    setCurrentView('workspace');
  };

  const handleBackToDashboard = () => {
    setSelectedDoc(null);
    setCurrentView('dashboard');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col justify-center items-center">
        {/* Loading Spinner with loading_effect style */}
        <div className="relative w-16 h-16 mb-4">
          <div className="absolute inset-0 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          <div className="absolute inset-2 bg-blue-50/50 rounded-full flex items-center justify-center">
            <FileText className="w-5 h-5 text-blue-600" />
          </div>
        </div>
        <p className="text-sm font-semibold text-slate-500">Initializing RapidDoc...</p>
      </div>
    );
  }

  switch (currentView) {
    case 'login':
      return <Login onToggleMode={handleNavigate} onSuccess={() => setCurrentView('dashboard')} />;
    case 'register':
      return <Register onToggleMode={handleNavigate} onSuccess={() => setCurrentView('dashboard')} />;
    case 'dashboard':
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
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}
