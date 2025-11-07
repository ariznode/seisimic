import logging
import signal
import sys
import traceback

from yocto.config import Configs
from yocto.deployment.deploy import Deployer, delete_vm
from yocto.image.build import maybe_build
from yocto.utils.artifact import delete_artifact
from yocto.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main() -> int:
    setup_logging()

    configs = Configs.parse()

    if configs.mode.delete_vm:
        delete_vm(configs.mode.delete_vm, configs.home)

    if configs.mode.delete_artifact:
        delete_artifact(configs.mode.delete_artifact, configs.home)

    should_deploy = maybe_build(configs)
    if not should_deploy:
        return

    assert configs.deploy  # should never happen

    image_path, measurements = should_deploy
    deployer = Deployer(
        configs=configs.deploy,
        image_path=image_path,
        measurements=measurements,
        ip_name=configs.deploy.vm.resource_group,
        home=configs.home,
        show_logs=configs.show_logs,
    )

    def deploy_signal_handler(signum, frame):
        """Handle cleanup on signals"""
        logger.info("Received signal to terminate")
        if deployer:
            deployer.cleanup()
        sys.exit(0)

    # Setup signal handlers for cleanup
    signal.signal(signal.SIGINT, deploy_signal_handler)
    signal.signal(signal.SIGTERM, deploy_signal_handler)

    try:
        deploy_output = deployer.deploy()
        deploy_output.update_deploy_metadata()
        deployer.start_proxy_server(deploy_output.public_ip)
        return 0
    except Exception as e:
        logger.error(f"Failed: {str(e)}\n{traceback.format_exc()}")
        return 1
    finally:
        deployer.cleanup()


if __name__ == "__main__":
    exit(main())
