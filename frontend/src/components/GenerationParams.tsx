import { JsonView, darkStyles } from "react-json-view-lite";
import "react-json-view-lite/dist/index.css";

export default function GenerationParams({
  settings,
  durationSeconds,
}: {
  settings: Record<string, unknown> | null | undefined;
  durationSeconds?: number | null;
}) {
  if (!settings) return null;
  return (
    <details className="mt-2 rounded border border-border bg-bg-alt p-2">
      <summary className="cursor-pointer font-semibold text-text-h">
        Generation parameters
        {durationSeconds != null && <span className="ml-1 font-normal opacity-75">— took {durationSeconds}s</span>}
      </summary>
      <div className="mt-2 max-h-[300px] overflow-auto text-xs">
        <JsonView data={settings} style={darkStyles} shouldExpandNode={(level) => level < 1} />
      </div>
    </details>
  );
}
