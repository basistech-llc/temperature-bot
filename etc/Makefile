SYSTEMD_UNITS ?= $(wildcard *.service *.timer)

.PHONY: install
install:
	sudo cp -f $(SYSTEMD_UNITS) /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl restart $(SYSTEMD_UNITS)
