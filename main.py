from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whatif.config import Config
from whatif.diagnostics import diagnose
from whatif.episode import load_episode
from whatif.errors import WhatIfError
from whatif.pipeline import render_episode
from whatif.tts import PiperTTS
from whatif.utils import executable_available, setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WhatIf Agent local narrated-video production engine.")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--episode", type=Path, help="Episode JSON to render.")
    parser.add_argument("--check", action="store_true", help="Run installation and input diagnostics.")
    parser.add_argument("--force", action="store_true", help="Regenerate all narration, clips, and output.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = Config.load(args.config)
        logger = setup_logging(Path("logs"), args.verbose)
        episode = load_episode(args.episode) if args.episode else None
        if args.check:
            for key, value in diagnose(config, args.episode).items():
                print(f"{key}: {value}")
            return 0
        if episode is None:
            raise WhatIfError("--episode is required unless --check is used.")
        piper = None
        if config.voice_model:
            if not executable_available(config.piper):
                raise WhatIfError(f"Piper executable is not available: {config.piper}")
            piper = PiperTTS(
                config.piper,
                Path(config.voice_model),
                Path(config.voice_config) if config.voice_config else None,
                logger,
            )
        render_episode(
            episode, config, project_root=Path.cwd(), force=args.force, logger=logger, piper=piper
        )
        return 0
    except KeyboardInterrupt:
        print("Interrupted. Completed intermediate assets were preserved; rerun to resume.", file=sys.stderr)
        return 130
    except WhatIfError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
