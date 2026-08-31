import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { api } from "../lib/api";
import { useVideo } from "../lib/queries";
import ReferenceThumb from "../components/ReferenceThumb";
import ConfirmDialog from "../components/ConfirmDialog";

export default function CharactersList() {
  const { id } = useParams({ from: "/videos/$id/characters" });
  const { data: video, error } = useVideo(id);
  const qc = useQueryClient();
  const [newName, setNewName] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["video", id] });
    qc.invalidateQueries({ queryKey: ["videos"] });
  };

  const addCharacter = useMutation({
    mutationFn: (name: string) => api.createCharacter(id, { name }),
    onSuccess: () => {
      setNewName("");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteCharacter = useMutation({
    mutationFn: (characterId: string) => api.deleteCharacter(id, characterId),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error(e.message),
  });

  function removeCharacter(characterId: string) {
    setPendingDeleteId(characterId);
  }

  if (error) return <div className="mx-auto max-w-3xl px-4 py-6 text-danger">{error.message}</div>;
  if (!video) return <div className="mx-auto max-w-3xl px-4 py-6">Loading...</div>;

  const characters = [...video.characters].sort((a, b) => a.order - b.order);

  return (
    <div className="mx-auto max-w-3xl px-4 pb-52 pt-6">
      <Link to="/videos/$id" params={{ id }} className="inline-flex items-center gap-1"><ArrowLeft size={14} /> {video.title}</Link>
      <h1 className="mb-4 mt-2 text-2xl font-bold">Characters</h1>

      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (newName.trim()) addCharacter.mutate(newName.trim());
        }}
      >
        <input placeholder="New character name..." value={newName} onChange={(e) => setNewName(e.target.value)} className="max-w-xs" />
        <button disabled={addCharacter.isPending} type="submit">Add character</button>
      </form>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
        {characters.map((character) => (
          <Link
            key={character.id}
            to="/videos/$id/characters/$characterId"
            params={{ id, characterId: character.id }}
            className="block rounded-lg border border-border bg-bg-alt p-3.5 no-underline hover:border-accent"
          >
            <div className="mb-2 flex items-center gap-2.5">
              {character.references[0] && <ReferenceThumb type={character.references[0].type} path={character.references[0].path} />}
              <div>
                <div className="font-semibold text-text-h">Subject {character.order + 1}: {character.name || "(unnamed)"}</div>
                <div className="text-sm opacity-75">
                  {character.references.length} reference{character.references.length === 1 ? "" : "s"}
                  {character.reference_videos.some((rv) => rv.status === "done") && " · reference video ready"}
                </div>
              </div>
            </div>
            <button
              className="mt-2 border-0 bg-transparent p-0 text-danger"
              onClick={(e) => {
                e.preventDefault();
                removeCharacter(character.id);
              }}
            >
              Delete
            </button>
          </Link>
        ))}
        {characters.length === 0 && <div className="py-6 opacity-60">No characters yet — add one above.</div>}
      </div>

      <ConfirmDialog
        open={!!pendingDeleteId}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Delete this character?"
        description="All its references and reference videos will be removed."
        onConfirm={() => pendingDeleteId && deleteCharacter.mutate(pendingDeleteId)}
      />
    </div>
  );
}
