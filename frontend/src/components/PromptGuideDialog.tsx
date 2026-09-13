import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-accent">{title}</h3>
      <div className="space-y-2 text-sm leading-relaxed text-text">{children}</div>
    </section>
  );
}

export default function PromptGuideDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[90vw] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border border-border bg-bg-alt p-5 shadow-lg">
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold text-text-h">H3 Prompt Guide</Dialog.Title>
            <Dialog.Close asChild>
              <button className="border-0 bg-transparent p-1 text-text-muted hover:text-text-h" aria-label="Close">
                <X size={18} />
              </button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="mb-3 text-xs text-text-muted">
            Condensed from this project's AGENTS.md (empirically tested against real generations) and the
            h3-storyboard-skill guide it references. Read the full AGENTS.md for details and worked examples.
          </Dialog.Description>

          <div className="overflow-y-auto pr-1">
            <Section title="Beat density &amp; performance">
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  <strong>Max 2-3 expression beats per shot.</strong> More than that and H3 averages them into a
                  frozen or near-frozen face. Split shots at that ceiling instead of cramming a scene into one.
                </li>
                <li>
                  <strong>Dialogue reallocates the whole clip's frame budget</strong>, not just that shot's. Don't
                  mix a dialogue shot with a shot that needs background/setting continuity in the same clip.
                </li>
                <li>
                  <strong>Camera position before expression.</strong> If what a character is looking at isn't in
                  frame, H3 defaults to camera-facing "stage acting." Move the camera to what they're looking at
                  instead of fighting the story's locked pose.
                </li>
                <li>
                  <strong>Describe the physical action, not the adjective.</strong> Never write "confused" or
                  "shocked" &mdash; describe what the body does (e.g. "head retreats 3cm, upper eyelids fully open,
                  breath held with shoulders staying elevated"). Order: eyebrows first, then eyes, then mouth last.
                </li>
                <li>
                  <strong>Don't script a continuous A-to-B emotional transition</strong> visible in one shot &mdash;
                  H3 interpolates it into rubbery morphing. Hide the transition behind an occlusion (eyes closing, a
                  cut, a hand) and reveal the new state only after.
                </li>
                <li>
                  <strong>Frame-count table:</strong> 124 frames (5.17s) = one static action &bull; 158 (6.58s) =
                  action + one camera move &bull; 192 (8.00s) = entrance/approach &bull; 209 (8.71s) =
                  action&rarr;reaction&rarr;settle &bull; 243+ (10.13s+) = with cuts. Leave ~1.3-1.5s of tail buffer
                  &mdash; H3 often degrades to noise in the last 1.2-1.7s.
                </li>
                <li>H3 can't do contact-driven causality or maintain liquid volume &mdash; cut from "about to happen" to "already happened, state now settled," don't script the moment of impact/pour.</li>
                <li>Describe sizing/distance as crop relationships ("ear tip one palm-width from the top edge"), not fractions or units &mdash; fractions get ignored.</li>
                <li>Don't name objects that shouldn't be in frame &mdash; H3 tends to hallucinate what it's told about.</li>
                <li>If a correctly-structured shot still reads as fake, stop reprompting and cut instead &mdash; H3 treats each timestamp as a state to arrive at cleanly, not a true discontinuous human transition. Shoot with extra length for cutting room.</li>
                <li>Verify with PSNR on before/after beat frames, not just by eye: &gt;45dB = frozen, 30-40dB = only micro-motion, 18-28dB = clear motion, &lt;15dB = cut-level change.</li>
              </ul>
            </Section>

            <Section title="Prompt structure (official MiniMax vocabulary)">
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  <code>retention_analysis</code> controlled vocabulary &mdash; visual:{" "}
                  <code>fully_preserved</code> / <code>partially_preserved</code> / <code>attribute_transfer</code> /{" "}
                  <code>weak_reference</code>; audio: <code>fully_copy</code> / <code>partially_copy</code> /{" "}
                  <code>reference</code> / <code>weak_reference</code>.
                </li>
                <li>
                  A reference used only for wardrobe/style (not identity) should be cited inline inside its{" "}
                  <code>&lt;Subject N&gt;</code> definition, tagged <code>attribute_transfer</code> &mdash; this is
                  exactly what a character reference's <code>note</code> field does in this app.
                </li>
                <li>
                  <code>summary</code> should carry a task-type prefix: <code>[video continuation]</code>,{" "}
                  <code>[keyframe completion]</code>, <code>[reference generation]</code>,{" "}
                  <code>[video editing]</code>, <code>[audio reuse]</code>, or <code>[audio reference]</code>.
                </li>
                <li><code>detailed_description</code> target length is ~350-500 English words (relaxed for dialogue-dense scenes) &mdash; check against this if a generation seems to ignore part of a long prompt.</li>
              </ul>
            </Section>

            <Section title="This app's own reference rules">
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  <strong>Never hardcode <code>&lt;Picture N&gt;</code>/<code>&lt;Audio N&gt;</code>/<code>&lt;Video N&gt;</code> numbers</strong>{" "}
                  in a character's identity or wardrobe text &mdash; numbering runs globally across the whole
                  video's character list, not per-character. Describe traits, not which numbered reference carries them; the auto-generated prefix already handles the numbering.
                </li>
                <li>
                  Use <code>[[key]]</code> to insert a reusable Prompt Tag (e.g. a standard accent/dubbing block)
                  anywhere in a prompt field &mdash; it expands once, on the fully composed prompt, right before
                  generation. Manage tags from the Prompt Tags page.
                </li>
                <li>A photorealism baseline is auto-prepended to every shot's <code>detailed_description</code> already &mdash; no need to retype it per character.</li>
              </ul>
            </Section>

            <Section title="Length &amp; continuity">
              <ul className="list-disc space-y-1.5 pl-5">
                <li>Each clip is a single window, hard-capped at ~15s (362 frames) &mdash; this app has no per-clip multi-window (PW) mode. Model longer beats as multiple independent clips, chained or ffmpeg-concatenated.</li>
                <li><code>continue_from_previous</code> appends new frames onto the prior clip's real output (confirmed via pixel diff) &mdash; it does not re-render existing content, and the resulting duration is additive.</li>
                <li>Combined reference limits are real WanGP integration ceilings: 2 video refs and 2 audio refs total per generation, each 2-15s (audio) or similarly bounded, not just this app's own choice.</li>
              </ul>
            </Section>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
