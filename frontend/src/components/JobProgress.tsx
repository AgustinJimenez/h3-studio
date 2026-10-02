import type { ActiveJob } from "../schemas";

// Sampling reports real steps; the other stages (loading, decoding) have no count, so the bar just pulses with a label.
export default function JobProgress({ progress }: { progress: ActiveJob["progress"] }) {
  const pct = progress?.fraction != null ? Math.round(progress.fraction * 100) : null;
  return (
    <span className="mt-1 flex flex-col gap-0.5">
      <span className="h-1.5 w-full overflow-hidden rounded bg-bg">
        <span
          className={`block h-full rounded bg-accent ${pct == null ? "w-1/3 animate-pulse" : "transition-all"}`}
          style={pct == null ? undefined : { width: `${pct}%` }}
        />
      </span>
      <span className="text-[10px] opacity-70">
        {progress?.stage ?? "Starting"}
        {progress?.value != null && progress?.max ? ` · step ${progress.value}/${progress.max} (${pct}%)` : ""}
      </span>
    </span>
  );
}
