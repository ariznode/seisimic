# Supervisor

## Install

```sh
sudo apt-get install -y supervisor
```

## Configuration

Copy `devnet/supervisor/devnet.conf` to `/etc/supervisor/conf.d/devnet.conf`
Then run `sudo supervisorctl reload`

## Build

Build the relevant `--release` binaries. You can see which binaries are expected with `sudo supervisorctl status`

## Management

```sh
sudo supervisorctl start all
```
