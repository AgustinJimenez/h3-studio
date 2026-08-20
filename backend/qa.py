"""Post-generation clip QA: an on-demand analysis pass over a finished H3
clip, separate from generation itself. Two independent checks:

  - analyze_visual: MCG-NJU/VideoChat3-4B (github.com/MCG-NJU/VideoChat3,
    Apache 2.0, plain `transformers`, visual-only -- confirmed via its own
    paper, no audio modality) looks for duplicated/cloned subjects and
    ghosting/double-exposure artifacts, the two visual failure modes this
    project has repeatedly hit and previously only caught by manual
    frame-by-frame review (see AGENTS.md's cardinality-directive and
    DV-depth-transfer-ghosting notes).
  - analyze_voice: speechbrain's ECAPA-TDNN speaker-verification model
    (speechbrain/spkrec-ecapa-voxceleb, Apache 2.0) compares each character
    reference audio file actually used in generation (from the clip's own
    stored last_generation_settings.audio_guide/audio_guide2) against the
    clip's own audio track, as a coarse objective check for the multi-
    speaker voice-bleed bug documented in AGENTS.md (GitHub issue #17).
    This compares the reference against the clip's WHOLE audio track, not
    per-speaker-diarized segments -- real diarization is out of scope here;
    treat a low score as "this voice doesn't clearly show up at all", not
    a precise per-line attribution.

VRAM note: VideoChat3 (~8GB bf16) can't reliably coexist with WanGP's own
resident H3/Animate checkpoint (17-30GB) on a 23GB GPU. Callers must release
WanGP's model first -- see main.py's use of session.release_model().

torchaudio/speechbrain compatibility note: speechbrain 1.0.3's import path
calls torchaudio.list_audio_backends(), an API removed in newer torchaudio
(2.11 here). WanGP's own preprocessing/speaker_separator/separator.py hit
this exact incompatibility already and carries a working monkeypatch
(soundfile-backed torchaudio.info/load/save) -- reused verbatim below
rather than re-solving the same problem twice.
"""

from __future__ import annotations

import os

# qwen_vl_utils prefers torchcodec for video reading when it *looks*
# importable, but torchcodec's compiled DLLs fail to actually load on this
# machine (ABI/ffmpeg-version mismatch -- tried FFmpeg 4 through 8, all
# fail); its fallback on that failure is torchvision, not decord, and this
# torchvision build has no `io.read_video` at all (removed in favor of
# torchcodec-only). decord is already installed and works -- force it
# before qwen_vl_utils's backend selection (which is @lru_cache'd on first
# call) ever runs.
os.environ.setdefault("FORCE_QWENVL_VIDEO_READER", "decord")

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

_videochat_model = None
_videochat_processor = None
_speaker_verification = None
_torchaudio_patched = False

QA_PROMPT = (
    "Carefully analyze this video for these specific problems: "
    "(1) duplicated or cloned people -- the SAME character appearing twice, mirrored, or doubled; "
    "(2) ghosting or double-exposure visual artifacts; "
    "(3) any other visual inconsistencies, warping, or unnatural artifacts. "
    "Important: a scene showing two or more DIFFERENT characters together is normal and must not be "
    "reported as a duplicate -- only flag (1) if one single character's face/body clearly appears more "
    "than once at the same time. "
    "For each category, state clearly whether the problem is present, and if so, describe when/where it occurs."
)


def _build_qa_prompt(scene_prompt: str | None) -> str:
    """Prepend the clip's own generation prompt as disambiguating context.
    Found empirically (2026-08-20) that without this, VideoChat3 can mistake
    two distinct characters in one shot for one character duplicated -- see
    the false positive on Breaking Bad clip 0 documented in AGENTS.md. Giving
    it the scene description lets it know how many distinct characters were
    actually intended, without asking it to trust the prompt for anything else."""
    if not scene_prompt or not scene_prompt.strip():
        return QA_PROMPT
    return (
        "Context: this video was generated from the following scene description, which lists the "
        "characters intended to appear and what they look like:\n"
        f"\"{scene_prompt.strip()}\"\n"
        "Use this only to know how many distinct characters should be in the scene and how to tell them "
        "apart -- do not assume the video otherwise matches the description exactly.\n\n"
        + QA_PROMPT
    )


def _load_videochat3():
    global _videochat_model, _videochat_processor
    if _videochat_model is None:
        from transformers import AutoConfig, AutoModelForCausalLM, AutoProcessor

        model_id = "MCG-NJU/VideoChat3-4B"
        # The vision tower dispatches attention via a custom `config.vision_config.attn_impl`
        # field (VL_VISION_ATTENTION_FUNCTIONS dict in modeling_videochat3.py), separate from
        # HF's standard `attn_implementation=` kwarg -- that kwarg only affects the LLM backbone.
        # Both default to "flash_attention_2". The `sdpa` fallback works but builds a dense
        # O(n^2) attention mask per forward pass -- OOMs on real clip lengths (~10-15s @ 24fps).
        # flash-attn is now installed (see AGENTS.md), so use the real varlen kernels everywhere.
        _videochat_model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype="auto", device_map="auto", trust_remote_code=True,
            attn_implementation="flash_attention_2",
        )
        _videochat_processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    return _videochat_model, _videochat_processor


def _patch_torchaudio_for_speechbrain() -> None:
    """See module docstring -- verbatim reuse of the working shim already
    in preprocessing/speaker_separator/separator.py (lines 23-52)."""
    global _torchaudio_patched
    if _torchaudio_patched:
        return
    import torch
    import torchaudio

    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["ffmpeg", "soundfile"]
    if not hasattr(torchaudio, "AudioMetaData"):
        from collections import namedtuple

        torchaudio.AudioMetaData = namedtuple("AudioMetaData", "sample_rate num_frames num_channels bits_per_sample encoding")

    def _torchaudio_info(uri, backend=None, format=None, buffer_size=4096):
        import soundfile as sf

        info = sf.info(uri)
        bits = 0
        for suffix in ("8", "16", "24", "32", "64"):
            if suffix in str(info.subtype):
                bits = int(suffix)
                break
        return torchaudio.AudioMetaData(
            sample_rate=info.samplerate, num_frames=info.frames, num_channels=info.channels,
            bits_per_sample=bits, encoding=info.subtype or info.format,
        )

    def _torchaudio_load(uri, frame_offset=0, num_frames=-1, normalize=True, channels_first=True, format=None, buffer_size=4096, backend=None):
        import soundfile as sf

        start = max(0, int(frame_offset or 0))
        stop = None if num_frames is None or int(num_frames) < 0 else start + int(num_frames)
        audio_data, sample_rate = sf.read(uri, start=start, stop=stop, dtype="float32", always_2d=True)
        waveform = torch.from_numpy(audio_data.T.copy() if channels_first else audio_data.copy())
        return waveform, sample_rate

    def _torchaudio_save(uri, src, sample_rate, channels_first=True, format=None, encoding=None, bits_per_sample=None, buffer_size=4096, backend=None, compression=None):
        import numpy as np
        import soundfile as sf

        audio_data = src.detach().cpu().float().numpy() if torch.is_tensor(src) else np.asarray(src, dtype=np.float32)
        if channels_first and audio_data.ndim == 2:
            audio_data = audio_data.T
        sf.write(uri, audio_data, int(sample_rate))

    torchaudio.info = _torchaudio_info
    torchaudio.load = _torchaudio_load
    torchaudio.save = _torchaudio_save
    _torchaudio_patched = True


def _load_speaker_verification():
    global _speaker_verification
    if _speaker_verification is None:
        _patch_torchaudio_for_speechbrain()
        from speechbrain.inference.speaker import SpeakerRecognition
        from speechbrain.utils.fetching import LocalStrategy

        # Windows without Developer Mode/admin can't create the symlinks
        # speechbrain's fetcher defaults to -- copy the files instead.
        _speaker_verification = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(Path(__file__).resolve().parent / "data" / "pretrained_models" / "spkrec-ecapa-voxceleb"),
            local_strategy=LocalStrategy.COPY,
        )
    return _speaker_verification


def analyze_visual(video_path: str, scene_prompt: str | None = None) -> str:
    model, processor = _load_videochat3()
    from qwen_vl_utils import process_vision_info

    messages = [{"role": "user", "content": [
        {"type": "video", "video": video_path},
        {"type": "text", "text": _build_qa_prompt(scene_prompt)},
    ]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    images, videos, video_kwargs = process_vision_info(
        messages, image_patch_size=14, return_video_kwargs=True, return_video_metadata=True,
    )
    # return_video_metadata=True makes each `videos` entry a (tensor, metadata)
    # tuple. Per transformers' own video_processor docs (main_classes/video_processor),
    # video_metadata must be routed through the modality-specific `videos_kwargs={}`
    # dict (the "recommended API" in ProcessingMixin._merge_kwargs's own docstring),
    # not as a flat top-level kwarg to processor() -- a flat video_metadata= kwarg
    # was tried first and silently failed to route through, reproducing the original
    # KeyError('video_metadata') from processing_videochat3.py's videos_inputs.pop().
    #
    # video_metadata must additionally be DOUBLY nested: transformers'
    # BaseVideoProcessor._prepare_input_videos does
    # `[metadata for batch_list in video_metadata for metadata in batch_list]`,
    # i.e. it expects list[list[dict]] (one inner list per video). Passing a
    # flat list[dict] made `batch_list` bind to the single dict itself, and
    # iterating a dict yields its KEYS -- silently corrupting video_metadata
    # into ['fps', 'frames_indices', ...] instead of the real metadata,
    # which then crashed VideoChat3's own __call__ with
    # AttributeError: 'str' object has no attribute 'fps'.
    # `processing_videochat3.py`'s __call__ does `metadata.fps`,
    # `metadata.timestamps` (a computed property), etc. -- attribute access
    # against the model's own VideoChat3VideoMetadata class, not a plain
    # dict or a hand-rolled stand-in (tried types.SimpleNamespace first;
    # it's missing computed properties like `.timestamps` that only the
    # real class provides). transformers' generic BaseVideoProcessor
    # plumbing doesn't convert the raw dicts qwen_vl_utils produces into
    # this class for the pre-decoded-tensor path this app uses, so
    # construct real instances directly -- the class is dynamically
    # registered in sys.modules once the model/processor is loaded
    # (trust_remote_code=True), found by module-name substring rather than
    # hardcoding the model's content-hash revision directory.
    import sys

    videochat3_utils = next(m for name, m in sys.modules.items() if name.endswith(".videochat3_utils"))
    VideoChat3VideoMetadata = videochat3_utils.VideoChat3VideoMetadata

    videos_kwargs = {}
    if videos:
        videos_kwargs["video_metadata"] = [[VideoChat3VideoMetadata(**v[1])] for v in videos]
        videos = [v[0] for v in videos]
    inputs = processor(
        text=text, images=images, videos=videos, videos_kwargs=videos_kwargs,
        do_resize=False, return_tensors="pt", **(video_kwargs or {}),
    )
    inputs = inputs.to(model.device)
    generated_ids = model.generate(**inputs, max_new_tokens=512, do_sample=False)
    trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, generated_ids)]
    return processor.tokenizer.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0].strip()


def _extract_audio(video_path: str) -> str:
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    import os

    os.close(fd)
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", wav_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr[-500:]}")
    return wav_path


def _load_wav_16k(path: str):
    """Loads audio and resamples to the 16kHz mono `verify_batch` expects.
    Deliberately bypasses SpeakerRecognition.load_audio(), which hardcodes
    LocalStrategy.SYMLINK internally (speechbrain/inference/interfaces.py)
    regardless of what strategy the model itself was loaded with -- on
    Windows without Developer Mode that fails for every input file, not
    just the pretrained weights. Loading directly through the (already
    monkeypatched, soundfile-backed) torchaudio.load sidesteps it."""
    import torch
    import torchaudio

    waveform, sample_rate = torchaudio.load(path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != 16000:
        waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
    return waveform


def analyze_voice(video_path: str, reference_audio_paths: list[str]) -> list[dict[str, Any]]:
    if not reference_audio_paths:
        return []
    verification = _load_speaker_verification()
    clip_audio_path = _extract_audio(video_path)
    try:
        clip_wav = _load_wav_16k(clip_audio_path)
        results = []
        for ref_path in reference_audio_paths:
            ref_wav = _load_wav_16k(ref_path)
            score, prediction = verification.verify_batch(ref_wav, clip_wav)
            results.append({
                "reference_path": ref_path,
                "score": float(score[0]),
                "same_speaker": bool(prediction[0]),
            })
        return results
    finally:
        Path(clip_audio_path).unlink(missing_ok=True)


def run_qa(
    video_path: str,
    reference_audio_paths: list[str],
    release_wangp_model,
    scene_prompt: str | None = None,
) -> dict[str, Any]:
    release_wangp_model()
    return {
        "visual_analysis": analyze_visual(video_path, scene_prompt),
        "voice_results": analyze_voice(video_path, reference_audio_paths),
        "analyzed_at": time.time(),
    }
