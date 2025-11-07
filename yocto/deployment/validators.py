import argparse
import json
import tempfile
from pathlib import Path

from yocto.cloud.azure import CONSENSUS_PORT
from yocto.cloud.cloud_api import CloudApi
from yocto.cloud.cloud_config import CloudProvider
from yocto.config import get_domain_record_prefix, get_genesis_vm_prefix
from yocto.utils.metadata import load_metadata
from yocto.utils.summit_client import SummitClient


def _genesis_vm_name(node: int, cloud: CloudProvider) -> str:
    """Get genesis VM name for the given node and cloud provider."""
    prefix = get_genesis_vm_prefix(cloud)
    return f"{prefix}-{node}"


def _genesis_client(node: int, cloud: CloudProvider) -> SummitClient:
    """Create a genesis client for the given node and cloud provider."""
    prefix = get_domain_record_prefix(cloud)
    return SummitClient(
        f"https://{prefix}-{node}.seismictest.net/summit"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--nodes", type=int, default=4)
    parser.add_argument(
        "--code-path",
        default="",
        type=str,
        help="path to code relative to $HOME",
    )
    parser.add_argument(
        "--cloud",
        type=str,
        default="azure",
        choices=["azure", "gcp"],
        help="Cloud provider (azure or gcp)",
    )
    return parser.parse_args()


def _get_pubkeys(
    home: Path,
    node_clients: list[tuple[int, SummitClient]],
    cloud: str,
    cloud_provider: CloudProvider,
) -> tuple[list[dict[str, str]], dict[int, str]]:
    metadata = load_metadata(str(home))
    cloud_resources = metadata["resources"].get(cloud, {})

    validators = []
    node_to_pubkey = {}
    for node, client in node_clients:
        vm_name = _genesis_vm_name(node, cloud_provider)
        if vm_name not in cloud_resources:
            raise ValueError(f"VM {vm_name} not found in {cloud} metadata")

        meta = cloud_resources[vm_name]
        ip_address = meta["public_ip"]
        try:
            pubkey = client.get_public_key()
            validators.append(
                {
                    "public_key": pubkey,
                    "ip_address": f"{ip_address}:{CONSENSUS_PORT}",
                }
            )
            node_to_pubkey[node] = pubkey
        except Exception as e:
            print(f"Error: {e}")
            raise e
    return validators, node_to_pubkey


def _post_shares(
    tmpdir: str,
    node_clients: list[tuple[int, SummitClient]],
    node_to_pubkey: dict[int, str],
):
    genesis_file = f"{tmpdir}/genesis.toml"
    genesis_toml = SummitClient.load_genesis_toml(genesis_file)
    validators = genesis_toml["validators"]

    for node, client in node_clients:
        share_index = next(
            i
            for i, v in enumerate(validators)
            if v["public_key"] == node_to_pubkey[node]
        )
        ip = validators[share_index]["ip_address"]
        share_file = f"{tmpdir}/node{share_index}/share.pem"
        with open(share_file) as f:
            share = f.read()
            msg = (
                f"Posting share {share} to node {node} @ {ip} "
                f"/ {node_to_pubkey[node]}"
            )
            print(msg)
            client.send_share(share)


def main():
    args = _parse_args()
    cloud = CloudProvider(args.cloud)
    node_clients = [
        (n, _genesis_client(n, cloud)) for n in range(1, args.nodes + 1)
    ]

    tmpdir = tempfile.mkdtemp()
    home = Path.home() if not args.code_path else Path.home() / args.code_path

    summit_path = str(home / "summit")
    summit_genesis_target = f"{summit_path}/target/debug/genesis"
    summit_example_genesis = f"{summit_path}/example_genesis.toml"

    validators, node_to_pubkey = _get_pubkeys(
        home, node_clients, args.cloud, cloud
    )

    tmp_validators = f"{tmpdir}/validators.json"
    with open(tmp_validators, "w+") as f:
        print(f"Wrote validators to {tmp_validators}")
        json.dump(validators, f, indent=2)

    CloudApi.run_command(
        cmd=[
            summit_genesis_target,
            "-o",
            f"{tmpdir}",
            "-i",
            summit_example_genesis,
            "-v",
            tmp_validators,
        ],
        show_logs=True,
    )

    _post_shares(tmpdir, node_clients, node_to_pubkey)
    for _, client in node_clients:
        client.post_genesis_filepath(f"{tmpdir}/genesis.toml")


if __name__ == "__main__":
    main()
