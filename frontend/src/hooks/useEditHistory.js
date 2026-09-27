import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Undo/redo over the editor's pending-edit map.
 *
 * The map is a plain `{key: editRecord}` object, so a history entry is just a
 * shallow snapshot of it. Snapshots are cheap (one entry per edited block) and
 * immutable by convention - every mutation goes through `applyEdits`, which
 * produces a new object - which is what makes storing the old reference safe.
 *
 * Two behaviours matter for a text editor and are easy to get wrong:
 *
 * 1. **Coalescing.** Typing produces one change event per keystroke. Pushing a
 *    snapshot each time would make Ctrl+Z peel off single characters. Changes to
 *    the *same key* within `coalesceMs` are merged into one undo step, so undo
 *    jumps back to the state before that run of typing. Switching to a different
 *    block, or pausing, closes the step immediately.
 *
 * 2. **No-op suppression.** A snapshot is only pushed when the map actually
 *    changed, so undo never lands on an identical state and appears stuck.
 *
 * The newest state is always `present` rather than living in the undo stack, so
 * the stack length is exactly "how many steps back you can go".
 */
const MAX_HISTORY = 100;
const COALESCE_MS = 600;

const shallowEqual = (a, b) => {
  if (a === b) return true;
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) return false;
  for (const key of aKeys) {
    if (a[key] !== b[key]) return false;
  }
  return true;
};

export const useEditHistory = (initialEdits = {}, { coalesceMs = COALESCE_MS } = {}) => {
  const [edits, setEditsState] = useState(() => initialEdits || {});
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const undoStack = useRef([]);
  const redoStack = useRef([]);
  const lastTouchedKey = useRef(null);
  const lastTouchedAt = useRef(0);
  // Bumped while undo()/redo() run so the resulting setState is not itself
  // recorded as a fresh history entry (which would make redo impossible).
  const replaying = useRef(false);

  const syncFlags = useCallback(() => {
    setCanUndo(undoStack.current.length > 0);
    setCanRedo(redoStack.current.length > 0);
  }, []);

  const setEdits = useCallback(
    (updater, touchedKey) => {
      setEditsState((current) => {
        const next = typeof updater === 'function' ? updater(current) : updater;
        if (next === current || shallowEqual(next, current)) {
          return current;
        }

        if (replaying.current) {
          return next;
        }

        const now = Date.now();
        const coalesce =
          touchedKey != null &&
          touchedKey === lastTouchedKey.current &&
          now - lastTouchedAt.current < coalesceMs;

        // Only push a step when this change starts a new run of edits, so a
        // burst of keystrokes in one block collapses into a single undo step.
        if (!coalesce) {
          undoStack.current.push(current);
          if (undoStack.current.length > MAX_HISTORY) {
            undoStack.current.shift();
          }
          redoStack.current = [];
        }
        lastTouchedKey.current = touchedKey ?? null;
        lastTouchedAt.current = now;

        queueMicrotask(syncFlags);
        return next;
      });
    },
    [coalesceMs, syncFlags]
  );

  const undo = useCallback(() => {
    const previous = undoStack.current.pop();
    if (previous === undefined) return false;
    replaying.current = true;
    redoStack.current.push(edits);
    lastTouchedKey.current = null;
    setEditsState(previous);
    replaying.current = false;
    syncFlags();
    return true;
  }, [edits, syncFlags]);

  const redo = useCallback(() => {
    const next = redoStack.current.pop();
    if (next === undefined) return false;
    replaying.current = true;
    undoStack.current.push(edits);
    lastTouchedKey.current = null;
    setEditsState(next);
    replaying.current = false;
    syncFlags();
    return true;
  }, [edits, syncFlags]);

  /**
   * Replace the whole map (save, discard, reload). Recorded as one undo step so
   * "discard everything" is itself reversible.
   */
  const replaceAll = useCallback(
    (next) => {
      setEditsState((current) => {
        if (shallowEqual(current, next)) return current;
        if (!replaying.current) {
          undoStack.current.push(current);
          if (undoStack.current.length > MAX_HISTORY) undoStack.current.shift();
          redoStack.current = [];
          lastTouchedKey.current = null;
          queueMicrotask(syncFlags);
        }
        return next;
      });
    },
    [syncFlags]
  );

  /** Re-seed from the server without recording a step (document reloaded). */
  const reset = useCallback((next) => {
    undoStack.current = [];
    redoStack.current = [];
    lastTouchedKey.current = null;
    setEditsState(next || {});
    setCanUndo(false);
    setCanRedo(false);
  }, []);

  const undoDepth = undoStack.current.length;
  const redoDepth = redoStack.current.length;

  return useMemo(
    () => ({ edits, setEdits, replaceAll, reset, undo, redo, canUndo, canRedo, undoDepth, redoDepth }),
    [edits, setEdits, replaceAll, reset, undo, redo, canUndo, canRedo, undoDepth, redoDepth]
  );
};

/**
 * Wire Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z (plus Ctrl+Y) to undo/redo.
 *
 * Listens on the window in the capture phase so the shortcut still works while a
 * textarea has focus, but stands down whenever the user is typing somewhere
 * that has its own native undo stack (an <input>/<textarea>/contenteditable).
 * Those fields are short, one-shot composers rather than the document, so
 * hijacking their undo would fight the browser.
 */
export const useUndoRedoShortcuts = ({ undo, redo, enabled = true }) => {
  useEffect(() => {
    if (!enabled) return undefined;

    const isNativeUndoField = (target) => {
      if (!target || !target.tagName) return false;
      const tag = target.tagName.toLowerCase();
      return tag === 'input' || tag === 'textarea' || target.isContentEditable === true;
    };

    const onKeyDown = (event) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      const isUndo = key === 'z' && !event.shiftKey;
      const isRedo = (key === 'z' && event.shiftKey) || key === 'y';
      if (!isUndo && !isRedo) return;
      if (isNativeUndoField(event.target)) return;

      event.preventDefault();
      if (isUndo) {
        undo();
      } else {
        redo();
      }
    };

    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [undo, redo, enabled]);
};
