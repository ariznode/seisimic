#!/bin/sh

# stop all processes first
sudo supervisorctl stop all

# reth data
sudo rm -rf ~/.reth

# temp files
sudo rm -rf /var/tmp/*
sudo rm -rf /tmp/*

# known hosts
sudo rm -rf ~/.ssh/known_hosts

# nginx / letsencrypt
sudo rm -rf /etc/letsencrypt/*
sudo rm -rf /etc/nginx/sites-enabled/default.conf

# logs
sudo find /var/log -type f -exec truncate --size=0 {} \;

# cloud
sudo cloud-init clean -l -s --machine-id -c all

# finally, bash history
rm -f ~/.bash_history
