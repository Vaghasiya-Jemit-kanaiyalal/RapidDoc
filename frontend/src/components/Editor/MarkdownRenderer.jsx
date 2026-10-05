import React from 'react';

/**
 * Lightweight, high-fidelity Markdown renderer for RapidDoc summaries.
 * Renders headings, bold/italic inline text, lists, and code blocks
 * with clean typography without leaking raw markdown symbols.
 */
export const MarkdownRenderer = ({ content, className = '' }) => {
  if (!content) return null;

  const lines = String(content).split('\n');
  const elements = [];
  let inCodeBlock = false;
  let codeBlockLines = [];
  let currentList = [];
  let listType = null; // 'ul' | 'ol'

  const flushList = () => {
    if (currentList.length > 0) {
      if (listType === 'ol') {
        elements.push(
          <ol key={`ol-${elements.length}`} className="my-1.5 space-y-1 pl-1">
            {currentList.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2 text-[11.5px] leading-relaxed text-slate-700">
                <span className="font-bold text-indigo-600 shrink-0 text-[10px] bg-indigo-50 border border-indigo-100 rounded px-1.5 py-0.2">
                  {idx + 1}
                </span>
                <span className="min-w-0">{renderInline(item)}</span>
              </li>
            ))}
          </ol>
        );
      } else {
        elements.push(
          <ul key={`ul-${elements.length}`} className="my-1.5 space-y-1 pl-1">
            {currentList.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2 text-[11.5px] leading-relaxed text-slate-700">
                <span className="text-indigo-500 font-bold shrink-0 mt-0.5">•</span>
                <span className="min-w-0">{renderInline(item)}</span>
              </li>
            ))}
          </ul>
        );
      }
      currentList = [];
      listType = null;
    }
  };

  const renderInline = (text) => {
    if (!text) return null;

    // Pattern for inline code, bold, italic
    const tokens = [];
    let remaining = text;
    let keyIdx = 0;

    // Match `code`, **bold**, or *italic*
    const inlineRegex = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/;

    while (remaining) {
      const match = remaining.match(inlineRegex);
      if (!match) {
        tokens.push(remaining);
        break;
      }

      const matchIdx = match.index;
      if (matchIdx > 0) {
        tokens.push(remaining.slice(0, matchIdx));
      }

      const matchedStr = match[0];
      if (matchedStr.startsWith('`') && matchedStr.endsWith('`')) {
        tokens.push(
          <code
            key={`code-${keyIdx++}`}
            className="rounded bg-indigo-50/80 border border-indigo-100 px-1 py-0.5 font-mono text-[10px] text-indigo-700 font-semibold"
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
          <em key={`em-${keyIdx++}`} className="italic text-slate-800">
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

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    // Check code fence
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        // End code block
        elements.push(
          <pre
            key={`codeblock-${elements.length}`}
            className="my-2 overflow-x-auto rounded-xl bg-slate-900 p-3 font-mono text-[10.5px] leading-relaxed text-indigo-200 border border-slate-800 shadow-inner"
          >
            <code>{codeBlockLines.join('\n')}</code>
          </pre>
        );
        codeBlockLines = [];
        inCodeBlock = false;
      } else {
        flushList();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(rawLine);
      continue;
    }

    if (!line) {
      flushList();
      continue;
    }

    // Headings
    if (line.startsWith('# ')) {
      flushList();
      elements.push(
        <h1
          key={`h1-${elements.length}`}
          className="mt-1 mb-2 text-sm sm:text-base font-extrabold text-slate-900 tracking-tight border-b border-indigo-100 pb-1.5 flex items-center gap-1.5"
        >
          {renderInline(line.slice(2))}
        </h1>
      );
      continue;
    }

    if (line.startsWith('## ')) {
      flushList();
      elements.push(
        <h2
          key={`h2-${elements.length}`}
          className="mt-3 mb-1.5 text-xs sm:text-[13px] font-bold text-indigo-950 uppercase tracking-wide flex items-center gap-1.5"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
          {renderInline(line.slice(3))}
        </h2>
      );
      continue;
    }

    if (line.startsWith('### ')) {
      flushList();
      elements.push(
        <h3
          key={`h3-${elements.length}`}
          className="mt-2 mb-1 text-[11.5px] font-bold text-slate-800"
        >
          {renderInline(line.slice(4))}
        </h3>
      );
      continue;
    }

    // Unordered list
    if (line.startsWith('- ') || line.startsWith('* ')) {
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
      if (listType !== 'ol') {
        flushList();
        listType = 'ol';
      }
      currentList.push(olMatch[2]);
      continue;
    }

    // Standard paragraph line
    flushList();
    elements.push(
      <p
        key={`p-${elements.length}`}
        className="my-1.5 text-[11.5px] leading-relaxed text-slate-700"
      >
        {renderInline(line)}
      </p>
    );
  }

  flushList();

  return <div className={`space-y-0.5 text-left ${className}`}>{elements}</div>;
};

export default MarkdownRenderer;
