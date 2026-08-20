# h3-studio

A local app for building multi-shot, character-consistent videos on MiniMax H3 Ref2VA, on top of [WanGP](https://github.com/deepbeepmeep/Wan2GP). A **video** is an ordered list of **clips**, each an independent H3 generation with its own shot prompt; clips share a video's characters/base settings and can be concatenated into one file. Includes structured prompt editing, a reusable prompt-tag library, character/reference management, and on-demand post-generation QA (visual duplication/ghosting detection + voice speaker-verification).

See [`AGENTS.md`](./AGENTS.md) for the full build history and implementation notes.

## Prerequisites

- **A working [WanGP](https://github.com/deepbeepmeep/Wan2GP) checkout with its own `.venv`.** This app is not standalone — it runs *inside* WanGP's Python environment and imports WanGP's `shared.api` directly as source. Set it up per WanGP's own install instructions first. Default expected location is `E:\repo\wan2.1gp`; if yours lives elsewhere, set the `WANGP_ROOT` environment variable to that path when running the backend.
- **Node.js** (for the frontend).
- **`ffmpeg`/`ffprobe` on PATH** — used for clip concatenation, tail-frame extraction, and QA audio extraction.
- An NVIDIA GPU capable of running H3 (see WanGP's own requirements).

## Backend

Runs from this repo's root, using **WanGP's own venv** (not a separate one):

```
<path-to-wangp>\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8787
```

If your WanGP checkout isn't at `E:\repo\wan2.1gp`, set `WANGP_ROOT` first:

```
set WANGP_ROOT=D:\path\to\your\wan2.1gp
```

Don't use `--reload` — it's unreliable here (see `AGENTS.md`); restart manually after backend code changes.

### Extra dependencies for the QA feature (optional)

The on-demand clip "Analyze" feature (visual duplication/ghosting detection via VideoChat3-4B, voice-bleed detection via speechbrain) needs a few packages beyond WanGP's own requirements, installed into WanGP's venv:

```
<path-to-wangp>\.venv\Scripts\pip install speechbrain qwen-vl-utils decord
```

Visual analysis also **requires flash-attn** — there's no plain PyPI wheel for it on Windows; see `AGENTS.md`'s "Installing flash-attn for real" note for how to find a prebuilt wheel matching your exact torch/CUDA/Python versions (or build from source). The rest of the app (generation, editing, voice QA) works fine without it — only the visual-analysis half of the Analyze button needs it.

## Frontend

```
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`, talking to the backend at `http://localhost:8787`.

Other frontend commands: `npm run build`, `npm run typecheck` (`tsc -b`), `npm test` (Vitest).

## First run

All project data (`backend/data/`) is created automatically on first run — no manual setup needed. It's gitignored (generated videos/images/audio, not source).
