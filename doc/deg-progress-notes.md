## Notes to self

Looks like I'll be touching this only at the end of each month, so stashing notes, thoughts, and
open tabs here:

- VPN for BasisTech: Tailscale, installed on MacBook deg-mac-2023
- Site links:
  - [main site](https://air.basistech.net/)
  - [Simson's clone](https://slg1.basistech.net/)
  - [David's clone](https://deg1.basistech.net/)
  - [local](http://localhost:8000/)
- Database: Often useful to copy latest database from /var/db on server to each instance. Placed in
  root or var/db.
- Raw view of [Mitsubishi HVAC](http://10.2.1.20/control/index.html). Credentials in
  Bitwarden. Nominal manual [here](http://10.2.1.20/en/maintenance.html) but requires insecure Java
  browser.
- [Git repo](https://github.com/basistech-llc/temperature-bot)
- [ChatGPT project](https://chatgpt.com/g/g-p-68f5f96a17a081918d4bb454409e6602-temperature-bot/project)
- [Maps and other CALA operations notes](https://drive.google.com/drive/folders/1bEr7AV2xa5vEsoc0z8lx5yMtcLWnAdGs)
- [ClickHouse DB](https://clickhouse.com/)
- Related project: [Home Assistant](https://home-assistant.basistech.net/)
- CSS tooling used in this project: [pure.css](https://pure-css.github.io/)
- Other notes in Git repo and Slack with Simson


# Progress notes

## 19 Oct, 2025

- First read of code
- Cursor-driven code review to identify unclear areas
- VPN configured
- Accessed slg1.basistech.net via browser
- Accessed slg1.basistech.net via ssh
- Updated password

## 20 Oct, 2025

- Reviewed nginx config
- Setup nginx and systemctl
- Start testing deployment

## Config notes

- air.basistech.net runs on port 8100
- slg1.basistech.net runs on port 8003
- deg1... will be on 8004

### nginx config

- Sites are in /etc/nginx/sites-available symlinked ti /etc/nginx/sites-enabled
- Logs are in /var/logs/nginx/
- Test config: `sudo nginx -t`
- Restart: `sudo systemctl restart nginx`
- Test status: `sudo systemctl status nginx`

### Local dev config

- `make install-macos`
- `make make-dev-db`
- `make local-dev`
- `make test` (some tests currently fail)

To run the runner locally, you'll need a filled-in temerature-bot-config.yaml

### deployments config

- `git pull ...`, after setting up .ssh
- `make install-ubuntu`
- `<repo>/etc/*.service` has the service control files for each copy
- Each needs to be copied manually into /etc/systemd/system
- Start service with, e.g.,

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now deg1_basistech_net.service
```

- See logs:

```
sudo systemctl status deg1_basistech_net.service
sudo journalctl -u deg1_basistech_net.service -e -n 200
```

## Questions

- in /etc/nginx, what is causing default routing to air.basistech.net (e.g. of deg1, before I
    configured it). Is this desirable behavior, or more confusing than it is worth?
- Do we have any automation for deploying <repo>/etc/_\_service to /etc/systemd/system/_.service?

## Todo

- Move /etc/nginx config files to git in <repo>/etc
- Write tooling to keep live nginx and systemctl files in sync with repo

## Currently stuck on
