import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { referencePreviewUrl } from "../lib/api";

const SIZE_CLASSES: Record<"sm" | "lg", string> = {
  sm: "h-10 w-10",
  lg: "h-24 w-24",
};

export default function ReferenceThumb({
  type,
  path,
  size = "sm",
}: {
  type: string;
  path?: string | null;
  size?: "sm" | "lg";
}) {
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const src = referencePreviewUrl(path);
  const boxClass = SIZE_CLASSES[size];

  if (!src || failed) {
    return (
      <span className={`flex ${boxClass} shrink-0 items-center justify-center rounded border border-border opacity-50`}>?</span>
    );
  }

  if (type === "image") {
    return (
      <>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="shrink-0 cursor-zoom-in border-0 bg-transparent p-0"
          title="Click to view full size"
        >
          <img className={`${boxClass} rounded border border-border object-cover`} src={src} alt="" onError={() => setFailed(true)} />
        </button>
        <Dialog.Root open={open} onOpenChange={setOpen}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-black/80" />
            <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] max-w-[90vw] -translate-x-1/2 -translate-y-1/2">
              <Dialog.Title className="sr-only">Reference image preview</Dialog.Title>
              <img src={src} alt="" className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-2xl" />
              <Dialog.Close asChild>
                <button
                  className="absolute -right-3 -top-3 flex h-8 w-8 items-center justify-center rounded-full border-0 bg-bg-alt text-text-h shadow-lg"
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </Dialog.Close>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </>
    );
  }
  if (type === "video") {
    return <video className={`${boxClass} rounded border border-border object-cover`} src={src} muted controls onError={() => setFailed(true)} />;
  }
  if (type === "audio") {
    return <audio className="h-8 w-full max-w-xs shrink-0" src={src} controls onError={() => setFailed(true)} />;
  }
  return null;
}
