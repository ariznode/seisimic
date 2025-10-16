#!/usr/bin/env bash

# Exit immediately if any command fails, and treat unset variables as errors
set -euo pipefail

echo "Updating package information..."
sudo apt-get -yq update

# Install Basic Dev Tools
echo "Installing basic dev tools..."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq \
  build-essential \
  ocaml \
  ocamlbuild \
  automake \
  autoconf \
  libtool \
  wget \
  python-is-python3 \
  libssl-dev \
  git \
  cmake \
  perl \
  libcurl4-openssl-dev \
  protobuf-compiler \
  libprotobuf-dev \
  debhelper \
  reprepro \
  unzip \
  pkgconf \
  libboost-dev \
  libboost-system-dev \
  libboost-thread-dev \
  lsb-release \
  libsystemd0 \
  clang \
  tpm2-tools \
  libtss2-dev

# Downgrade to Node.js 18 for compatibility
echo "Installing Compatible Node.js..."
sudo apt purge nodejs npm
wget https://nodejs.org/dist/v18.19.1/node-v18.19.1-linux-x64.tar.xz
sudo tar -xJf node-v18.19.1-linux-x64.tar.xz -C /usr/ --strip-components=1
rm node-v18.19.1-linux-x64.tar.xz

# Install SGX SDK
# Followed instructions from https://github.com/intel/SGXDataCenterAttestationPrimitives/tree/main/QuoteGeneration
# Note: The SGX driver is pre-installed by Azure, while the sdk is not. 
## You can confirm the driver is installed by running 
## 'grep CONFIG_X86_SGX /boot/config-$(uname -r)' and seeing 'CONFIG_X86_SGX=y'
# Note: the latest sgx sdk distro will change over time
## find the latest sdk distro here: https://download.01.org/intel-sgx/latest/linux-latest/distro/ubuntu24.04-server/
SGX_SDK_BIN="sgx_linux_x64_sdk_2.26.100.0.bin"
echo "Installing SGX SDK..."
if [ ! -d "/opt/intel" ]; then
  sudo mkdir /opt/intel
fi
cd /opt/intel
sudo wget -O ./"$SGX_SDK_BIN" "https://download.01.org/intel-sgx/latest/linux-latest/distro/ubuntu24.04-server/$SGX_SDK_BIN"
sudo chmod +x "$SGX_SDK_BIN"
echo "Current directory: $(pwd)"
echo "yes" | sudo ./"$SGX_SDK_BIN"
sudo chown "$USER:$USER" "/opt/intel/sgxsdk/environment"
export PKG_CONFIG_PATH=${PKG_CONFIG_PATH:-""}
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-""}
source "/opt/intel/sgxsdk/environment"
sudo rm -f "$SGX_SDK_BIN"
cd $HOME

# Install SGX Software Packages
# See https://download.01.org/intel-sgx/latest/linux-latest/docs/Intel_SGX_SW_Installation_Guide_for_Linux.pdf
echo "Installing SGX Software Packages..."
wget -O sgx_debian_local_repo.tgz https://download.01.org/intel-sgx/latest/linux-latest/distro/ubuntu24.04-server/sgx_debian_local_repo.tgz
tar xzf sgx_debian_local_repo.tgz
echo 'deb [signed-by=/etc/apt/keyrings/intel-sgx-keyring.asc arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu jammy main' | sudo tee /etc/apt/sources.list.d/intel-sgx.list
wget -O intel-sgx-deb.key https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key
cat intel-sgx-deb.key | sudo tee /etc/apt/keyrings/intel-sgx-keyring.asc > /dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq update
# sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install libsgx-epid libsgx-quote-ex libsgx-dcap-ql # necessary for 22.04 but not 24.04
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev # missing from installation guide, but necessary on some architectures? 
sudo usermod -aG sgx "$USER"
sudo usermod -aG sgx_prv "$USER"
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install libsgx-dcap-default-qpl
rm sgx_debian_local_repo.tgz
rm -rf sgx_debian_local_repo
rm intel-sgx-deb.key

# Build DCAP Quote Generation
echo "Building DCAP Quote Generation..."
git clone --recurse-submodules https://github.com/intel/SGXDataCenterAttestationPrimitives.git
cd SGXDataCenterAttestationPrimitives/QuoteGeneration/
./download_prebuilt.sh
make
cd $HOME
rm -rf SGXDataCenterAttestationPrimitives

# Setup qncl file 
# based on https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/main/QuoteGeneration/qcnl/linux/sgx_default_qcnl_azure.conf
# need to replace the /etc/sgx_default_qcnl.conf with this json for pccs to work
echo "Setting up qncl file..."
cat << 'EOF' | sudo tee /etc/sgx_default_qcnl.conf >/dev/null
{
    "pccs_url": "https://global.acccache.azure.net/sgx/certification/v4/",
    "use_secure_cert": true,
    "collateral_service": "https://api.trustedservices.intel.com/sgx/certification/v4/",
    "pccs_api_version": "3.1",
    "retry_times": 6,
    "retry_delay": 5,
    "local_pck_url": "http://169.254.169.254/metadata/THIM/sgx/certification/v4/",
    "pck_cache_expire_hours": 48,
    "verify_collateral_cache_expire_hours": 48,
    "custom_request_options" : {
        "get_cert" : {
            "headers": {
                "metadata": "true"
            },
            "params": {
                "api-version": "2021-07-22-preview"
            }
        }
    }
}
EOF

# Install Rust
# Note: you need to exit and the shell and re-enter to get the environment variables to be set
echo "Installing Rust..."
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Install Docker
## Add Docker's official GPG key:
echo "Installing Docker..."
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq update
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
## Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq update
## Install Docker Packeges:
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
## set up docker group
sudo usermod -aG docker $USER
newgrp docker

# Install supervisorctl
echo "Installing supervisorctl..."
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install supervisor

# Install lz4 for tar compression
echo "Installing lz4..."
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install lz4

# restart services to make sure things are as updated as possible
echo "Restarting services..."
sudo DEBIAN_FRONTEND=noninteractive apt-get -yq install needrestart 
sudo needrestart

echo "All done!"
