"""Etape : generation de config.yaml + secrets.yaml (in-process, sans injection)."""
from __future__ import annotations

from pathlib import Path

from ..configpatch import (assert_no_secrets, backup_if_exists, build_config,
                           build_secrets, write_yaml)
from ..events import Output
from ..pipeline import StepContext


def run_step(ctx: StepContext) -> None:
    lyra = ctx.state.lyra_dir
    example = lyra / "config.yaml.example"
    if not example.exists():
        raise RuntimeError(f"{example} introuvable")

    mapping = {"lyra": str(lyra), "home": str(Path.home())}
    config = build_config(
        example.read_text(encoding="utf-8"),
        ctx.mcps, ctx.state.device_config, mapping,
        ollama_host=ctx.state.ollama_host,
    )
    assert_no_secrets(config, ctx.mcps)

    config_path = lyra / "config.yaml"
    backup = backup_if_exists(config_path)
    if backup:
        ctx.emit(Output(f"Backup : {backup.name}"))
    write_yaml(config_path, config)
    ctx.emit(Output("config.yaml ecrit"))

    secrets_path = lyra / "secrets.yaml"
    existing = secrets_path.read_text(encoding="utf-8") if secrets_path.exists() else ""
    secrets = build_secrets(existing, ctx.mcps, ctx.state.device_config,
                            ctx.state.secrets)
    if secrets:
        backup = backup_if_exists(secrets_path)
        if backup:
            ctx.emit(Output(f"Backup : {backup.name}"))
        write_yaml(secrets_path, secrets, mode=0o600)
        ctx.emit(Output("secrets.yaml ecrit (chmod 600)"))
