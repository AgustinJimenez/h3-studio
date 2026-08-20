// MiniMax H3's own controlled vocabulary for retention_analysis (confirmed
// from their Ref2VA prompt-writing guide — see AGENTS.md). A free-text field
// forces a human to remember these exact tokens; this is now the sole
// source of truth for both the picker (RetentionSelect) and any future
// validation.
export type RetentionOption = {
  value: string;
  label: string;
  description: string;
};

export const RETENTION_OPTIONS: RetentionOption[] = [
  {
    value: "fully_preserved",
    label: "Fully preserved",
    description: "Exact identity carries over 1:1 — face, body, hair, everything. Default for main/recurring characters.",
  },
  {
    value: "partially_preserved",
    label: "Partially preserved",
    description: "Core identity carries over but some attributes may drift or adapt, e.g. under a strong stylization effect.",
  },
  {
    value: "attribute_transfer",
    label: "Attribute transfer",
    description: "Only specific attributes (usually wardrobe/style) are taken from the reference, not full identity.",
  },
  {
    value: "weak_reference",
    label: "Weak reference",
    description: "The reference is a loose inspirational guide only, with very low binding to its visual details.",
  },
];

export function retentionDescription(value: string): string {
  return RETENTION_OPTIONS.find((o) => o.value === value)?.description ?? "";
}
