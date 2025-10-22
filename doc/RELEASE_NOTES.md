# Temperature-bot release notes

## 2025-10-22 Update

* Added `make deploy`
* Added bulk select/unselect of sensor charts
* Implement `all` button for charts
* Show all sensors on charts page, disabling those that were not active
* Highlight selected date range
* Highlight selected menu item
  * Known issue: Some of the items in the menu are not selections, so display wonky. Best answer
    will probably be to move them into a hamburger menu.

## 2025-10-21 Update

* Added Centigrade/Fahrenheit switch
  * Known issue: Update on the "TEPERATURE BOT" page lags for a few seconds
* Slightly prettier margins
* Fixes to tooling for better startup on new machines
* Added `make clean` and `make cleanall`

## 2025-10-13 Update

* Changing a device fan motor or speed now disables rules on that device for 3 hours
* Air quality variables can now be used in rules
* Dropdown on chart now only appears if you specify ?dropdown=1
