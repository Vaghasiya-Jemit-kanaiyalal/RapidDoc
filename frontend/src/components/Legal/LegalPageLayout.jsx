import React from 'react';
import {
  ArrowLeft,
  BookOpen,
  Cookie,
  FileText,
  HelpCircle,
  Mail,
  Shield,
} from 'lucide-react';
import loadingEffect from '../../assets/laoding_effect.png';

const LEGAL_LINKS = [
  { id: 'privacy', label: 'Privacy Policy', icon: Shield },
  { id: 'terms', label: 'Terms of Service', icon: FileText },
  { id: 'cookies', label: 'Cookie Policy', icon: Cookie },
  { id: 'help', label: 'Help Center', icon: HelpCircle },
];

export const LegalPageLayout = ({
  active,
  title,
  description,
  icon: Icon,
  updated = 'October 26, 2026',
  onNavigate,
  children,
}) => {
  const openPage = (page) => {
    onNavigate(page);
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="fixed top-0 left-0 right-0 bg-white/95 backdrop-blur-xl border-b border-slate-200 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-[76px] flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => openPage('landing')}
            className="flex items-center gap-2.5 group shrink-0"
            aria-label="RapidDoc home"
          >
            <img src={loadingEffect} alt="" className="w-[50px] h-[50px]" />
            <span className="text-xl sm:text-2xl font-black tracking-tight text-slate-900">
              Rapid<span className="text-brand-600">Doc</span>
            </span>
          </button>

          <div className="hidden md:flex items-center gap-1 rounded-xl bg-slate-100/80 p-1">
            {LEGAL_LINKS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => openPage(id)}
                className={`px-3 py-2 rounded-lg text-xs font-bold transition ${
                  active === id
                    ? 'bg-white text-brand-600 shadow-sm'
                    : 'text-slate-600 hover:text-brand-600 hover:bg-white/60'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => openPage('landing')}
            className="flex items-center gap-2 px-3 sm:px-4 py-2 text-slate-700 hover:text-brand-600 font-semibold text-sm shrink-0"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Back to Home</span>
          </button>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 sm:pt-32 pb-16">
        <header className="relative overflow-hidden rounded-3xl border border-blue-100 bg-gradient-to-br from-white via-blue-50/70 to-indigo-50 px-6 py-8 sm:px-10 sm:py-10 mb-8 shadow-card">
          <div className="absolute -right-12 -top-12 w-52 h-52 rounded-full bg-blue-200/30 blur-3xl pointer-events-none" />
          <div className="relative flex flex-col sm:flex-row sm:items-center gap-5">
            <div className="w-14 h-14 rounded-2xl bg-white border border-blue-100 shadow-sm flex items-center justify-center shrink-0">
              <Icon className="w-7 h-7 text-brand-600" />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-black uppercase tracking-[0.18em] text-brand-600 mb-2">
                Legal &amp; Support
              </p>
              <h1 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">{title}</h1>
              <p className="text-sm text-slate-600 leading-relaxed mt-2 max-w-2xl">{description}</p>
              <p className="text-xs font-semibold text-slate-400 mt-3">Last updated: {updated}</p>
            </div>
          </div>
        </header>

        <div className="grid lg:grid-cols-[230px_minmax(0,1fr)] gap-6 items-start">
          <aside className="lg:sticky lg:top-28 space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
              <p className="px-2 pt-1 pb-2 text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">
                Policies &amp; help
              </p>
              <nav className="space-y-1" aria-label="Legal and support pages">
                {LEGAL_LINKS.map(({ id, label, icon: LinkIcon }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => openPage(id)}
                    className={`w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-xs font-bold transition ${
                      active === id
                        ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-brand-600'
                    }`}
                  >
                    <LinkIcon className="w-4 h-4 shrink-0" />
                    {label}
                  </button>
                ))}
              </nav>
            </div>

            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
              <div className="flex items-center gap-2 text-emerald-800 font-bold text-sm">
                <BookOpen className="w-4 h-4" />
                Need a hand?
              </div>
              <p className="text-xs text-emerald-800/80 leading-relaxed mt-2">
                Search common answers or send our team a message from the Help Center.
              </p>
              <button
                type="button"
                onClick={() => openPage('help')}
                className="mt-3 inline-flex items-center gap-1.5 text-xs font-black text-emerald-700 hover:text-emerald-900"
              >
                Visit Help Center
                <ArrowLeft className="w-3.5 h-3.5 rotate-180" />
              </button>
            </div>

            <a
              href="mailto:support@rapiddoc.ai"
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold text-slate-500 hover:text-brand-600 transition"
            >
              <Mail className="w-4 h-4" />
              support@rapiddoc.ai
            </a>
          </aside>

          <article className="rounded-3xl border border-slate-200 bg-white px-5 py-7 sm:px-9 sm:py-9 shadow-card">
            <div className="prose prose-slate max-w-none space-y-8 text-sm sm:text-[15px]">
              {children}
            </div>
          </article>
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-7 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-slate-500 font-medium">
            &copy; 2026 RapidDoc. All rights reserved.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
            <button type="button" onClick={() => openPage('privacy')} className="text-xs font-semibold text-slate-500 hover:text-brand-600 transition">
              Privacy
            </button>
            <button type="button" onClick={() => openPage('terms')} className="text-xs font-semibold text-slate-500 hover:text-brand-600 transition">
              Terms
            </button>
            <button type="button" onClick={() => openPage('cookies')} className="text-xs font-semibold text-slate-500 hover:text-brand-600 transition">
              Cookies
            </button>
            <button type="button" onClick={() => openPage('help')} className="text-xs font-semibold text-slate-500 hover:text-brand-600 transition">
              Help Center
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LegalPageLayout;
