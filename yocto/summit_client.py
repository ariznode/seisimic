import logging
import tomllib
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

GenesisText = str
Json = Any


class SummitClient:
    def __init__(self, url: str):
        self.url = url

    def _get(self, path: str) -> str:
        response = requests.get(f"{self.url}/{path}")
        response.raise_for_status()
        return response.text

    def _post_text(self, path: str, body: str) -> str:
        response = requests.post(
            f"{self.url}/{path}",
            data=body,
            headers={"Content-Type": "text/plain"},
        )
        response.raise_for_status()
        return response.text

    def health(self) -> str:
        return self._get("health")

    def get_public_key(self) -> str:
        return self._get("get_public_key")

    def send_share(self, share: str) -> str:
        return self._post_text("send_share", share)

    def send_genesis(self, genesis: GenesisText) -> str:
        self.validate_genesis_text(genesis)
        return self._post_text("send_genesis", genesis)

    def post_genesis_filepath(self, path: Path):
        text = self.load_genesis_file(path)
        self.send_genesis(text)

    @staticmethod
    def load_genesis_file(path: Path) -> GenesisText:
        with open(path) as f:
            return f.read()

    @staticmethod
    def validate_genesis_text(genesis: GenesisText) -> dict[str, Any]:
        try:
            return tomllib.loads(genesis)
        except tomllib.TOMLDecodeError as e:
            logger.error(
                "\n".join(
                    [
                        f"Failed to parse genesis as toml: {e}",
                        "File contents:",
                        genesis,
                    ]
                )
            )
            raise e

    @classmethod
    def load_genesis_toml(cls, path: Path) -> dict[str, Any]:
        text = cls.load_genesis_file(path)
        return cls.validate_genesis_text(text)
