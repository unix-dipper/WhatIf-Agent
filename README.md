# WhatIf Agent

WhatIf Agent is a local-first Phase 1 production engine. It consumes an episode JSON file, scene images, and either prerecorded WAV narration or a local Piper voice model, then creates scene MP4 clips, an SRT subtitle file, a manifest, and a final H.264/AAC MP4.

The sample uses original SVG placeholder graphics and generated tone WAVs. These are test assets, not AI-generated cinematic media. Replace them with your own licensed images and narration before publishing.

## Requirements

- Windows 10/11, Python 3.10+ (3.12 is supported by the standard-library code).
- FFmpeg and FFprobe available on PATH. On Windows, install a current build from the official FFmpeg download page or a package manager, then verify `ffmpeg -version` and `ffprobe -version` in a new PowerShell window.
- Piper installed locally, plus a compatible `.onnx` voice model and companion JSON file, only for generating narration. Piper is optional when episode scenes provide `narration_audio`.
- No CUDA, Docker, WSL, cloud API, or paid service is required.

## Install in PowerShell

```powershell
cd C:\path\to\WhatIf-Agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python main.py --check
```

If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process Bypass` for the current terminal, or run `.venv\Scripts\python.exe` directly.

## First sample render

The checked-in sample has prerecorded WAV files, so it tests the media pipeline without Piper:

```powershell
python main.py --episode episode\scenes.json
```

Outputs are written to `episode\output\whatif_episode.mp4`, `whatif_episode.srt`, and `manifest.json`; reusable WAV and scene clips remain in `episode\audio` and `episode\clips`. Run `python main.py --episode episode\scenes.json --force` to rebuild everything. If the process is interrupted, rerun without `--force` to reuse completed assets.

The engine renders 1920x1080 at 30 FPS by default. For a faster local test, temporarily set `"resolution": "1280x720"` in `config.json`, then restore 1080p for delivery. FFmpeg uses CPU encoding with two threads and a `veryfast` preset, suitable for an integrated-GPU machine.

## Episode format

Paths are relative to the JSON file and are prevented from escaping its directory. Required fields are `title`, `description`, `language`, `resolution`, and a non-empty `scenes` array. Each scene requires a unique `id`, an existing `image`, and non-empty `narration`.

Optional scene fields include `narration_audio`, `image_prompt`, `transition`, `duration_hint`, and `sound_effects`. `duration_hint` is retained for compatibility but actual WAV duration controls timing. Music can be added with a top-level `"music": "music/track.mp3"`; it loops, is reduced to the configured volume, and is mixed under narration. Do not add copyrighted media without permission.

## Piper setup

Set `voice_model` to the model path, `voice_config` to its companion JSON path, and `piper` to the executable or full path in `config.json`. The application never downloads models automatically. Follow the installation instructions for the Piper distribution you choose, and confirm the executable works before rendering. If `narration_audio` exists for a scene, it is used without Piper.

## Diagnostics and troubleshooting

`python main.py --check --episode episode\scenes.json` reports Python, FFmpeg, FFprobe, Piper, model, output-directory, and episode status. Common fixes:

- **Command not found:** add the FFmpeg/Piper directory to Windows PATH, open a new PowerShell window, and rerun diagnostics.
- **Piper model missing:** confirm both the `.onnx` model and companion JSON path; do not point at a directory.
- **Image rejected:** use a path inside the episode directory and verify its spelling. SVG, PNG, JPG, and other formats supported by your FFmpeg build are acceptable.
- **Output locked:** close the MP4 in a media player and rerun; output and intermediates are never deleted automatically.
- **Subtitles are approximate:** Phase 1 distributes phrase-sized cues by character weight across the actual scene WAV duration. It does not claim word-level alignment.

## Architecture and roadmap

`episode.py` validates the future-compatible JSON contract. `tts.py` isolates Piper. `video.py` creates deterministic restrained motion and assembles clips. `subtitles.py` creates SRT cues. `pipeline.py` coordinates sequential, resumable work and writes a manifest. `diagnostics.py` makes missing local tools explicit.

Phase 2 can write the same JSON directly from a local story generator. Phase 3 can place generated images at the referenced paths; the production engine does not need to know how they were made. Future providers can implement the small narration boundary represented by `PiperTTS`.

## Known limitations

- No automatic image generation, story generation, word-level subtitle alignment, GUI, or cloud integration.
- Scene pause is represented in subtitle timing metadata but clips are concatenated without inserted silent pause frames; narration itself is never cut off.
- Music fade-out uses a conservative long-tail filter because final duration is established by the concatenated clips.
- Windows FFmpeg/Piper installation is environment-specific and must be verified locally.

## Testing

```powershell
python -m pytest -q
python -m compileall main.py whatif tests
```

The unit tests cover JSON validation, path safety, missing images, configuration errors, subtitle formatting, and WAV duration. A real FFmpeg render and Piper integration test must be run on a machine where those external tools and a voice model are installed.
