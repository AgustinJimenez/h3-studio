import { Check, Circle, X } from "lucide-react";
import type { Status } from "../schemas";

const STATUS_ICON: Record<string, typeof Check> = {
  done: Check,
  failed: X,
  queued: Circle,
  draft: Circle,
  none: Circle,
};

const STATUS_BG: Record<string, string> = {
  draft: "bg-status-draft",
  queued: "bg-status-queued",
  running: "bg-status-running",
  done: "bg-status-done",
  failed: "bg-status-failed",
};

export default function StatusBadge({ status, label }: { status: Status | string; label?: string }) {
  const text = label ?? status;
  const Icon = STATUS_ICON[status] ?? Circle;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs uppercase text-white ${STATUS_BG[status] ?? "bg-status-draft"}`}
    >
      {status === "running" ? <span className="status-spinner" /> : <Icon size={11} />}
      {text}
    </span>
  );
}
