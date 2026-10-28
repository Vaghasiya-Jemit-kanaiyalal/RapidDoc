import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  FileQuestion,
  HelpCircle,
  LifeBuoy,
  LockKeyhole,
  Mail,
  MessageSquare,
  Search,
  Send,
  Sparkles,
  Upload,
  UserRound,
} from 'lucide-react';
import { API_URL, safeFetchJson } from '../../utils/api';
import { LegalPageLayout } from './LegalPageLayout';

const CATEGORIES = [
  {
    id: 'start',
    title: 'Getting started',
    description: 'Upload a document, open the editor, and run your first edit.',
    icon: Upload,
    color: 'text-blue-600 bg-blue-50 border-blue-100',
  },
  {
    id: 'editing',
    title: 'Editing & formatting',
    description: 'Find and replace, headings, tables, fonts, images, headers, and footers.',
    icon: BookOpen,
    color: 'text-emerald-600 bg-emerald-50 border-emerald-100',
  },
  {
    id: 'ai',
    title: 'AI tools',
    description: 'Summaries, translation, study notes, MCQs, and keyword extraction.',
    icon: Sparkles,
    color: 'text-purple-600 bg-purple-50 border-purple-100',
  },
  {
    id: 'account',
    title: 'Account & privacy',
    description: 'Sign-in, password reset, document ownership, and data requests.',
    icon: LockKeyhole,
    color: 'text-amber-600 bg-amber-50 border-amber-100',
  },
];

const FAQS = [
  {
    topics: ['start', 'uploads'],
    question: 'Which file types can I upload?',
    answer:
      'RapidDoc accepts PDF and DOCX documents. Each file can be up to 15 MB. If a file is rejected, check that the extension matches the real format and that it is not password-protected.',
  },
  {
    topics: ['start', 'editing'],
    question: 'How do I replace text across a document?',
    answer:
      'Open the document and type a command such as “Replace ACME with Acme Corporation” in the command bar. RapidDoc finds matching variants first, lets you review them, and then applies the replacement to the ones you select.',
  },
  {
    topics: ['ai'],
    question: 'Which AI tools are available?',
    answer:
      'The command bar supports summarization, translation, study notes, MCQ generation, keyword extraction, rewriting, and image analysis. Open the slash menu or use a quick command chip to start one of the common tools.',
  },
  {
    topics: ['ai'],
    question: 'Why is an AI result sometimes unavailable?',
    answer:
      'RapidDoc uses local models first and can fall back to a configured cloud AI provider. If neither engine can handle a request, the editor shows an error instead of inventing a result. Try a shorter selection or a more specific command.',
  },
  {
    topics: ['editing'],
    question: 'Will editing change my document formatting?',
    answer:
      'RapidDoc edits supported document structures directly and keeps the original file format. Complex layouts can still vary by file, so review the preview and download a copy before sharing important documents.',
  },
  {
    topics: ['editing', 'exports'],
    question: 'How do I download my edited document?',
    answer:
      'Use the download control in the editor and choose the original format or an available export format. For summaries, the summary panel has its own copy and export buttons.',
  },
  {
    topics: ['account'],
    question: 'How do I reset my password?',
    answer:
      'Choose “Forgot password” on the sign-in screen, enter your account email, and use the six-digit code sent to that address. If email delivery is not configured on your installation, use the development code shown by your local setup.',
  },
  {
    topics: ['account'],
    question: 'Who can see the documents I upload?',
    answer:
      'Documents are associated with the account that uploaded them. Other users cannot open them through their own accounts. See the Privacy Policy for retention, AI processing, and data-request details.',
  },
  {
    topics: ['ai', 'study'],
    question: 'How do I create study notes from a document?',
    answer:
      'Open the document and type “Create study notes from this document”. The result appears in the AI result panel as structured notes with key takeaways that you can copy or export.',
  },
  {
    topics: ['ai', 'keywords'],
    question: 'How do I extract keywords?',
    answer:
      'Type “Extract 10 keywords” or “Find the important keywords in this document”. RapidDoc ranks meaningful terms from the document and displays them as a reviewable list.',
  },
  {
    topics: ['ai', 'translation'],
    question: 'Can I translate a document?',
    answer:
      'Yes. Type “Translate this document to Spanish” or translate the selected text by selecting it first. Translation needs an available AI translation engine; the editor reports clearly when one is not configured.',
  },
];

const INITIAL_FORM = {
  name: '',
  email: '',
  category: 'General question',
  subject: '',
  message: '',
};

export const HelpCenter = ({ onNavigate, user }) => {
  const [query, setQuery] = useState('');
  const [openFaq, setOpenFaq] = useState(0);
  const [form, setForm] = useState(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    if (!user) return;
    setForm((current) => ({
      ...current,
      name: current.name || user.name || '',
      email: current.email || user.email || '',
    }));
  }, [user]);

  const filteredFaqs = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return FAQS;
    return FAQS.filter((faq) => (
      faq.question.toLowerCase().includes(term)
      || faq.answer.toLowerCase().includes(term)
      || faq.topics.some((topic) => topic.includes(term))
    ));
  }, [query]);

  const updateField = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
    if (notice) setNotice(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;

    const name = form.name.trim();
    const email = form.email.trim();
    const subject = form.subject.trim();
    const message = form.message.trim();

    if (!name || !email || !subject || !message) {
      setNotice({ tone: 'error', text: 'Please complete your name, email, subject, and issue description.' });
      return;
    }
    if (message.length < 10) {
      setNotice({ tone: 'error', text: 'Please describe the issue in at least 10 characters.' });
      return;
    }

    setSubmitting(true);
    setNotice(null);
    try {
      const data = await safeFetchJson(`${API_URL}/support/issues`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          email,
          category: form.category,
          subject,
          message,
          page_url: window.location.href,
        }),
      });
      setForm(INITIAL_FORM);
      setNotice({
        tone: 'success',
        text: data.ticket_id
          ? `Message sent. Your reference is ${data.ticket_id}. We will reply by email.`
          : 'Message sent. We will reply by email.',
      });
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error.message || 'Your message could not be sent. Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <LegalPageLayout
      active="help"
      icon={HelpCircle}
      title="Help Center"
      description="Find a quick answer, or describe the issue you are facing and send it directly to our support team."
      onNavigate={onNavigate}
    >
      <section>
        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-5 sm:p-6">
          <div className="flex items-center gap-2 text-slate-900 font-bold text-lg">
            <LifeBuoy className="w-5 h-5 text-brand-600" />
            How can we help?
          </div>
          <p className="text-sm text-slate-600 mt-1">
            Search the common answers below or jump straight to the issue form.
          </p>
          <div className="relative mt-4">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search for uploads, replace, summaries, translation, keywords..."
              className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-11 pr-4 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            />
          </div>
          {query && (
            <p className="mt-2 text-xs font-semibold text-slate-500">
              {filteredFaqs.length} result{filteredFaqs.length === 1 ? '' : 's'} for “{query}”
            </p>
          )}
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between gap-3 mb-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Browse by topic</h2>
            <p className="text-sm text-slate-500 mt-1">Pick the area that matches what you are trying to do.</p>
          </div>
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          {CATEGORIES.map(({ id, title, description, icon: Icon, color }) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                setQuery('');
                const first = FAQS.findIndex((faq) => faq.topics.includes(id));
                setOpenFaq(first >= 0 ? first : 0);
              }}
              className="group rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-card transition"
            >
              <span className={`inline-flex w-9 h-9 items-center justify-center rounded-xl border ${color}`}>
                <Icon className="w-4.5 h-4.5" />
              </span>
              <span className="block text-sm font-black text-slate-900 mt-3 group-hover:text-brand-700">{title}</span>
              <span className="block text-xs text-slate-500 leading-relaxed mt-1">{description}</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-1">Frequently asked questions</h2>
        <p className="text-sm text-slate-500 mb-4">Answers based on the features currently available in RapidDoc.</p>

        {filteredFaqs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
            <FileQuestion className="w-7 h-7 text-slate-400 mx-auto" />
            <p className="text-sm font-bold text-slate-700 mt-2">No answer matched your search.</p>
            <p className="text-xs text-slate-500 mt-1">Send us the details below and we will take a look.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white overflow-hidden">
            {filteredFaqs.map((faq, index) => {
              const isOpen = openFaq === index;
              return (
                <div key={faq.question}>
                  <button
                    type="button"
                    onClick={() => setOpenFaq(isOpen ? -1 : index)}
                    className="w-full flex items-center justify-between gap-4 px-4 sm:px-5 py-4 text-left hover:bg-slate-50/80 transition"
                    aria-expanded={isOpen}
                  >
                    <span className="text-sm font-bold text-slate-800">{faq.question}</span>
                    <ChevronDown
                      className={`w-4 h-4 shrink-0 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                    />
                  </button>
                  {isOpen && (
                    <div className="px-4 sm:px-5 pb-4 -mt-1">
                      <p className="text-sm text-slate-600 leading-relaxed">{faq.answer}</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section id="report" className="scroll-mt-28">
        <div className="rounded-3xl border border-blue-100 bg-gradient-to-br from-white to-blue-50/60 p-5 sm:p-7">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-brand-600 text-white flex items-center justify-center shrink-0 shadow-md shadow-blue-500/20">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">Comment on an issue</h2>
              <p className="text-sm text-slate-600 mt-1 leading-relaxed">
                Describe what went wrong, what you expected, and the steps that led to it. Your message goes to
                the support queue with a reference number.
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4" noValidate>
            <div className="grid sm:grid-cols-2 gap-4">
              <label className="block">
                <span className="flex items-center gap-1.5 text-xs font-bold text-slate-700 mb-1.5">
                  <UserRound className="w-3.5 h-3.5 text-slate-400" />
                  Your name
                </span>
                <input
                  type="text"
                  value={form.name}
                  onChange={updateField('name')}
                  maxLength={80}
                  autoComplete="name"
                  placeholder="e.g. Umran Sheikh"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                />
              </label>
              <label className="block">
                <span className="flex items-center gap-1.5 text-xs font-bold text-slate-700 mb-1.5">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  Email address
                </span>
                <input
                  type="email"
                  value={form.email}
                  onChange={updateField('email')}
                  maxLength={160}
                  autoComplete="email"
                  placeholder="you@example.com"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                />
              </label>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <label className="block">
                <span className="text-xs font-bold text-slate-700 mb-1.5 block">Topic</span>
                <select
                  value={form.category}
                  onChange={updateField('category')}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                >
                  <option>General question</option>
                  <option>Editing &amp; formatting</option>
                  <option>AI features</option>
                  <option>Uploads &amp; exports</option>
                  <option>Account &amp; security</option>
                  <option>Bug report</option>
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-bold text-slate-700 mb-1.5 block">Subject</span>
                <input
                  type="text"
                  value={form.subject}
                  onChange={updateField('subject')}
                  maxLength={120}
                  placeholder="A short summary of the issue"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                />
              </label>
            </div>

            <label className="block">
              <span className="text-xs font-bold text-slate-700 mb-1.5 block">Describe the issue</span>
              <textarea
                value={form.message}
                onChange={updateField('message')}
                rows={5}
                maxLength={5000}
                placeholder="Tell us what happened, what you expected, and any command or file type involved..."
                className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              />
              <span className="mt-1 block text-right text-[10px] font-semibold text-slate-400">
                {form.message.length}/5000
              </span>
            </label>

            {notice && (
              <div
                role="status"
                className={`flex items-start gap-2 rounded-xl border px-3.5 py-3 text-xs font-semibold ${
                  notice.tone === 'success'
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                    : 'border-red-200 bg-red-50 text-red-700'
                }`}
              >
                {notice.tone === 'success' ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0 mt-px" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0 mt-px" />
                )}
                <span>{notice.text}</span>
              </div>
            )}

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Do not include passwords or sensitive personal information in your message.
              </p>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed px-5 py-2.5 text-sm font-bold text-white shadow-md shadow-blue-500/20 transition"
              >
                <Send className="w-4 h-4" />
                {submitting ? 'Sending...' : 'Send message'}
              </button>
            </div>
          </form>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900">Prefer email?</h2>
            <p className="text-xs text-slate-500 mt-1">You can reach the team directly at support@rapiddoc.ai.</p>
          </div>
          <a
            href="mailto:support@rapiddoc.ai"
            className="inline-flex items-center gap-2 text-xs font-bold text-brand-600 hover:text-brand-700"
          >
            <Mail className="w-4 h-4" />
            support@rapiddoc.ai
          </a>
        </div>
      </section>
    </LegalPageLayout>
  );
};

export default HelpCenter;
