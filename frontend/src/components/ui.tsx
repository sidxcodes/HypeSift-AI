"use client";

import clsx from "clsx";
import { Loader2 } from "lucide-react";
import { forwardRef, isValidElement } from "react";

export const cx = clsx;

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "accent" | "secondary" | "ghost" | "danger" | "onHero";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors duration-150 select-none",
        "disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer whitespace-nowrap",
        size === "sm" && "h-8 px-3 text-sm",
        size === "md" && "h-10 px-4 text-sm",
        size === "lg" && "h-12 px-6 text-base",
        variant === "primary" && "bg-primary text-on-primary hover:bg-primary-hover shadow-sm",
        variant === "accent" && "bg-accent text-white hover:bg-accent-hover shadow-[0_6px_18px_-6px_var(--accent)]",
        variant === "onHero" && "border border-white/70 text-white hover:bg-white/10",
        variant === "secondary" && "bg-surface border border-border text-text hover:bg-surface-2",
        variant === "ghost" && "text-muted hover:text-text hover:bg-surface-2",
        variant === "danger" && "bg-surface border border-border text-danger hover:bg-surface-2",
        className,
      )}
      {...rest}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

export function Card({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("rounded-2xl bg-surface shadow-card", className)} {...rest} />;
}

export function Badge({
  tone = "neutral",
  className,
  ...rest
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "primary" | "success" | "warning" | "danger" | "accent" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-surface-2 text-muted",
        tone === "primary" && "bg-primary-soft text-primary",
        tone === "success" && "bg-success/12 text-success",
        tone === "warning" && "bg-warning/12 text-warning",
        tone === "danger" && "bg-danger/12 text-danger",
        tone === "accent" && "bg-accent-soft text-accent",
        className,
      )}
      {...rest}
    />
  );
}

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cx(
        "h-10 w-full rounded-xl border border-border bg-surface px-3 text-sm text-text placeholder:text-muted",
        "focus:outline-none focus:ring-2 focus:ring-ring/40 focus:border-primary transition",
        className,
      )}
      {...rest}
    />
  );
});

export function Textarea({ className, ...rest }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted",
        "focus:outline-none focus:ring-2 focus:ring-ring/40 focus:border-primary transition resize-y",
        className,
      )}
      {...rest}
    />
  );
}

export function Select({
  value,
  onChange,
  options,
  className,
  ...rest
}: Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "onChange"> & {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cx(
        "h-10 w-full rounded-xl border border-border bg-surface px-3 text-sm text-text cursor-pointer",
        "focus:outline-none focus:ring-2 focus:ring-ring/40 focus:border-primary",
        className,
      )}
      {...rest}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex items-start justify-between gap-4 cursor-pointer py-1">
      <span className="text-sm">
        <span className="text-text">{label}</span>
        {hint && <span className="block text-xs text-muted mt-0.5">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label || "Toggle captions"}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors cursor-pointer",
          checked ? "bg-primary" : "bg-border",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform",
            checked && "translate-x-5",
          )}
        />
      </button>
    </label>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  // Single text/select/range controls get a real <label> so the name is announced and clickable.
  const control =
    isValidElement(children) &&
    (children.type === Input || children.type === Select || children.type === Textarea || children.type === "input");
  const Wrapper = control ? "label" : "div";
  return (
    <Wrapper className="block space-y-1.5">
      <span className="block text-xs font-medium text-muted uppercase tracking-wide">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted">{hint}</span>}
    </Wrapper>
  );
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div
      className={cx("h-2 w-full overflow-hidden rounded-full bg-surface-2", className)}
      role="progressbar"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${Math.max(2, value * 100)}%` }} />
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton rounded-xl", className)} />;
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode }[];
  className?: string;
}) {
  return (
    <div className={cx("inline-flex flex-wrap gap-1.5", className)} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-full px-3.5 h-8 text-[13px] font-medium transition cursor-pointer inline-flex items-center gap-1.5 border",
            value === o.value
              ? "border-primary bg-primary text-on-primary"
              : "border-border bg-surface text-muted hover:text-text hover:border-primary/40",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Outlined pill filters on the navy band ("All · Debits · Credits"). */
export function HeroChips<T extends string>({
  value,
  onChange,
  options,
  label = "Show only:",
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode }[];
  label?: string;
}) {
  return (
    <div className="inline-flex flex-wrap items-center gap-2 rounded-xl bg-white/8 px-3 py-2">
      <span className="text-xs text-white/75">{label}</span>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cx(
            "h-8 rounded-full border px-4 text-xs font-medium transition cursor-pointer",
            value === o.value ? "border-white bg-white/10 text-white" : "border-white/40 text-white/85 hover:border-white/80",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon: React.ReactNode; title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center py-16 px-6">
      <div className="mb-4 grid size-12 place-items-center rounded-2xl bg-primary-soft text-primary">{icon}</div>
      <h3 className="font-display text-lg font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-muted">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function scoreTone(score: number): "success" | "primary" | "warning" | "neutral" {
  if (score >= 80) return "success";
  if (score >= 65) return "primary";
  if (score >= 50) return "warning";
  return "neutral";
}
