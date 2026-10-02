# Swap: end-to-end character replacement in a source video

Date: 2026-09-30. Status: draft for review. Path: architectural (new subsystem).

## 1. Goal and intent

Do the video-to-video character-swap workflow from h3-studio's UI instead of scratch scripts.
The user drops in a source video (for example a TikTok-style clip with several scenes and
people), the app splits it into scenes, the user says which character replaces which person in
each scene, and the app runs the swap passes, lets the user review each scene, and produces one
finished video with the original audio.

**Main use (confirmed): finish whole videos end to end.** Not just tune one scene.

**Success criteria**
- A video the size of the studio test clip (24 s, 7 scenes, 2 people) can be taken from upload to a
  joined video with audio using only the UI, with no manual ffmpeg or scripts.
- The consistency rules learned in testing are built in, not remembered by the user (see 6).
- A failed or black pass never loses finished passes, and can be re-run on its own.
- The result of the studio clip matches what the scripts produced by hand: one outfit per
  character across all scenes, backgrounds preserved, no mid-scene outfit change.

**Assumptions (not stated by the user)**
- Personal use on this machine (single RTX 4090, 64 GB RAM, ComfyUI with the H3 nodes available).
- Characters come from h3-studio's existing character store; ComfyUI is started by the existing
  auto-start helper.

## 2. Non-goals (first version)

- Exporting results into a Video project / story timeline (option C, later).
- Automatic recognition of who is who in each scene; the user describes people.
- Generating full-body reference images for characters (Qwen); not needed to ship.
- Swap models other than the akatz-ai character-swap LoRA on the pruned Ref2VA base.
- Lip-sync (the generated video does not match the original audio's lips; documented, not fixed).
- Videos longer than a few minutes; no resumable-upload or streaming concerns.
- A polished progress page beyond the existing queue widget and per-pass status chips.

## 3. What exists and is reused

- `backend/comfy.py`: ComfyUI auto-start, `_post_json`, `_get`, `_upload_image` (accepts any file),
  idle stop, pid adoption.
- `backend/jobs.py`: `JobStore.submit_callable(runner, dest_path, on_done, on_queued, on_running)`
  runs non-WanGP work in the same single-GPU FIFO slot. Each swap pass is one callable job.
- Character store (`backend/store.py`, `backend/prompt.py DEFAULT_CHARACTER`): names, reference
  images, descriptions.
- Frontend patterns: top nav, list page + detail page, queue indicator, `VideoPlayer`.
- Precedent for a separate feature with its own store and page: Animate Jobs
  (`animate.py`, `data/animate_jobs.json`, `pages/AnimateJobs.tsx`).

## 4. Architecture

A new package, `backend/swap/`, with no changes to the video/clip model.

| Module | One job |
|---|---|
| `scenes.py` | Convert to 24 fps; detect cuts by frame difference; split into scenes; pad a scene to the next legal H3 length; split long scenes into chunks |
| `graph.py` | Build the ComfyUI API graph for one pass (see 7) |
| `prompts.py` | Build the prompt for one pass from the rules in 6 |
| `runner.py` | Run one pass as a queued callable: stage inputs, run graph, fetch the SaveVideo output, trim, brightness check |
| `assemble.py` | Join chunks and scenes (scenes with nobody assigned keep the original footage), lay the original audio back on |
| `store.py` | Swap-project records under `data/swaps/` |

Routes live in `backend/swap/api.py` as a FastAPI `APIRouter` included by `backend/main.py`
(the job store is injected at startup), so the routes are testable without starting WanGP.
Swap passes also appear in `main._job_targets()` so the floating queue widget lists them.
Frontend: `pages/SwapsList.tsx`, `pages/SwapDetail.tsx`, small components for the scene card and
the pass status chip, plus `lib/swapApi` helpers. A "Swap" entry in `TopNav`.

Each module is testable on its own; `scenes.py`, `prompts.py` and `assemble.py` are pure or
ffmpeg-only (no GPU, no ComfyUI).

## 5. Data model and storage

`data/swaps/<slug>-<id8>/config.json`, plus files in `source/`, `passes/`, `final/`.

```
swap project
  id, title, created_at, status
  source: { path, width, height, fps_src, frames_src, duration, has_audio }
  settings: { quality: "preview"|"final", width, height, seed }
  scenes: [ {
      index, start_frame_src, end_frame_src,
      frames_24,            # real length at 24 fps
      padded_frames,        # next legal grid length >= chunk frames
      background_text,      # editable, per scene
      chunks: [ { index, start_frame_24, end_frame_24, frames_24, padded_frames } ],
      people: [ { id, target_description, character_id, order } ],
      thumbnail
  } ]
  passes: [ {
      id, scene_index, chunk_index, person_id, order,
      quality, prompt, source_path, status, job_id, output_path,
      mean_luma, error, seconds
  } ]
  final: { path, status }
```

**Cast (amended at planning time).** Characters belong to individual videos in this app, so the
swap project has its own **cast**: a list of entries `{id, name, image_path, appearance, outfit,
body, source_character_id}`. `image_path` is the character's reference photo (picked from an
existing character via `GET /swap-characters`, or typed). `outfit` is one fixed outfit sentence
reused verbatim in every scene; `body` is a short build description ("fat, heavyset");
`appearance` is how to recognise the character AFTER they are swapped in ("the dark-haired
heavyset man with glasses and a short beard"), used to protect them in later passes. The
character store is not modified. The prompt builder refuses a pass for a cast entry whose
`outfit` is empty.

**Chunking rule (amended).** The maximum chunk depends on quality: **243 frames for final**
(20-step runs of 243 frames worked) and **124 for preview** (turbo: 260 frames produced black
video; 124 always worked). A scene of at most that length is one chunk. A longer scene is split
into k = ceil(n / max) chunks of near-equal size (the first `n mod k` chunks get one extra
frame), so there are no skipped frames and no repeated frames at joins. Both maxima are
settings.

**Padding rule.** Legal lengths are `frames % 17 == 5` (124, 141, ..., 362; below 124 also 22,
39, 56, 73, 90, 107). A chunk shorter than its padded length has its last frame held; after
the pass the output is trimmed back to `frames_24`. Existing `backend/lint.py` holds the grid
helpers; `scenes.py` reuses them.

## 6. Prompt builder and consistency rules

`prompts.build_pass_prompt(project, scene, pass)` returns the full prompt, shown and editable
per pass and stored with it. It enforces the rules found in testing (see `AGENTS.md`):

1. Always the long explicit form; never the bare one-sentence prompt (which did nothing).
2. One replacement per pass. Later passes describe their target by **what he looks like now**
   (the user's `target_description`, written by appearance), never by his original clothes.
3. Everyone else in the frame is protected by appearance plus their own outfit and colours
   ("leave the dark-haired heavyset man with glasses, keeping his light blue shirt and khaki
   trousers exactly as he is"), never naming clothes without saying whose they are.
4. Each replaced character's `swap_outfit` and `swap_body` are inserted verbatim in every
   scene ("In every shot this character wears exactly the same outfit: ...").
5. `background_text` describes only what is really behind the people. A warning is raised if it
   contains words the scene is not known to have (the user can override); "stripes" is the
   known offender. The clause "No light rays, no beams, no streaks, no translucent overlays and
   no colour gradients ... keep the overall brightness, contrast and colour grading as in
   <Video 1>" is always appended.
6. The prompt always ends with the preserve-camera / match-movement / do-not-show-the-reference
   sentence.

## 7. The ComfyUI pass graph

Native ComfyUI nodes (verified working, 0-based ref keys):

- `UNETLoader` `minimax_h3_ref2va_pruned_fp8_scaled.safetensors`
- `LoraLoaderModelOnly` `h3_character_swap_pro4500_1000.safetensors`, strength 1.0
- optional (preview quality only) `LoraLoaderModelOnly`
  `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`, strength 0.6
- `CLIPLoader` qwen3vl text encoder (type `minimax`), video VAE fp16, audio VAE fp32
- `LoadImage` (character reference) -> `ref_images.ref_image_0`; `LoadVideo` ->
  `GetVideoComponents` -> `ref_videos.ref_video_0` of `MiniMaxH3ReferenceToVideo`
- Final: `res_multistep`, scheduler `simple`, 20 steps. Preview: `euler`, `simple`, 4 steps.
- Output: `CreateVideo` **without** the audio branch (an audio-mux crash lost a 23 minute run),
  then `SaveVideo`. The runner reads **that node's output**, never `history[...]["outputs"][0]`
  (it can be the `LoadVideo` input preview, bit-identical to the source).
- The source video must be 24 fps; the loader does not resample.

Preview output is for iterating. The UI shows a warning on the final-assembly button if a scene
only has preview results (turbo causes colour gradients, darkening and lost identity on hard
faces).

## 8. Runner behaviour per pass

1. Mark running; ensure ComfyUI is up (existing helper); release WanGP's model first.
2. Copy the source chunk (padded) into ComfyUI's input folder, upload the character photo.
3. Post the graph; poll history; on error record the exception message.
4. Fetch the SaveVideo file; trim to `frames_24`; write to `passes/`.
5. Mean-luma check on three frames; black (about 16 on a 0-255 scale) marks the pass failed with
   reason "black output".
6. Always call ComfyUI `/free` afterwards, as the Qwen runner does.

**Cancel.** `POST /swaps/{id}/passes/{pid}/cancel` calls ComfyUI `POST /interrupt` and `/free`
directly, and removes the pass from the pending queue if it has not started. Stopping only the
h3-studio job is not enough (ComfyUI keeps sampling).

**Ordering.** Passes of one chunk run in order; the queue is FIFO and a pass is only submitted
once its source exists (the previous pass finished). Different scenes are independent.

## 9. Assembly

`assemble.py`: for each scene, join its chunks (repeating one frame at each join), trim to the
scene's real frame count; join scenes in order; mux the original audio (AAC, `-shortest`).
Because scene frame counts at 24 fps are derived from the source, the total equals the
source duration within one frame per scene; the assembly reports the difference. Output:
`final/<title>.mp4`.

## 10. API

`POST /swaps` (upload source), `GET /swaps`, `GET /swaps/{id}`, `DELETE /swaps/{id}`,
`POST /swaps/{id}/detect-scenes`, `PATCH /swaps/{id}/scenes` (merge, split, background text,
people), `POST /swaps/{id}/plan` (build passes and prompts), `PATCH /swaps/{id}/passes/{pid}`
(edit prompt), `POST /swaps/{id}/run` (quality, scope: all or one scene),
`POST /swaps/{id}/passes/{pid}/rerun`, `POST /swaps/{id}/passes/{pid}/cancel`,
`POST /swaps/{id}/assemble`, `GET /swaps/{id}/files/...`.

## 11. UI

A "Swap" top-nav item.

- **List:** each project with thumbnail, pass progress (done / total) and status.
- **Project page**, four stacked parts that appear once the previous is done:
  1. **Source:** video picker/player; "Detect scenes".
  2. **Scenes:** one card per scene (thumbnail, length, background text, people rows: who to
     replace by appearance, character, order); merge/split buttons.
  3. **Run:** quality choice (Preview / Final), prompt preview and edit for any pass, "Run all"
     and "Run this scene"; per-pass status chips; jobs also appear in the queue widget.
  4. **Results:** per scene, source and result side by side, re-run button; the assembled
     video with a download link.

## 12. Errors and edge cases

- ComfyUI unreachable or not auto-startable: the pass fails with that message; nothing else is lost.
- Black or near-black output: failed with reason; the user re-runs with another seed or quality.
- Output file missing or zero size: failed.
- Scene with no people assigned: skipped in the plan, with a notice.
- A character without `swap_outfit`: blocked with an inline prompt to fill it in.
- Scene longer than one chunk: automatically chunked; the plan shows the chunk count.
- Source not 24 fps or not on the grid: converted and padded by `scenes.py`; never passed raw.
- Disk: per-pass outputs are kept until the project is deleted; the project page shows size.
- Licence: the UI shows a one-line note that the MiniMax H3 community licence excludes the EU,
  UK, Republic of Korea and USA and requires the "MiniMax H3" display for commercial products.

## 13. Testing

Unit (no GPU): scene detection on synthetic frames with known cuts; padding and chunk splitting
for 35, 39, 69, 124, 125, 249 frames; the prompt builder against each rule in section 6
(including "never names clothes without saying whose", "stripes" warning, empty `swap_outfit`
blocked); assembly arithmetic (chunks and scenes add up to the source frame count); the graph
builder's node keys against a stored known-good graph. Backend tests run like
`python -m backend.tests.test_lint`. The frontend vitest suite cannot run in this checkout
(missing `@testing-library/dom`), so frontend checks are type-check plus manual.

Acceptance (manual, GPU): the studio clip (`ObNx9fajfpcURSGN.mp4`, 7 scenes) with lafi/markos
characters replaced by mapache and veron; expected result is the hand-made video at 580 frames,
24.17 s, with the original audio, no mid-scene outfit change, and no rays or gradients.

## 14. Decisions taken for the first version

- People per scene are typed by the user; suggesting descriptions with a vision model is a
  later feature (see non-goals).
- Assembly runs from a button ("Assemble"), never automatically after the last pass, since a
  long run may be interrupted or edited between passes.
- Pass outputs are kept until the project is deleted; no automatic clean-up. The project page
  shows its disk size.
