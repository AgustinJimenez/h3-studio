import { useState } from "react";
import { referencePreviewUrl } from "../lib/api";

export default function ReferenceThumb({ type, path }: { type: string; path?: string | null }) {
  const [failed, setFailed] = useState(false);
  const src = referencePreviewUrl(path);
  if (!src || failed) {
    return (
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-border opacity-50">?</span>
    );
  }
  if (type === "image") {
    return <img className="h-10 w-10 shrink-0 rounded border border-border object-cover" src={src} alt="" onError={() => setFailed(true)} />;
  }
  if (type === "video") {
    return <video className="h-10 w-10 shrink-0 rounded border border-border object-cover" src={src} muted onError={() => setFailed(true)} />;
  }
  if (type === "audio") {
    return <audio className="h-7 max-w-[160px] shrink-0" src={src} controls onError={() => setFailed(true)} />;
  }
  return null;
}
