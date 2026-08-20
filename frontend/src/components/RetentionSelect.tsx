import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { RETENTION_OPTIONS } from "../lib/retention";

export default function RetentionSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const current = RETENTION_OPTIONS.find((o) => o.value === value);

  return (
    <Select.Root value={value} onValueChange={onChange}>
      <Select.Trigger
        title={current?.description}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-border bg-bg px-2 py-1.5 text-left text-text-h data-[placeholder]:opacity-60"
      >
        <Select.Value placeholder="Select retention...">{current?.label ?? value}</Select.Value>
        <Select.Icon className="opacity-60">
          <ChevronDown size={16} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={4}
          className="z-50 w-[--radix-select-trigger-width] overflow-hidden rounded-md border border-border bg-bg-alt shadow-lg"
        >
          <Select.Viewport className="p-1">
            {RETENTION_OPTIONS.map((option) => (
              <Select.Item
                key={option.value}
                value={option.value}
                title={option.description}
                className="cursor-pointer select-none rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-text"
              >
                <div className="flex items-center gap-1.5">
                  <Select.ItemText>{option.label}</Select.ItemText>
                  <Select.ItemIndicator>
                    <Check size={14} />
                  </Select.ItemIndicator>
                </div>
                <div className="text-xs opacity-75">{option.description}</div>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
