"use client";

/**
 * The shortcut hint panel.
 *
 * The old system kept a permanent strip of shortcuts on screen, which is how
 * staff learned them without training. This shows the same thing on demand
 * (press ?) plus a always-visible reminder that the panel exists — a
 * permanent strip costs vertical space the counter screen does not have, but
 * a hidden feature nobody discovers is the same as no feature.
 */
import { Keyboard, X } from "lucide-react";
import { formatCombo, useKeyboard } from "@/components/keyboard/keyboard-provider";
import { cn } from "@/lib/utils";

export function ShortcutHints() {
  const { shortcuts, hintsOpen, setHintsOpen, isMac } = useKeyboard();

  return (
    <>
      {/* The discoverability nudge. Small, fixed, out of the way. */}
      {!hintsOpen && (
        <button
          type="button"
          onClick={() => setHintsOpen(true)}
          className="fixed bottom-3 right-3 z-40 flex items-center gap-1.5 rounded-full border
                     border-pine/15 bg-white/90 px-3 py-1.5 text-[11px] text-ink-muted
                     shadow-card backdrop-blur transition hover:border-pine/40 hover:text-pine"
          aria-label="Show keyboard shortcuts"
        >
          <Keyboard className="h-3.5 w-3.5" />
          <kbd className="rounded border border-border px-1 font-sans">?</kbd>
          <span className="hidden sm:inline">shortcuts</span>
        </button>
      )}

      {hintsOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-ink/20 p-3 sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-label="Keyboard shortcuts"
          onClick={() => setHintsOpen(false)}
        >
          <div
            className="max-h-[70vh] w-full max-w-lg overflow-y-auto rounded-2xl border
                       border-pine/10 bg-white shadow-lift"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sticky top-0 flex items-center gap-2 border-b border-pine/10
                            bg-white px-4 py-3">
              <Keyboard className="h-4 w-4 text-pine" />
              <h2 className="font-display text-sm font-semibold text-pine">
                Keyboard shortcuts
              </h2>
              <button
                type="button"
                onClick={() => setHintsOpen(false)}
                className="ml-auto rounded p-1 text-ink-faint transition hover:text-clay"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <ul className="divide-y divide-border">
              {shortcuts.length === 0 && (
                <li className="px-4 py-6 text-center text-xs text-ink-faint">
                  No shortcuts on this screen.
                </li>
              )}
              {shortcuts.map((shortcut) => (
                <li
                  key={shortcut.combo}
                  className="flex items-center gap-3 px-4 py-2.5 text-sm"
                >
                  <span className="text-ink">{shortcut.label}</span>
                  <kbd
                    className={cn(
                      "tabular ml-auto shrink-0 rounded border border-border border-b-2",
                      "bg-mint px-2 py-0.5 font-sans text-[11px] font-medium text-pine"
                    )}
                  >
                    {formatCombo(shortcut.combo, isMac)}
                  </kbd>
                </li>
              ))}
            </ul>

            <p className="border-t border-pine/10 px-4 py-2.5 text-[11px] text-ink-faint">
              Press <kbd className="rounded border border-border px-1">?</kbd> to open this,
              or <kbd className="rounded border border-border px-1">Ctrl</kbd> +
              <kbd className="rounded border border-border px-1">/</kbd> while your cursor is in
              a field. Plain-key shortcuts stay out of the way while you are typing.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
