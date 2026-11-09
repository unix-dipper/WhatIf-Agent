from __future__ import annotations

from pathlib import Path
import json

from .errors import ExternalToolError, ValidationError
from .utils import run_command


class PiperTTS:
    def __init__(self, executable: str, model: Path, config: Path | None, logger):
        self.executable = executable
        self.model = model
        self.config = config
        self.logger = logger

    def validate(self) -> None:
        if not self.model.is_file():
            raise ValidationError(f"Piper voice model does not exist: {self.model}")
        if self.config and not self.config.is_file():
            raise ValidationError(f"Piper voice config does not exist: {self.config}")

    def synthesize(self, text: str, output: Path) -> None:
        self.validate()
        args = [self.executable, "--model", self.model, "--output_file", output]
        if self.config:
            args.extend(["--config", self.config])
        run_command(args, logger=self.logger, input_text=text)
        if not output.is_file() or output.stat().st_size == 0:
            raise ExternalToolError(f"Piper did not create a valid WAV: {output}")


def resolve_narration_audio(
    scene, output: Path, *, piper: PiperTTS | None, force: bool, logger,
    cache_key: str,
) -> Path:
    source = scene.narration_audio
    if source and source.is_file():
        logger.info("Reusing narration for %s: %s", scene.id, source.name)
        return source
    sidecar = output.with_suffix(".json")
    if output.is_file() and output.stat().st_size > 0 and sidecar.is_file() and not force:
        try:
            cached = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = {}
        if cached.get("cache_key") == cache_key:
            logger.info("Reusing generated narration for %s", scene.id)
            return output
    if piper is None:
        raise ValidationError(
            f"No narration WAV is available for {scene.id}. Configure Piper or set narration_audio in the episode."
        )
    logger.info("Generating narration for %s", scene.id)
    piper.synthesize(scene.narration, output)
    sidecar.write_text(json.dumps({"cache_key": cache_key}, indent=2), encoding="utf-8")
    return output
