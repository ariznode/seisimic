from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildPaths:
    def __init__(self, home: str):
        self.home = Path(home)

    @property
    def yocto_manifests(self) -> Path:
        return self.home / "yocto-manifests"

    @property
    def artifacts(self) -> Path:
        return self.yocto_manifests / "reproducible-build/artifacts"

    @staticmethod
    def artifact_prefix() -> str:
        return "cvm-image-azure-tdx.rootfs"

    @property
    def meta_seismic(self) -> Path:
        return self.home / "meta-seismic"

    @property
    def measured_boot(self) -> Path:
        return self.home / "measured-boot"

    @property
    def enclave_bb(self) -> str:
        return "recipes-nodes/enclave/enclave.bb"

    @property
    def sreth_bb(self) -> str:
        return "recipes-nodes/reth/reth.bb"

    @property
    def summit_bb(self) -> str:
        return "recipes-nodes/summit/summit.bb"

    @property
    def repo_root(self) -> Path:
        return self.home / "deploy"

    @property
    def deploy_script(self) -> Path:
        return self.repo_root / "deploy.sh"

    @property
    def deploy_metadata(self) -> Path:
        return self.repo_root / "deploy_metadata.json"

    @property
    def proxy_client(self) -> Path:
        return self.home / "cvm-reverse-proxy/build/proxy-client"

    @property
    def source_env(self) -> Path:
        return self.home / "yocto-manifests/build/srcs/poky"
