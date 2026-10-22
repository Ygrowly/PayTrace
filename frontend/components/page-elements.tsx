import { Icon } from "@/components/icons";

/* Shared surfaces. Square-ish, hairline-ruled, quiet — the colour budget is
   spent on the three evidence states, not on chrome. */

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
  meta,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
    <header className="border-b border-rule-2 pb-6">
      <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <div className="eyebrow">{eyebrow}</div>
          <h1 className="display mt-2 text-[27px] leading-tight font-semibold text-ink">
            {title}
          </h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-6 text-ink-2">
            {description}
          </p>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {meta && <div className="mt-5">{meta}</div>}
    </header>
  );
}

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
  bodyClassName = "",
}: {
  title: string;
  eyebrow?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={`rounded-[2px] border border-rule bg-surface ${className}`}
    >
      <div className="flex items-start justify-between gap-4 border-b border-rule px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="display text-[14px] font-semibold text-ink">{title}</h2>
          {eyebrow && <p className="eyebrow mt-1">{eyebrow}</p>}
        </div>
        {action}
      </div>
      <div className={`px-5 py-4 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div
      aria-live="polite"
      className="flex min-h-32 items-center justify-center gap-3 rounded-[2px] border border-rule bg-surface text-[13px] text-ink-3"
    >
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-rule-2 border-t-petrol" />
      {label}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      aria-live="assertive"
      className="flex items-start gap-3 rounded-[2px] border border-alarm/30 bg-alarm-soft p-4 text-[13px]"
    >
      <Icon name="triangle" size={16} />
      <div className="flex-1 text-alarm">
        <p className="font-semibold">This view could not be loaded</p>
        <p className="mt-1 opacity-80">{message}</p>
      </div>
      {onRetry && (
        <button
          className="shrink-0 cursor-pointer rounded-[2px] border border-alarm/30 bg-surface px-3 py-1.5 text-[11px] font-semibold text-alarm transition-colors hover:bg-alarm-soft"
          onClick={onRetry}
          type="button"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-[2px] border border-dashed border-rule-2 bg-surface px-6 text-center">
      <span className="flex h-9 w-9 items-center justify-center rounded-full border border-rule text-ink-3">
        <Icon name="search" size={16} />
      </span>
      <h2 className="display mt-4 text-[14px] font-semibold text-ink">{title}</h2>
      <p className="mt-1.5 max-w-md text-[12px] leading-5 text-ink-3">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Primary and secondary buttons, sized for the ruled layout. */
export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  href,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "quiet";
  disabled?: boolean;
  type?: "button" | "submit";
  href?: string;
}) {
  const base =
    "inline-flex items-center gap-2 rounded-[2px] px-3.5 py-2 text-[12px] font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50";
  const variants = {
    primary: "bg-petrol text-white hover:bg-petrol-2",
    secondary: "border border-rule-2 bg-surface text-ink hover:border-ink-3",
    quiet: "text-ink-2 hover:bg-paper-2 hover:text-ink",
  };
  const className = `${base} ${variants[variant]}`;

  if (href) {
    return (
      <a className={className} href={href}>
        {children}
      </a>
    );
  }
  return (
    <button
      className={`${className} cursor-pointer`}
      disabled={disabled}
      onClick={onClick}
      type={type}
    >
      {children}
    </button>
  );
}
