# Azure Devbox

## Setting up the VM
* Go to the `Create a virtual machine` page

### Basics
* Virtual machine name: [give it a name]
* Region: `EAST US 2`
* Availability Zone: `Zone 2`
* Security type: `Confidential virtual machine`
* Image: `Ubuntu Server 24.04 LTS (Confidential VM) - x64 Gen2`. It will nested under `Ubuntu 24.04 LTS - All Plans including Ubuntu Pro`
* Size: `Standard E8as v6 (8 vcpus, 64 GiB memory)`. Other sizes probably work too, but I haven't tested them. Smaller sizes may not be able to run Reth
* Select inbound ports: [I often pick allow all]

### Disks
Turn on `Confidential OS disk encryption`

For OS disk size, the default (30GiB) is usually fine. However, if Reth runs for a long time (or restores from a snapshot with a lot of state), the OS disk size should be large (e.x. 1 TiB)

### Networking
Turn on `Delete public IP and NIC when VM is deleted`

### Create
You are ready to click the blue `create` button


## Installing Dependencies
`setup.sh` is a script that installs all the necessary dependencies for the devbox. Copy `setup.sh` to the devbox. Then run it:
```
chmod +x setup.sh
./setup.sh
```

### While running the script
Handle interactive prompts: You may need to press enter, type yes, etc.
If a purple prompt appears, press escape to accept the default provided

## Post Installation
- You need to exit and re-enter the shell to get the environment variables to be set, particularly for cargo/rust to work
- On the azure machine, add your ssh pub key to `~/.ssh/authorized_keys` so that you can ssh into the machine
  - `../ssh/authorized_keys` has a list of keys for the company if you intend to have others use the box
- Copy over the devnet.conf supervisorctl config to /etc/supervisor/conf.d/devnet.conf - it may need to be adjusted per your use case. e.g actions runners have a differnt conf becuase reth builds in a differnt spot, then reload supervisor so the conf is active
- (Optional) Generate a new ssh key for the machine itself with `ssh-keygen -t ed25519 -C "your_email@example.com"` and add it to github
