import React from 'react';
import {
  Sparkles, Compass, ListOrdered, TrendingUp, Layers, Award,
  FileText, Quote, ChevronRight
} from 'lucide-react';

/**
 * Premium, high-fidelity Markdown renderer for RapidDoc summaries.
 * Features:
 * - Executive section headers with contextual icons
 * - Glassmorphic callout cards for blockquotes & executive briefs
 * - Tag badge pills for categorized findings
 * - Metric / quantitative figure auto-highlighting
 * - GitHub-flavored tables & horizontal dividers
 * - Clean typography without leaking raw markdown symbols
 */
export const MarkdownRenderer = ({ content, className = '' }) => {
  if (!content) return null;

  const lines = String(content).split('\n');
  const elements = [];
  let inCodeBlock = false;
  let codeBlockLines = [];
  let currentList = [];
  let listType = null; // 'ul' | 'ol'
  let currentQuote = [];
  let currentTable = [];

  const getSectionIcon = (headingTitle) => {
    const lower = String(headingTitle || '').toLowerCase();
    if (lower.includes('overview') || lower.includes('brief') || lower.includes('abstract')) {
      return <Compass className="w-3.5 h-3.5 text-indigo-600" />;
    }
    if (lower.includes('point') || lower.includes('takeaway') || lower.includes('key')) {
      return <ListOrdered className="w-3.5 h-3.5 text-indigo-600" />;
    }
    if (lower.includes('finding') || lower.includes('metric') || lower.includes('result') || lower.includes('data')) {
      return <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />;
    }
    if (lower.includes('highlight') || lower.includes('section') || lower.includes('detail') || lower.includes('part')) {
      return <Layers className="w-3.5 h-3.5 text-blue-600" />;
    }
    if (lower.includes('conclusion') || lower.includes('outcome') || lower.includes('summary')) {
      return <Award className="w-3.5 h-3.5 text-purple-600" />;
    }
    return <FileText className="w-3.5 h-3.5 text-indigo-500" />;
  };

  const flushQuote = () => {
    if (currentQuote.length > 0) {
      elements.push(
        <div
          key={`quote-${elements.length}`}
          className="my-3 rounded-2xl bg-gradient-to-r from-indigo-50/90 via-violet-50/40 to-white border border-indigo-200/80 p-3.5 shadow-xs"
        >
          <div className="flex items-start gap-2.5">
            <span className="p-1.5 rounded-xl bg-indigo-100 text-indigo-700 shrink-0 mt-0.5 shadow-2xs">
              <Quote className="w-3.5 h-3.5" />
            </span>
            <div className="text-xs sm:text-[12.5px] leading-relaxed text-slate-800 font-medium space-y-1">
              {currentQuote.map((ql, qIdx) => (
                <p key={qIdx}>{renderInline(ql)}</p>
              ))}
            </div>
          </div>
        </div>
      );
      currentQuote = [];
    }
  };

  const flushTable = () => {
    if (currentTable.length > 0) {
      const rows = currentTable.map(r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
      if (rows.length >= 2) {
        // Find if row 1 is delimiter (|---|---|)
        const isDelimiter = rows[1].every(c => /^:?-+:?$/.test(c));
        const headerRow = rows[0];
        const bodyRows = isDelimiter ? rows.slice(2) : rows.slice(1);

        elements.push(
          <div
            key={`table-${elements.length}`}
            className="my-3 overflow-x-auto rounded-xl border border-indigo-100 bg-white shadow-2xs"
          >
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-indigo-50/70 text-indigo-950 font-bold border-b border-indigo-100">
                <tr>
                  {headerRow.map((cell, ci) => (
                    <th key={ci} className="px-3 py-2 tracking-wide font-extrabold">{renderInline(cell)}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {bodyRows.map((r, ri) => (
                  <tr key={ri} className="hover:bg-indigo-50/30 transition-colors">
                    {r.map((cell, ci) => (
                      <td key={ci} className="px-3 py-2 text-slate-700">{renderInline(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      currentTable = [];
    }
  };

  const flushList = () => {
    if (currentList.length > 0) {
      if (listType === 'ol') {
        elements.push(
          <ol key={`ol-${elements.length}`} className="my-2 space-y-1.5 pl-0.5">
            {currentList.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 text-xs sm:text-[12.5px] leading-relaxed text-slate-700">
                <span className="font-bold text-indigo-700 shrink-0 text-[10px] bg-indigo-50 border border-indigo-200/80 rounded-md px-1.5 py-0.5 mt-0.5 shadow-2xs">
                  {idx + 1}
                </span>
                <span className="min-w-0 flex-1">{renderListItemContent(item)}</span>
              </li>
            ))}
          </ol>
        );
      } else {
        elements.push(
          <ul key={`ul-${elements.length}`} className="my-2 space-y-1.5 pl-0.5">
            {currentList.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 text-xs sm:text-[12.5px] leading-relaxed text-slate-700">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 mt-2 shrink-0 inline-block shadow-xs" />
                <span className="min-w-0 flex-1">{renderListItemContent(item)}</span>
              </li>
            ))}
          </ul>
        );
      }
      currentList = [];
      listType = null;
    }
  };

  const flushAll = () => {
    flushQuote();
    flushTable();
    flushList();
  };

  const renderListItemContent = (itemText) => {
    // Check if item has a bold badge label prefix: e.g. **Category / Metric**: Value
    const badgeMatch = itemText.match(/^\*\*([^*:]+)\*\*:\s*(.*)$/);
    if (badgeMatch) {
      const category = badgeMatch[1].trim();
      const body = badgeMatch[2].trim();
      return (
        <span className="flex flex-wrap items-baseline gap-1.5">
          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-indigo-50 border border-indigo-200/70 text-indigo-800 shadow-2xs shrink-0 tracking-tight">
            {category}
          </span>
          <span className="text-slate-700 min-w-0">{renderInline(body)}</span>
        </span>
      );
    }
    return renderInline(itemText);
  };

  const renderInline = (text) => {
    if (!text) return null;

    // Pattern for inline code, bold, italic
    const tokens = [];
    let remaining = text;
    let keyIdx = 0;

    const inlineRegex = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/;

    while (remaining) {
      const match = remaining.match(inlineRegex);
      if (!match) {
        tokens.push(renderPlainTextWithMetricHighlight(remaining, keyIdx++));
        break;
      }

      const matchIdx = match.index;
      if (matchIdx > 0) {
        tokens.push(renderPlainTextWithMetricHighlight(remaining.slice(0, matchIdx), keyIdx++));
      }

      const matchedStr = match[0];
      if (matchedStr.startsWith('`') && matchedStr.endsWith('`')) {
        tokens.push(
          <code
            key={`code-${keyIdx++}`}
            className="rounded bg-indigo-50/80 border border-indigo-100/90 px-1.5 py-0.5 font-mono text-[10.5px] text-indigo-700 font-semibold"
          >
            {matchedStr.slice(1, -1)}
          </code>
        );
      } else if (
        (matchedStr.startsWith('**') && matchedStr.endsWith('**')) ||
        (matchedStr.startsWith('__') && matchedStr.endsWith('__'))
      ) {
        tokens.push(
          <strong key={`strong-${keyIdx++}`} className="font-extrabold text-slate-900">
            {matchedStr.slice(2, -2)}
          </strong>
        );
      } else if (
        (matchedStr.startsWith('*') && matchedStr.endsWith('*')) ||
        (matchedStr.startsWith('_') && matchedStr.endsWith('_'))
      ) {
        tokens.push(
          <em key={`em-${keyIdx++}`} className="italic text-slate-700 font-medium">
            {matchedStr.slice(1, -1)}
          </em>
        );
      } else {
        tokens.push(matchedStr);
      }

      remaining = remaining.slice(matchIdx + matchedStr.length);
    }

    return tokens;
  };

  const renderPlainTextWithMetricHighlight = (plainText, baseKey) => {
    // Regex for statistics, currency, metrics, percentages (e.g. $1.85M, 12%, 120,000, 4.2ms)
    const metricRegex = /(\$\d+(?:,\d+)*(?:\.\d+)?(?:M|B|K)?|\b\d+(?:\.\d+)?%|\b\d+(?:,\d+)+(?:\.\d+)?|\b\d+\s*(?:ms|fps|frames?|records?|queries)\b)/gi;
    const parts = plainText.split(metricRegex);
    if (parts.length === 1) return plainText;

    return parts.map((part, pIdx) => {
      if (metricRegex.test(part)) {
        return (
          <span
            key={`metric-${baseKey}-${pIdx}`}
            className="font-bold text-indigo-950 bg-indigo-50/70 border border-indigo-200/50 px-1 py-0.2 rounded text-[11px] inline-block shadow-3xs"
          >
            {part}
          </span>
        );
      }
      return part;
    });
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    // Check code fence
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          <pre
            key={`codeblock-${elements.length}`}
            className="my-2.5 overflow-x-auto rounded-xl bg-slate-900 p-3 font-mono text-[10.5px] leading-relaxed text-indigo-200 border border-slate-800 shadow-inner"
          >
            <code>{codeBlockLines.join('\n')}</code>
          </pre>
        );
        codeBlockLines = [];
        inCodeBlock = false;
      } else {
        flushAll();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(rawLine);
      continue;
    }

    // Horizontal Rule
    if (/^[-*_]{3,}$/.test(line)) {
      flushAll();
      elements.push(
        <div key={`hr-${elements.length}`} className="my-3.5 flex items-center gap-3">
          <div className="h-px bg-gradient-to-r from-transparent via-indigo-200 to-transparent flex-1" />
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
          <div className="h-px bg-gradient-to-r from-transparent via-indigo-200 to-transparent flex-1" />
        </div>
      );
      continue;
    }

    // Markdown Table Line
    if (line.startsWith('|') && line.endsWith('|')) {
      flushQuote();
      flushList();
      currentTable.push(line);
      continue;
    } else if (currentTable.length > 0) {
      flushTable();
    }

    // Blockquote
    if (line.startsWith('>')) {
      flushList();
      flushTable();
      currentQuote.push(line.replace(/^>\s*/, ''));
      continue;
    } else if (currentQuote.length > 0) {
      flushQuote();
    }

    if (!line) {
      flushAll();
      continue;
    }

    // Document Title Heading (# )
    if (line.startsWith('# ')) {
      flushAll();
      elements.push(
        <div
          key={`h1-${elements.length}`}
          className="mt-1 mb-3 pb-2.5 border-b border-indigo-100 flex items-center justify-between gap-2"
        >
          <h1 className="text-sm sm:text-base font-black text-slate-900 tracking-tight flex items-center gap-2">
            <span className="p-1 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-xs">
              <Sparkles className="w-3.5 h-3.5" />
            </span>
            <span>{renderInline(line.slice(2))}</span>
          </h1>
        </div>
      );
      continue;
    }

    // Major Section Heading (## )
    if (line.startsWith('## ')) {
      flushAll();
      const headingText = line.slice(3);
      const icon = getSectionIcon(headingText);
      elements.push(
        <h2
          key={`h2-${elements.length}`}
          className="mt-4 mb-2 text-xs sm:text-[13px] font-extrabold text-indigo-950 uppercase tracking-wider flex items-center gap-2 pb-1.5 border-b border-slate-100"
        >
          <span className="p-1 rounded-md bg-indigo-50/90 border border-indigo-100 shadow-3xs shrink-0">
            {icon}
          </span>
          <span className="min-w-0">{renderInline(headingText)}</span>
        </h2>
      );
      continue;
    }

    // Minor Subsection (### )
    if (line.startsWith('### ')) {
      flushAll();
      elements.push(
        <h3
          key={`h3-${elements.length}`}
          className="mt-2.5 mb-1 text-xs font-bold text-slate-800 flex items-center gap-1.5"
        >
          <ChevronRight className="w-3 h-3 text-indigo-500 shrink-0" />
          <span>{renderInline(line.slice(4))}</span>
        </h3>
      );
      continue;
    }

    // Unordered list
    if (line.startsWith('- ') || line.startsWith('* ')) {
      flushQuote();
      flushTable();
      if (listType !== 'ul') {
        flushList();
        listType = 'ul';
      }
      currentList.push(line.slice(2));
      continue;
    }

    // Ordered list: e.g. "1. "
    const olMatch = line.match(/^(\d+)\.\s+(.*)/);
    if (olMatch) {
      flushQuote();
      flushTable();
      if (listType !== 'ol') {
        flushList();
        listType = 'ol';
      }
      currentList.push(olMatch[2]);
      continue;
    }

    // Standard paragraph line
    flushAll();
    elements.push(
      <p
        key={`p-${elements.length}`}
        className="my-1.5 text-xs sm:text-[12.5px] leading-relaxed text-slate-700"
      >
        {renderInline(line)}
      </p>
    );
  }

  flushAll();

  return <div className={`space-y-0.5 text-left ${className}`}>{elements}</div>;
};

export default MarkdownRenderer;
