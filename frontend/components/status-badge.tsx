/* Two different things, deliberately styled at different volumes.
 *
 * `SupportStatus` is the evidence contract — the one tri-state the product
 * exists to communicate, so it gets the colour. `RunStatus` is administrative
 * bookkeeping: quiet by default, loud only when something genuinely failed or
 * was withheld for lack of data.
 */

const SUPPORT_STYLES: Record<string, string> = {
  SUPPORTED: "border-settled/35 bg-settled-soft text-settled",
  PARTIAL: "border-partial/35 bg-partial-soft text-partial",
  UNKNOWN: "border-open/30 bg-open-soft text-open",
};

const SUPPORT_MEANING: Record<string, string> = {
  SUPPORTED: "Specific evidence of this cause is present in the run.",
  PARTIAL: "Only observational or directional evidence supports this claim.",
  UNKNOWN:
    "The evidence cannot carry this claim. It is published as unknown and does not account for any explained loss.",
};

export function SupportStatus({
  status,
  showMeaning = false,
}: {
  status: string;
  showMeaning?: boolean;
}) {
  const value = SUPPORT_STYLES[status] ? status : "UNKNOWN";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-[2px] border px-2 py-[3px] font-mono text-[10px] font-semibold tracking-[0.08em] uppercase ${SUPPORT_STYLES[value]}`}
      title={SUPPORT_MEANING[value]}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {value}
      {showMeaning && <span className="sr-only"> — {SUPPORT_MEANING[value]}</span>}
    </span>
  );
}

const RUN_LOUD: Record<string, string> = {
  FAILED: "border-alarm/35 bg-alarm-soft text-alarm",
  DISPATCH_FAILED: "border-alarm/35 bg-alarm-soft text-alarm",
  NEEDS_DATA: "border-partial/35 bg-partial-soft text-partial",
  CANCELLED: "border-rule-2 bg-paper-2 text-ink-3",
};

export function RunStatus({ status }: { status: string | null | undefined }) {
  const value = status || "UNKNOWN";
  const tone =
    RUN_LOUD[value] ?? "border-rule-2 bg-paper-2 text-ink-2";
  return (
    <span
      className={`inline-flex items-center rounded-[2px] border px-2 py-[3px] font-mono text-[10px] font-semibold tracking-[0.08em] uppercase ${tone}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

/** Kept as the general-purpose chip for run and incident states. */
export const StatusBadge = RunStatus;
