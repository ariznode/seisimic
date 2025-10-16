import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yocto Build and Deploy Automation")

    parser.add_argument(
        "--build",
        action="store_true",
        help="Build a new image",
    )
    parser.add_argument("--deploy", action="store_true", help="Deploy an image")
    parser.add_argument("--delete-vm", type=str, help="VM name to delete")
    parser.add_argument("--delete-artifact", type=str, help="Artifact to delete")

    parser.add_argument(
        "--artifact",
        type=str,
        help=(
            "If not running with --build, "
            "use this to specify an artifact to deploy, "
            "e.g. 'cvm-image-azure-tdx.rootfs-20241203182636.wic.vhd'"
        ),
    )
    parser.add_argument(
        "--resource-group",
        type=str,
        help="For deploying: the name of the resource group to create",
    )
    parser.add_argument(
        "-v",
        "--logs",
        action="store_true",
        help="If flagged, print build and/or deploy logs as they run",
        default=False,
    )

    # Git args
    parser.add_argument(
        "--enclave-branch",
        default="seismic",
        help=(
            "Seismic Enclave git branch name. Defaults to 'main'. "
            "Only used if --enclave-commit is provided too"
        ),
    )
    parser.add_argument(
        "--enclave-commit",
        help=(
            "Seismic Enclave git gommit hash. "
            "If not provided, does not change image"
        ),
    )

    parser.add_argument(
        "--sreth-branch",
        default="seismic",
        help=(
            "Seismic Reth git branch name. Defaults to 'seismic'. "
            "Only used if --sreth-commit is provided too"
        ),
    )
    parser.add_argument(
        "--sreth-commit",
        help="Seismic Reth git commit hash. If not provided, does not change image",
    )

    parser.add_argument(
        "--summit-branch",
        default="main",
        help=(
            "Summit git branch name. Defaults to 'main'. "
            "Only used if --summit-commit is provided too"
        ),
    )
    parser.add_argument(
        "--summit-commit",
        help=(
            "Summit git commit hash. "
            "If not provided, does not change image"
        ),
    )

    # Domain args
    parser.add_argument(
        "--domain-record",
        help=(
            "Domain record name (e.g. xxx.seismicdev.net). "
            "Required if deploying"
        ),
    )
    parser.add_argument(
        "--domain-name",
        default="seismicdev.net",
        help="Domain name (e.g. seismicdev.net)",
    )
    parser.add_argument(
        "--domain-resource-group",
        default="devnet2",
        help="Azure domain resource group name (e.g. devnet2)",
    )
    parser.add_argument(
        "--email",
        default="c@seismic.systems",
        help="Email for certbot (e.g. c@seismic.systems)",
    )
    parser.add_argument(
        "--code-path",
        type=str,
        default="",
        help="path of code relative to $HOME",
    )
    return parser.parse_args()
