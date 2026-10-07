/**
 * Extracts structured runs (bold, italic, underline, color, etc.) from a contentEditable DOM element.
 */
export function extractRunsFromElement(rootElement) {
  if (!rootElement) return [];
  const runs = [];

  function traverse(node, currentStyle = {}) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent;
      if (text) {
        runs.push({
          text,
          bold: currentStyle.bold || false,
          italic: currentStyle.italic || false,
          underline: currentStyle.underline || false,
          strike: currentStyle.strike || false,
          color: currentStyle.color || null,
          font_size: currentStyle.fontSize || null,
          font_name: currentStyle.fontName || null,
          highlight: currentStyle.highlight || false,
        });
      }
      return;
    }

    if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node;
      const computed = window.getComputedStyle(el);
      const tag = el.tagName.toUpperCase();

      const isBold =
        currentStyle.bold ||
        tag === 'B' ||
        tag === 'STRONG' ||
        parseInt(computed.fontWeight || '400', 10) >= 600;

      const isItalic =
        currentStyle.italic ||
        tag === 'I' ||
        tag === 'EM' ||
        computed.fontStyle === 'italic';

      const textDec = computed.textDecorationLine || computed.textDecoration || '';
      const isUnderline =
        currentStyle.underline ||
        tag === 'U' ||
        textDec.includes('underline');

      const isStrike =
        currentStyle.strike ||
        tag === 'S' ||
        tag === 'STRIKE' ||
        tag === 'DEL' ||
        textDec.includes('line-through');

      const isHighlight =
        currentStyle.highlight ||
        tag === 'MARK' ||
        computed.backgroundColor.includes('254, 240, 138') ||
        computed.backgroundColor.includes('yellow');

      const elColor = el.style.color || null;
      const elFontSize = el.style.fontSize ? parseFloat(el.style.fontSize) : null;
      const elFontFamily = el.style.fontFamily || null;

      const newStyle = {
        bold: isBold,
        italic: isItalic,
        underline: isUnderline,
        strike: isStrike,
        color: elColor || currentStyle.color,
        fontSize: elFontSize || currentStyle.fontSize,
        fontName: elFontFamily || currentStyle.fontName,
        highlight: isHighlight,
      };

      for (let child = node.firstChild; child; child = child.nextSibling) {
        traverse(child, newStyle);
      }
    }
  }

  traverse(rootElement);

  // Merge adjacent runs that have identical formatting
  if (runs.length <= 1) return runs;
  const merged = [runs[0]];
  for (let i = 1; i < runs.length; i++) {
    const prev = merged[merged.length - 1];
    const curr = runs[i];
    if (
      prev.bold === curr.bold &&
      prev.italic === curr.italic &&
      prev.underline === curr.underline &&
      prev.strike === curr.strike &&
      prev.color === curr.color &&
      prev.font_size === curr.font_size &&
      prev.font_name === curr.font_name &&
      prev.highlight === curr.highlight
    ) {
      prev.text += curr.text;
    } else {
      merged.push(curr);
    }
  }

  return merged;
}
