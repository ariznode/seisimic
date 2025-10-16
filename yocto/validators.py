import argparse
import json
import tempfile
from pathlib import Path

from yocto.azure_common import CONSENSUS_PORT, AzureCLI
from yocto.metadata import load_metadata
from yocto.summit_client import SummitClient


def _genesis_vm_name(node: int) -> str:
    return f"yocto-genesis-{node}"


def _genesis_client(node: int) -> SummitClient:
    return SummitClient(f"https://summit-genesis-{node}.seismictest.net/summit")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--nodes", type=int, default=4)
    parser.add_argument(
        "--code-path",
        default="",
        type=str,
        help="path to code relative to $HOME",
    )
    return parser.parse_args()


def _get_pubkeys(
    home: Path,
    node_clients: list[tuple[int, SummitClient]],
) -> tuple[list[dict[str, str]], dict[int, str]]:
    resources = load_metadata(str(home))["resources"]

    validators = []
    node_to_pubkey = {}
    for node, client in node_clients:
        meta = resources[_genesis_vm_name(node)]
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
            print(
                f"Posting share {share} to node {node} @ {ip} / {node_to_pubkey[node]}"
            )
            client.send_share(share)


def main():
    args = _parse_args()
    node_clients = [(n, _genesis_client(n)) for n in range(1, args.nodes + 1)]

    tmpdir = tempfile.mkdtemp()
    home = Path.home() if not args.code_path else Path.home() / args.code_path

    summit_path = str(home / "summit")
    summit_genesis_target = f"{summit_path}/target/debug/genesis"
    summit_example_genesis = f"{summit_path}/example_genesis.toml"

    validators, node_to_pubkey = _get_pubkeys(home, node_clients)

    tmp_validators = f"{tmpdir}/validators.json"
    with open(tmp_validators, "w+") as f:
        print(f"Wrote validators to {tmp_validators}")
        json.dump(validators, f, indent=2)

    AzureCLI.run_command(
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
