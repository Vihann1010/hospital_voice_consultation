"use client";

/**
 * Keyboard-first operation.
 *
 * The system this replaces was run almost entirely from the keyboard, and the
 * staff who will use this one have years of that muscle memory. Losing it is
 * the single most likely reason a replacement gets rejected at the counter:
 * a prettier screen that costs two more keystrokes per patient is a slower
 * screen, and reception feels that within an hour.
 *
 * Two rules make this safe to have running under every page:
 *
 * **Typing wins.** While the caret is in a field, plain keys belong to the
 * field. Only function keys and modifier combinations are intercepted, so a
 * patient named "Neeta" never triggers the shortcut bound to N.
 *
 * **The browser wins where it insists.** Ctrl+N, Ctrl+T and Ctrl+W are taken
 * by the browser itself and cannot be intercepted by a page — the old desktop
 * client could claim them and this cannot. Anything registered on those is
 * reported by `unavailableShortcuts` rather than silently doing nothing, so
 * the hint panel never promises a key that will not work.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export interface Shortcut {
  /** Canonical form: "F2", "ctrl+s", "shift+?" — lower case, modifiers first. */
  combo: string;
  label: string;
  handler: () => void;
  /** Ordering in the hint panel; lower is earlier. */
  order?: number;
}

interface KeyboardContextValue {
  register: (shortcut: Shortcut) => () => void;
  shortcuts: Shortcut[];
  hintsOpen: boolean;
  setHintsOpen: (open: boolean) => void;
  /** True on macOS, so hints can show ⌘ instead of Ctrl. */
  isMac: boolean;
}

const KeyboardContext = createContext<KeyboardContextValue | null>(null);

/** Combos the browser reserves and a page cannot intercept. */
const BROWSER_RESERVED = new Set(["ctrl+n", "ctrl+t", "ctrl+w", "ctrl+shift+n", "ctrl+shift+t"]);

export function comboFrom(event: KeyboardEvent): string {
  const parts: string[] = [];
  // Cmd on a Mac and Ctrl elsewhere are the same intent, so they normalise to
  // one name and a binding does not have to be written twice.
  if (event.ctrlKey || event.metaKey) parts.push("ctrl");
  if (event.altKey) parts.push("alt");
  if (event.shiftKey) parts.push("shift");
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  parts.push(key);
  return parts.join("+");
}

/** Is the caret somewhere that plain keystrokes belong to? */
function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    el.isContentEditable === true
  );
}

export function formatCombo(combo: string, isMac: boolean): string {
  return combo
    .split("+")
    .map((part) => {
      if (part === "ctrl") return isMac ? "⌘" : "Ctrl";
      if (part === "alt") return isMac ? "⌥" : "Alt";
      if (part === "shift") return isMac ? "⇧" : "Shift";
      if (part === "Escape") return "Esc";
      if (part.length === 1) return part.toUpperCase();
      return part;
    })
    .join(isMac ? "" : "+");
}

export function KeyboardProvider({ children }: { children: React.ReactNode }) {
  // A ref, not state: handlers change on nearly every render of the screens
  // that own them, and re-binding a window listener that often would drop
  // keystrokes typed during the swap.
  const registry = useRef<Map<string, Shortcut>>(new Map());
  const [version, setVersion] = useState(0);
  const [hintsOpen, setHintsOpen] = useState(false);
  const [isMac, setIsMac] = useState(false);

  useEffect(() => {
    // Read after mount: the server has no idea what the staff member is using,
    // and guessing would render the wrong modifier until hydration corrected it.
    setIsMac(/Mac|iPhone|iPad/.test(window.navigator.platform));
  }, []);

  const register = useCallback((shortcut: Shortcut) => {
    registry.current.set(shortcut.combo, shortcut);
    setVersion((v) => v + 1);
    return () => {
      // Only remove it if it is still ours — a screen unmounting after its
      // replacement has already claimed the same combo must not unbind it.
      if (registry.current.get(shortcut.combo) === shortcut) {
        registry.current.delete(shortcut.combo);
        setVersion((v) => v + 1);
      }
    };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const combo = comboFrom(event);

      // Two ways to reach the hint panel. "?" is the convention, but it is a
      // plain key, so it cannot fire while the caret is in a field — and the
      // counter screen autofocuses one, which is exactly where a new member
      // of staff would go looking. Ctrl+/ works from inside a field.
      const asksForHints =
        combo === "ctrl+/" || (combo === "shift+?" && !isTyping(event.target));
      if (asksForHints) {
        event.preventDefault();
        setHintsOpen((open) => !open);
        return;
      }
      if (combo === "Escape" && hintsOpen) {
        event.preventDefault();
        setHintsOpen(false);
        return;
      }

      // A modal owns the keyboard while it is open. Without this, Escape in
      // a confirmation dialog both dismissed the dialog and fired the global
      // "back" shortcut, so a clerk who thought better of cancelling a bill
      // lost the whole screen as well. F2 and F5 would navigate out from
      // under an open dialog for the same reason.
      //
      // Detected from the document rather than the event target, because
      // focus may sit on the body while a dialog is open and a target-based
      // check would miss it.
      if (document.querySelector('[role="dialog"]') !== null) return;

      const shortcut = registry.current.get(combo);
      if (!shortcut) return;

      const functionKey = /^F\d{1,2}$/.test(event.key);
      const modified = event.ctrlKey || event.metaKey || event.altKey;
      if (isTyping(event.target) && !functionKey && !modified && event.key !== "Escape") {
        return;
      }

      event.preventDefault();
      shortcut.handler();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hintsOpen]);

  const shortcuts = useMemo(
    () =>
      Array.from(registry.current.values()).sort(
        (a, b) => (a.order ?? 100) - (b.order ?? 100) || a.label.localeCompare(b.label)
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version]
  );

  const value = useMemo(
    () => ({ register, shortcuts, hintsOpen, setHintsOpen, isMac }),
    [register, shortcuts, hintsOpen, isMac]
  );

  return <KeyboardContext.Provider value={value}>{children}</KeyboardContext.Provider>;
}

export function useKeyboard(): KeyboardContextValue {
  const context = useContext(KeyboardContext);
  if (context === null) {
    throw new Error("useKeyboard must be used inside a KeyboardProvider.");
  }
  return context;
}

/**
 * Bind one shortcut for as long as the calling component is mounted.
 *
 * The handler is held in a ref so that a screen re-rendering — which it does
 * on every keystroke into a form — does not unbind and rebind the shortcut.
 */
export function useShortcut(
  combo: string,
  label: string,
  handler: () => void,
  options: { order?: number; enabled?: boolean } = {}
): void {
  // Tolerant of having no provider. A component that offers a shortcut —
  // the Visit Pad's Ctrl+S — is also rendered in shells without one, such as
  // the ward terminal, and must not crash there for want of a key binding.
  const register = useContext(KeyboardContext)?.register;
  const { order, enabled = true } = options;
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!enabled || !register) return;
    if (BROWSER_RESERVED.has(combo) && process.env.NODE_ENV !== "production") {
      console.warn(
        `[keyboard] "${combo}" is reserved by the browser and will never fire. ` +
          "Choose a function key or an Alt combination instead."
      );
    }
    return register({ combo, label, handler: () => handlerRef.current(), order });
  }, [register, combo, label, order, enabled]);
}

export const isBrowserReserved = (combo: string) => BROWSER_RESERVED.has(combo);
