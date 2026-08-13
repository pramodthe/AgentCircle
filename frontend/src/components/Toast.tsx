import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

/**
 * One channel for "that worked" and "that failed".
 *
 * Before this, a write either rendered an inline `.auth-error`, or a `.thread-notice`
 * that pushed the page down, or nothing at all — so the same class of event looked
 * different on every surface and some actions gave no answer whatsoever. Errors that
 * belong *to a field* still stay inline; this is for the result of an action you just
 * took, which is the case where an inline message is easy to miss because you are
 * still looking at the button.
 */

type ToastKind = "ok" | "error" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  toast: (message: string, kind?: ToastKind) => void;
  /** Runs an action, reports the outcome, and hands back whether it succeeded. */
  report: <T>(action: () => Promise<T>, success?: string) => Promise<T | undefined>;
}

const ToastContext = createContext<ToastApi | null>(null);

const ICONS = { ok: CircleCheck, error: CircleAlert, info: Info } as const;

// Long enough to read a sentence, short enough not to sit over the next thing you do.
const DISMISS_AFTER = { ok: 3200, info: 3800, error: 6000 } as const;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, kind: ToastKind = "info") => {
      const id = nextId.current++;
      // Cap the stack so a burst of failures cannot cover the page it is reporting on.
      setToasts((current) => [...current.slice(-2), { id, kind, message }]);
      timers.current.push(window.setTimeout(() => dismiss(id), DISMISS_AFTER[kind]));
    },
    [dismiss],
  );

  const report = useCallback(
    async <T,>(action: () => Promise<T>, success?: string) => {
      try {
        const value = await action();
        if (success) toast(success, "ok");
        return value;
      } catch (caught) {
        toast(caught instanceof Error ? caught.message : "Something went wrong", "error");
        return undefined;
      }
    },
    [toast],
  );

  const api = useMemo(() => ({ toast, report }), [toast, report]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* aria-live so the outcome reaches a screen reader too — the visual toast is
          off to the side of wherever focus actually is. */}
      <div className="toast-host" role="status" aria-live="polite">
        {toasts.map(({ id, kind, message }) => {
          const Icon = ICONS[kind];
          return (
            <div className={`toast-item ${kind}`} key={id}>
              <Icon size={16} />
              <span>{message}</span>
              <button type="button" onClick={() => dismiss(id)} aria-label="Dismiss">
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>");
  return context;
}
