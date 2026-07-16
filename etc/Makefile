SERVICE_UNITS ?= *.service

.PHONY: install
install:
	sudo cp -f $(SERVICE_UNITS) /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl restart $(SERVICE_UNITS)
