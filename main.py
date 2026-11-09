from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whatif.config import Config
from whatif.diagnostics import diagnose
from whatif.episode import load_episode
from whatif.errors import WhatIfError
from whatif.ai import GenerationOptions, OllamaClient, OllamaError, StoryGenerationPipeline
from whatif.ai.validation import validate_plan
from whatif.pipeline import render_episode
from whatif.tts import PiperTTS
from whatif.utils import executable_available, setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WhatIf Agent local narrated-video production engine.")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--episode", type=Path, help="Episode JSON to render.")
    parser.add_argument("--check", action="store_true", help="Run installation and input diagnostics.")
    parser.add_argument("--ai-check", action="store_true", help="Check the local Ollama service and configured model.")
    parser.add_argument("--list-models", action="store_true", help="List models installed in Ollama.")
    parser.add_argument("--generate", metavar="TOPIC", help="Generate a story plan from a hypothetical topic.")
    parser.add_argument("--duration", type=float, default=None, help="Target generated episode length in minutes.")
    parser.add_argument("--model", help="Ollama model name for generation.")
    parser.add_argument("--review", type=Path, help="Review a generated planning.json or episode.json.")
    parser.add_argument("--force", action="store_true", help="Regenerate all narration, clips, and output.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = Config.load(args.config)
        logger = setup_logging(Path("logs"), args.verbose)
        client = OllamaClient(config.ollama_url, timeout=config.ai_timeout_seconds)
        if args.ai_check or args.list_models:
            client.check()
            models = client.list_models()
            if args.list_models:
                for model in models:
                    print(model.name)
            else:
                selected = args.model or config.ai_model
                print(f"Ollama: available ({config.ollama_url})")
                print(f"Configured model: {selected} ({'installed' if any(m.name == selected for m in models) else 'not installed'})")
            return 0
        if args.generate:
            selected = args.model or config.ai_model
            if not client.has_model(selected):
                raise WhatIfError(
                    f"Ollama model '{selected}' is not installed. Run --list-models and install it explicitly with Ollama."
                )
            options = GenerationOptions(
                model=selected,
                duration_minutes=args.duration or 6.0,
                temperature=config.ai_temperature,
                max_tokens=config.ai_max_tokens,
                retries=config.ai_retries,
            )
            result = StoryGenerationPipeline(
                client, Path(config.ai_output_dir), logger=logger
            ).generate(args.generate, options)
            generated_episode = Path(result["directory"]) / "episode.json"
            load_episode(generated_episode)
            print(f"Generated episode: {generated_episode}")
            print(f"Planning data: {Path(result['directory']) / 'planning.json'}")
            for warning in result["warnings"]:
                print(f"Warning: {warning}")
            return 0
        if args.review:
            review_path = args.review
            if review_path.name == "planning.json":
                import json
                plan = json.loads(review_path.read_text(encoding="utf-8"))
                report = validate_plan(plan, target_minutes=float(plan.get("generation", {}).get("target_duration_minutes", 6)))
                print(f"Title: {plan.get('title', '(missing)')}")
                print(f"Scenes: {len(plan.get('scenes', []))}")
                print(f"Words: {sum(len(str(s.get('narration', '')).split()) for s in plan.get('scenes', []))}")
                for warning in report.warnings:
                    print(f"Warning: {warning}")
                report.raise_if_invalid()
            else:
                episode = load_episode(review_path)
                print(f"Valid Phase 1 episode: {episode.title} ({len(episode.scenes)} scenes)")
            return 0
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
    except OllamaError as exc:
        print(f"Ollama error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
