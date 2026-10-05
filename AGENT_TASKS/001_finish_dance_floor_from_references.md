# Finish the "Dance floor (from references)" video: clips 2 and 3, then upscale and join

**Status:** In progress (2026-10-05). Clip 1 is done at low res; clips 2 and 3 are close; the final low-res check, the FlashVSR upscale and the full join are still to do.
**Origin:** a long session (2026-10-02 to 2026-10-05) with the user. They have a source video `dance_floor.mp4` (Homelander -> Lafi shot, back of a head -> crowd with a man in a spotlight, Butcher close-up). The Swap LoRA route failed on it, so we rebuild the video with MiniMax H3 Ref2VA from character reference photos, using the original scenes only as guides. This file lets a fresh agent continue with no memory of that conversation.

---
## QUICK START (what exists, how to run it)

- **App:** `E:\repo\h3-studio` (React + TanStack frontend on :5173, FastAPI backend on :8787, runs inside WanGP's venv `E:\repo\wan2.1gp\.venv`). Start the backend from `E:\repo\h3-studio`:
  `nohup ../wan2.1gp/.venv/Scripts/python.exe -m uvicorn backend.main:app --port 8787 > <log> 2>&1 &`
  Stop it with PowerShell `Get-CimInstance Win32_Process | ? CommandLine -like '*uvicorn*8787*' | Stop-Process`. **Never restart it while a job runs** (it kills the job and leaves the clip status "running"; reset with `store.update_clip(video_id, clip_id, status="failed")`).
- **Video id:** `61536ba4353b40eeab11fe746103f10e` ("Dance floor (from references)"), page `http://localhost:5173/videos/61536ba4353b40eeab11fe746103f10e`. Its data folder: `backend/data/videos/dance-floor-from-references-61536ba4/` (not in git).
- **Swap project (the original footage, scenes + cuts):** id `84833496549147f59e993095cbfda8b4`, scenes (0-145), (146-211), (212-284), (285-446), source `backend/data/swaps/dance-floor-84833496/source/dance_floor.mp4` (480x848, 30 fps). A second swap project, `1e99e393cd6a49f6b8ea62aaa4acbb2b`, holds the whole-video low-res LoRA test (kept only for comparison).
- **Characters in the video:** Lafi, Markos, and an environment character "Dance floor spotlight". **Markos has a video reference** `controls/butcher_dance_ref_124f.mp4` (the Butcher's scene 4 cut to 124 frames, note "dance movement...").
- **Tests/typecheck:** `python -m backend.tests.<name>` for each file in `backend/tests/` (all pass; 17+ files), and `cd frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Generation is done by pressing **Regenerate** on the clip in the browser (Chrome MCP); the user wants the real browser used for generating, and honesty about script-vs-click. Settings edits were made through `PUT /videos/{id}/clips/{clip_id}`.

## THE RECIPE THAT WORKS (cheap and good)

1. **Model:** per clip preset "PDD 8-step (fast)" (`minimax_h3_ref2va_pruned_pdd`, 8 steps) at **320x576 for tests** or 576x1024 for finals, then **FlashVSR x2** (`POST /clips/{id}/upscale {"scale": 2}`, ~95 s) -> 1152x2048. The user judged 576p PDD + FlashVSR close to native 1080p Singularity (which took ~50 min). Generation at 320x576 takes 2-3 min per clip.
2. **The output size comes from the clip's Size (or the template), NOT from the control video.** Per-clip Size/Model/Two-phase/Trim/video-references options live in the clip's Shot setup.
3. **Same seed != same video at a different size.** The current seed for clips 2 and 3 is 2718 (clip 1: 31415).
4. **Word prompts positively.** Negations ("no chewing", "never turns around", "nobody stands in a circle") made the model do exactly that. Describe what you want ("her face relaxed and calm", "loose scattered groups, open floor around the spotlight").
5. **Control video (depth guide, `DV`) locks layout, camera AND people's motion to the original.** On = faithful framing but Markos stays nearly still; off = free motion but the framing comes only from the prompt. Clip 2 and 3 currently run with it OFF.
6. **Movement comes from the Butcher reference video (`IV-` mode)**, referenced in the prompt as "using exactly the body movement of the man in <Video 1>". Reference mode also leaks that clip's head-down start, so it can be turned off per clip ("Use video references" checkbox, `video_references_enabled`).
7. **Continuation (`continue_from_previous` + `continuation_keep_frames` = 5):** clip 3 continues from clip 2's last 5 frames, which keeps the same room. The first ~16-28 frames of such a clip are an odd wide "restart"; cut them with **Trim start** (`trim_start_frames`).
8. **Scene detection of cuts:** `ffmpeg -i f.mp4 -vf "select='gt(scene,0.2)',showinfo" -an -f null -` and read `pts_time`.

## CURRENT STATE OF THE CLIPS (all 320x576, PDD 8-step, no control video)

- **Clip 1** (Lafi laughs -> serious, low-angle close-up): seed 31415, 124 frames, scene-1 control video attached and ON. Prompt rewritten without mouth instructions (the "chewing" was caused by "mouth closes / no chewing" wording). **Good, the user approved it.** Saved at `clips/tmp/lowres/c1_v2_mouthfix_s31415.mp4`.
- **Clip 2** (camera behind Lafi's head -> glides down to Markos dancing in the spotlight): seed 2718, 124 frames, Butcher dance reference ON, control OFF, prompt = close-up of the back of her head with blurred bokeh crowd, then "a single smooth glide forward and down", Lafi motionless, Markos with hands on each side of his hips moving his hips to the beat. The user said clip 2 "looks so much better".
- **Clip 3** (Markos from the hips up): seed 2718, 158 frames, continues from clip 2 (5 context frames), Butcher dance reference ON, control OFF, **trim_start_frames = 16**. Prompt: completely fixed camera, hips-up, slightly high angle, same room; head bowed looking down while he moves his hips, then slowly straightens and raises his head, in the last moments looks up toward Lafi.
- Joined test video (clip 2 + trimmed clip 3, 11.1 s): `clips/tmp/lowres/joined_2_3_static_320p.mp4`. Many earlier versions are in the clips' **History** panel (every generation is kept).

## WHAT THE USER STILL WANTS (next steps, in order)

1. **Clip 3 ending:** in the last 45 frames his head is only level, not looking up toward Lafi. Strengthen the ending in the prompt (in the last third he tilts his head back and aims his eyes up at the balcony far above the camera, chin raised), maybe more frames (17k+5 grid: 141, 158, 175...) so the rise is slower. Re-check the Butcher original (scene 4, frames 285-446): camera fixed, hips-up; head bowed for ~the first third, slow rise in the middle, hard upward stare at the camera in the last part.
2. **Camera consistency between clips 2 and 3.** The user said the camera style must match; now clip 3 is a fixed hips-up shot and clip 2 ends medium-wide, so there is one cut at ~5.2 s. Option offered, not yet tried: make clip 2 end closer on Markos so the cut matches.
3. **Crowd in clip 2:** still partly dark-blue clothes / some faces toward Markos; keep the positive wording ("loose scattered groups... only Markos wears a Boca jersey").
4. **Upscale and join:** FlashVSR x2 on clips 1, 2, 3, then join (clip 3 uses its own segment, i.e. minus the 5 context frames and the trim). The app's "Re-join clips" builds the 576p join automatically; the upscaled join was made by hand with ffmpeg concat (re-encode crf 14). Clip 1 needs its own upscaled file.
5. Ask before deleting anything visible; commit/push only when the user asks.

## NEW FEATURES BUILT IN THIS SESSION (all committed with the push that created this file)

- **Clip History panel** (`backend/clip_history.py`, `ClipHistory.tsx`): every finished generation keeps its own file and settings; "Use this take" restores one. Players keep each take's own aspect ratio.
- **Per-clip Size / Model preset / Two-phase (latent upscale)** (`resolution_override`, `model_preset`, `two_phase` in `prompt.build_generation_settings`; `ClipQualityField.tsx`). Two-phase (H3 latent upscaler) was tested: 31.8 min, artifacts + mouth movement, not recommended.
- **FlashVSR upscale button** on finished clips (`ClipUpscale.tsx`, `POST /clips/{id}/upscale`).
- **Trim start frames** (`trim_start_frames`, `control.start_offset_seconds`, `segments_to_join`): cuts the opening of a clip in the join and in its preview, regenerated live.
- **"Use video references" per clip** (`video_references_enabled`, `prompt.without_video_references`).
- **Cache-busting URLs** for files rewritten under the same name (`versioned_output_url`): the own-segment player was showing an old cached take.
- Control video from swap scenes now offers 1080p; its panel no longer claims it sets the output size.

## GOTCHAS FOUND

- WanGP/H3 reference videos must have 17n+5 frames (124 is fine); at least 2 s each; max 2 video references in total.
- Editing a file under CRLF with Python: read/write with `newline=""` and convert `\n` to the file's newline, or edits silently break.
- Do not put apostrophes/backslashes in bash heredocs; use the Write tool plus a script file.
- A stale "running" status after a backend restart is not reconciled automatically.
- The Swap LoRA over the whole source video at 320x576 was tried (project `1e99e393...`): scenes 1 and 4 fine, scene 2 flipped Lafi to face the camera (source is from behind), scene 3's far shot too small. Do not pursue it for this video.
- Task numbering: this is `001`; the WanGP repo has its own `AGENT_TASKS` (001, 002) for other work.
