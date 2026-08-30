"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Shared dialog.
 *
 * Rendered through a portal to document.body, not in place. Every caller sits
 * inside a PanelCard, which Motion leaves a `transform` on — and a transformed
 * ancestor becomes the containing block for `position: fixed`, so an in-place
 * dialog is positioned against the card rather than the viewport and appears
 * clipped inside it.
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  size = "md",
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  size?: "md" | "lg";
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[rgba(6,10,16,0.5)] p-4 backdrop-blur-sm sm:p-8"
      onClick={onClose}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className={`panel my-auto w-full ${size === "lg" ? "max-w-5xl" : "max-w-2xl"} p-5 outline-none`}
      >
        <header className="flex items-start justify-between gap-4 border-b border-[var(--line)] pb-3">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">{title}</h2>
            {subtitle && <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="pressable shrink-0 border border-[var(--line-strong)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]"
          >
            Close
          </button>
        </header>
        <div className="mt-4 max-h-[70vh] overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body
  );
}
