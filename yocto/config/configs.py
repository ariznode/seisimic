"""Top-level Configs dataclass."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yocto.config.build_config import BuildConfigs
from yocto.config.deploy_config import DeployConfigs
from yocto.config.mode import Mode
from yocto.utils.parser import parse_args


@dataclass
class Configs:
    mode: Mode
    build: BuildConfigs | None
    deploy: DeployConfigs | None
    show_logs: bool
    home: str

    @staticmethod
    def parse() -> "Configs":
        args = parse_args()
        mode = Mode.from_args(args)
        build = BuildConfigs.from_args(args) if args.build else None
        deploy = DeployConfigs.from_args(args) if args.deploy else None
        show_logs = args.logs
        if deploy and not build and not deploy.artifact:
            raise ValueError(
                "If running with --deploy and not --build, "
                "you must provide an --artifact to deploy"
            )
        home_path = (
            Path.home() if not args.code_path else Path.home() / args.code_path
        )
        return Configs(
            mode=mode,
            build=build,
            deploy=deploy,
            show_logs=show_logs,
            home=str(home_path),
        )

    def to_dict(self) -> dict[str, Any]:
        kwargs = {}
        if self.build:
            kwargs["build"] = self.build.to_dict()
        if self.deploy:
            kwargs["deploy"] = self.deploy.to_dict()
        return {
            "mode": self.mode.to_dict(),
            **kwargs,
            "show_logs": self.show_logs,
        }
