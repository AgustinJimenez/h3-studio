import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useOptions, useModelStatus, useLoadModel, useUnloadModel } from "../lib/queries";

export default function TopNav() {
  const { data: options } = useOptions();
  const { data: status } = useModelStatus();
  const loadModel = useLoadModel();
  const unloadModel = useUnloadModel();
  const [selected, setSelected] = useState<string>("");

  const modelTypes = options?.model_types ?? [];
  const loadedModelType = status?.model_type ?? null;
  const loadedModel = modelTypes.find((m) => m.model_type === loadedModelType);

  useEffect(() => {
    if (!selected && modelTypes.length > 0) setSelected(loadedModelType ?? modelTypes[0].model_type);
  }, [modelTypes, loadedModelType, selected]);

  return (
    <div className="sticky top-0 z-40 flex flex-nowrap items-center gap-3 overflow-x-auto whitespace-nowrap border-b border-border bg-bg px-4 py-1.5 text-sm">
      <Link to="/" className="shrink-0 font-semibold text-text-h no-underline">
        H3 Studio
      </Link>

      <div className="ml-auto flex flex-nowrap items-center gap-2">
        <span
          className="flex max-w-[16rem] items-center gap-1.5 truncate text-xs text-text-muted"
          title={loadedModelType ? `Currently loaded: ${loadedModelType}` : "No model currently loaded in GPU/RAM"}
        >
          <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${loadedModelType ? "bg-emerald-400" : "bg-zinc-600"}`} />
          <span className="truncate">{loadedModel ? loadedModel.name : loadedModelType ?? "No model loaded"}</span>
        </span>

        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="rounded-lg border border-border bg-bg-alt px-2.5 py-1 text-xs text-text-h"
        >
          {modelTypes.map((m) => (
            <option key={m.model_type} value={m.model_type}>
              {m.name}
            </option>
          ))}
        </select>

        {loadedModelType ? (
          <button className="shrink-0 py-1" disabled={unloadModel.isPending} onClick={() => unloadModel.mutate()}>
            Unload model
          </button>
        ) : (
          <button className="shrink-0 py-1" disabled={!selected || loadModel.isPending} onClick={() => loadModel.mutate(selected)}>
            Load model
          </button>
        )}
      </div>
    </div>
  );
}
