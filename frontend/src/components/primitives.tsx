import { X } from "lucide-react";
import {
  cloneElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type RefObject,
  type SelectHTMLAttributes,
} from "react";

export function Button({
  children,
  className = "",
  disabled,
  loading = false,
  variant = "default",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  variant?: "default" | "primary" | "ghost" | "danger";
}) {
  return <button
    aria-busy={loading || undefined}
    className={`button ${variant === "default" ? "" : variant} ${className}`.trim()}
    disabled={disabled || loading}
    {...props}
  >{children}</button>;
}

export function IconButton({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`icon-button ${className}`.trim()} {...props} />;
}

export function Field({ label, helper, error, children }: {
  label: string;
  helper?: string;
  error?: string;
  children: ReactNode;
}) {
  return <label className={`field ${error ? "invalid" : ""}`}>
    <span>{label}</span>
    {children}
    {error ? <small className="field-error">{error}</small> : helper ? <small>{helper}</small> : null}
  </label>;
}

export function TextField({ label, helper, error, id, className = "", ...props }: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  helper?: string;
  error?: string;
}) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const detailId = `${fieldId}-detail`;
  return <div className={`field ${error ? "invalid" : ""} ${className}`.trim()}>
    <label htmlFor={fieldId}>{label}</label>
    <input
      aria-describedby={helper || error ? detailId : undefined}
      aria-invalid={error ? true : undefined}
      id={fieldId}
      {...props}
    />
    {error ? <small className="field-error" id={detailId}>{error}</small> : helper ? <small id={detailId}>{helper}</small> : null}
  </div>;
}

export function SelectField({ label, helper, error, id, className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  helper?: string;
  error?: string;
}) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const detailId = `${fieldId}-detail`;
  return <div className={`field ${error ? "invalid" : ""} ${className}`.trim()}>
    <label htmlFor={fieldId}>{label}</label>
    <select
      aria-describedby={helper || error ? detailId : undefined}
      aria-invalid={error ? true : undefined}
      id={fieldId}
      {...props}
    >{children}</select>
    {error ? <small className="field-error" id={detailId}>{error}</small> : helper ? <small id={detailId}>{helper}</small> : null}
  </div>;
}

export function Badge({ children, className = "", tone = "neutral" }: {
  children: ReactNode;
  className?: string;
  tone?: "neutral" | "info" | "success" | "warning" | "critical";
}) {
  return <span className={`badge badge-${tone} ${className}`.trim()}>{children}</span>;
}

export function Tooltip({ label, children }: {
  label: string;
  children: ReactElement<Record<string, unknown>>;
}) {
  const id = useId();
  const describedBy = [children.props["aria-describedby"], id].filter(Boolean).join(" ");
  return <span className="tooltip">
    {cloneElement(children, { "aria-describedby": describedBy })}
    <span className="tooltip-content" id={id} role="tooltip">{label}</span>
  </span>;
}

export function Popover({ label, trigger, children, className = "" }: {
  label: string;
  trigger: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return <div className={`popover ${className}`.trim()} ref={rootRef}>
    <button
      aria-expanded={open}
      aria-haspopup="dialog"
      aria-label={label}
      className="popover-trigger icon-button"
      onClick={() => setOpen((current) => !current)}
      ref={triggerRef}
      type="button"
    >{trigger}</button>
    {open ? <section aria-label={label} className="popover-content" role="dialog">{children}</section> : null}
  </div>;
}

export function Dialog({ open, onClose, title, eyebrow, children, actions, closeLabel = "Close", className = "" }: {
  open: boolean;
  onClose: () => void;
  title: string;
  eyebrow?: string;
  children: ReactNode;
  actions?: ReactNode;
  closeLabel?: string;
  className?: string;
}) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  useModalFocus(open, onClose, panelRef);
  if (!open) return null;
  return <div className="modal-layer" onMouseDown={(event) => {
    if (event.currentTarget === event.target) onClose();
  }} role="presentation">
    <section aria-labelledby={titleId} aria-modal="true" className={`dialog-surface ${className}`.trim()} ref={panelRef} role="dialog">
      <button aria-label={closeLabel} className="dialog-close icon-button" data-autofocus onClick={onClose} type="button"><X aria-hidden="true" size={18} /></button>
      {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
      <h2 id={titleId}>{title}</h2>
      <div className="dialog-body">{children}</div>
      {actions ? <div className="dialog-actions">{actions}</div> : null}
    </section>
  </div>;
}

export function Drawer({ open, onClose, label, closeLabel = "Close", children, returnFocusRef, side = "left", title }: {
  open: boolean;
  onClose: () => void;
  label: string;
  closeLabel?: string;
  children: ReactNode;
  returnFocusRef?: RefObject<HTMLElement | null>;
  side?: "left" | "right";
  title?: string;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();
  useModalFocus(open, onClose, panelRef, returnFocusRef);
  if (!open) return null;
  return <div className="drawer-layer" role="presentation">
    <div className="drawer-backdrop" onMouseDown={onClose} />
    <section {...(title ? { "aria-labelledby": titleId } : { "aria-label": label })} aria-modal="true" className={`drawer-panel drawer-${side}`} ref={panelRef} role="dialog">
      <button aria-label={closeLabel} className="drawer-close icon-button" data-autofocus onClick={onClose} type="button"><X aria-hidden="true" size={19} /></button>
      {title ? <h2 className="drawer-title" id={titleId}>{title}</h2> : null}
      {children}
    </section>
  </div>;
}

function useModalFocus(
  open: boolean,
  onClose: () => void,
  panelRef: RefObject<HTMLElement | null>,
  explicitReturnFocusRef?: RefObject<HTMLElement | null>,
): void {
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previousFocus = explicitReturnFocusRef?.current ?? document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel?.querySelector<HTMLElement>("[data-autofocus], button, a, input, select, textarea, [tabindex]:not([tabindex='-1'])")?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const focusable = [...panel.querySelectorAll<HTMLElement>(
        "button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])",
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [explicitReturnFocusRef, open, panelRef]);
}
