import * as Dialog from "@radix-ui/react-dialog";

export default function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Delete",
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  onConfirm: () => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[90vw] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg-alt p-4 shadow-lg">
          <Dialog.Title className="text-lg font-semibold text-text-h">{title}</Dialog.Title>
          {description && <Dialog.Description className="mt-1.5 text-sm opacity-75">{description}</Dialog.Description>}
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close asChild>
              <button>Cancel</button>
            </Dialog.Close>
            <button
              className="danger"
              onClick={() => {
                onConfirm();
                onOpenChange(false);
              }}
            >
              {confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
