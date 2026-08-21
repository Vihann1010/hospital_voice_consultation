"use client";

/**
 * Minimal toast system.
 *
 * Actions that leave the building — sending a prescription to a patient,
 * issuing an order — deserve visible confirmation rather than a silent state
 * change, and failures need to be seen even when they happen off-screen.
 */
import { createContext, useCallback, useContext, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info";

interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

interface ToastContextValue {
  notify: (toast: Omit<Toast, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
}

const ToastContext = createContext<ToastContextValue>({
  notify: () => undefined,
  success: () => undefined,
  error: () => undefined,
});

export const useToast = () => useContext(ToastContext);

const TONE_STYLES: Record<ToastTone, string> = {
  success: "border-pine/30 bg-white",
  error: "border-clay/40 bg-white",
  info: "border-border bg-white",
};

const TONE_ICONS: Record<ToastTone, React.ComponentType<{ className?: string }>> = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
};

let toastCounter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = ++toastCounter;
      setToasts((current) => [...current, { ...toast, id }]);
      // Errors linger; successes get out of the way.
      setTimeout(() => dismiss(id), toast.tone === "error" ? 8000 : 4000);
    },
    [dismiss]
  );

  const value: ToastContextValue = {
    notify,
    success: (title, description) => notify({ tone: "success", title, description }),
    error: (title, description) => notify({ tone: "error", title, description }),
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2"
        role="status"
        aria-live="polite"
      >
        <AnimatePresence initial={false}>
          {toasts.map((toast) => {
            const Icon = TONE_ICONS[toast.tone];
            return (
              <motion.div
                key={toast.id}
                initial={{ opacity: 0, y: 16, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 24, transition: { duration: 0.15 } }}
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
                className={cn(
                  "pointer-events-auto flex items-start gap-3 rounded-xl border p-3.5 shadow-lift",
                  TONE_STYLES[toast.tone]
                )}
              >
                <Icon
                  className={cn(
                    "mt-0.5 h-4 w-4 shrink-0",
                    toast.tone === "success" && "text-pine",
                    toast.tone === "error" && "text-clay",
                    toast.tone === "info" && "text-ink-muted"
                  )}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink">{toast.title}</p>
                  {toast.description && (
                    <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
                      {toast.description}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => dismiss(toast.id)}
                  className="shrink-0 rounded p-0.5 text-ink-faint transition hover:bg-mint hover:text-pine"
                  aria-label="Dismiss"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
