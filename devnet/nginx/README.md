# Nginx

## Systemctl
Nginx is managed on our machine by `systemctl`. Some useful commands:

Start it:
`sudo systemctl start nginx`

Stop it:
`sudo systemctl stop nginx`

Restart it:
`sudo systemctl restart nginx`

Reload it (does not restart service and only apply changes in conf):
`sudo systemctl reload nginx`

See if it's healthy:
`sudo systemctl status nginx`

## Configuration
The conf files in `deploy/nginx/` tell Nginx what to do when requests come into the machine

First replace the file at `/etc/nginx/nginx.conf` with the one in `deploy/nginx/nginx.conf`.

Then copy `devnet.template` to `/etc/nginx/sites-enabled/devnet.template`. Then set the SERVER_NAME variable in the command below and run it:

```sh
SERVER_NAME="node-0.seismicdev.net" sudo -E sh -c "envsubst '\$SERVER_NAME' < /etc/nginx/sites-enabled/devnet.template > /etc/nginx/sites-enabled/default"
```

## Editing the configuration
First make changes manually on the machine

You can test that they are valid with:
`sudo nginx -t`

To apply the changes:
`sudo systemctl reload nginx`

Then copy the changes over to the `devnet.template` in this repo and make a PR.

## SSL

### Renewing SSL certificate

We have to do this every 90 days. Simply run:
`sudo certbot renew`

### Setting up SSL (One-time)

After you have successfully set up the domain, you can set up SSL. We are running Nginx on Ubuntu. First install Nginx on the machine:

```sh
sudo apt install nginx
```

Then follow the instructions for [Certbot](https://certbot.eff.org/instructions?ws=nginx&os=ubuntufocal). Copied here for convenience:

Install certbot:
```sh
sudo snap install --classic certbot
```

Perpare certbot command:
```sh
sudo ln -s /snap/bin/certbot /usr/bin/certbot
```

Run certbot itself:

Either:
```sh
sudo certbot --nginx
```

Or make sure to set the --domain and --email in the below command and run it:
```sh
sudo certbot --nginx --non-interactive --renew-by-default --agree-tos --email "c@seismic.systems" --domain node-0.seismicdev.net
```
