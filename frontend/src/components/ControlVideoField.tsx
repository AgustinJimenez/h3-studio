import { useEffect, useState } from "react";
import type { Clip } from "../schemas";

// Per-clip depth control video (H3 "Transfer Depth Map From Control Video"): a
// grey-box previs render of this shot, e.g. from Blender. It locks the room
// layout and the camera move; the look still comes from the references.
export default function ControlVideoField({ clip, onChange }: { clip: Clip; onChange: (path: string) => void }) {
  const [draft, setDraft] = useState(clip.control_video_path ?? "");
  useEffect(() => setDraft(clip.control_video_path ?? ""), [clip.control_video_path]);
  return (
    <label className="flex flex-col gap-1 text-sm">
      Control video (depth previs) — local path to this shot's grey-box render; sets the output size, match its frame count
      <span className="flex gap-2">
        <input
          className="flex-1 font-mono text-xs"
          placeholder="E:\\repo\\previs\\...\\07_remote_640.mp4"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => draft !== (clip.control_video_path ?? "") && onChange(draft.trim())}
        />
        {clip.control_video_path && (
          <button type="button" className="border-0 bg-transparent p-0 text-danger" onClick={() => onChange("")}>Clear</button>
        )}
      </span>
    </label>
  );
}
