import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { usePromptTags, useCreatePromptTag, useUpdatePromptTag, useDeletePromptTag } from "../lib/queries";
import ConfirmDialog from "../components/ConfirmDialog";
import type { PromptTag } from "../schemas";

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export default function PromptTagsList() {
  const { data: tags, error } = usePromptTags();
  const createTag = useCreatePromptTag();
  const deleteTag = useDeletePromptTag();

  const [draft, setDraft] = useState({ name: "", key: "", body: "" });
  const [keyTouched, setKeyTouched] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  function addTag() {
    if (!draft.name.trim() || !draft.key.trim() || !draft.body.trim()) return;
    createTag.mutate(draft, {
      onSuccess: () => {
        setDraft({ name: "", key: "", body: "" });
        setKeyTouched(false);
      },
    });
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pb-52 pt-6">
      <Link to="/" className="inline-flex items-center gap-1"><ArrowLeft size={14} /> Videos</Link>
      <h1 className="mb-1 mt-2 text-2xl font-bold">Prompt Tags</h1>
      <p className="mb-4 text-sm opacity-75">
        Reusable named snippets for repeated prompt boilerplate (e.g. a voice/accent register used across many
        clips). Reference one anywhere in a shot prompt as <code>[[key]]</code> — it's expanded into its full text
        right before generation, and stays a short, readable token in the prompt input in the meantime.
      </p>
      {error && <div className="mb-2 whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-danger">{error.message}</div>}

      <div className="mb-4 rounded-lg border border-dashed border-border p-3.5">
        <h3 className="mb-2 font-semibold text-text-h">Add tag</h3>
        <div className="flex flex-wrap gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <input
              placeholder="e.g. Neutral Spanish"
              value={draft.name}
              onChange={(e) => {
                const name = e.target.value;
                setDraft((d) => ({ ...d, name, key: keyTouched ? d.key : slugify(name) }));
              }}
              className="max-w-xs"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Key
            <input
              placeholder="neutral_spanish"
              value={draft.key}
              onChange={(e) => {
                setKeyTouched(true);
                setDraft((d) => ({ ...d, key: e.target.value }));
              }}
              className="max-w-xs font-mono"
            />
          </label>
        </div>
        <label className="mt-3 flex flex-col gap-1 text-sm">
          Body (the text this tag expands into)
          <textarea
            rows={2}
            placeholder="Neutral Latin American Spanish dubbing accent, no regional accent, no voseo, use tú"
            value={draft.body}
            onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
          />
        </label>
        <button className="mt-2" disabled={createTag.isPending} onClick={addTag}>Create tag</button>
      </div>

      <div className="flex flex-col gap-2.5">
        {tags?.map((tag) => (
          <PromptTagRow key={tag.id} tag={tag} onDelete={() => setPendingDeleteId(tag.id)} />
        ))}
        {tags?.length === 0 && <div className="py-6 opacity-60">No prompt tags yet — create one above.</div>}
      </div>

      <ConfirmDialog
        open={!!pendingDeleteId}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Delete this prompt tag?"
        description={'Any [[key]] reference to it left in a prompt will fail generation with an "unknown prompt tag" error until removed.'}
        onConfirm={() => pendingDeleteId && deleteTag.mutate(pendingDeleteId)}
      />
    </div>
  );
}

function PromptTagRow({ tag, onDelete }: { tag: PromptTag; onDelete: () => void }) {
  const updateTag = useUpdatePromptTag();
  const [draft, setDraft] = useState(tag);

  function save(fields: Partial<PromptTag>) {
    updateTag.mutate({ id: tag.id, body: fields });
  }

  return (
    <div className="rounded-lg border border-border bg-bg-alt p-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <input
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          onBlur={() => save({ name: draft.name })}
          className="max-w-xs font-semibold text-text-h"
        />
        <span className="rounded-full bg-status-draft px-2 py-0.5 font-mono text-xs text-white">[[{draft.key}]]</span>
        <button className="ml-auto border-0 bg-transparent p-0 text-danger" onClick={onDelete}>Delete</button>
      </div>
      <textarea
        rows={2}
        className="mt-2"
        value={draft.body}
        onChange={(e) => setDraft({ ...draft, body: e.target.value })}
        onBlur={() => save({ body: draft.body })}
      />
    </div>
  );
}
