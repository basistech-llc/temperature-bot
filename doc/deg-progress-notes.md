# Progress notes

# 19 Oct, 2025

- First read of code
- Cursor-driven code review to identify unclear areas
- VPN configured
- Accessed slg1.basistech.net via browser
- Accessed slg1.basistech.net via ssh
- Updated password

# 20 Oct, 2025

- Reviewed nginx config
-


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

### deployments config
- /etc/*_service has the service control files for each copy
- Each need to be copied (and renamed slightly) into /etc/systemd/system


## Questions

- in /etc/nginx, what is causing default routing to air.basistech.net (e.g. of deg1, before I
  configured it). Is this desirable behavior, or more confusing than it is worth?
- Do we have any automation for deploying <repo>/etc/*_service to /etc/systemd/system/*.service?

## Todo

- Move /etc/nginx config files to git in <repo>/etc


## Currently stuck on
