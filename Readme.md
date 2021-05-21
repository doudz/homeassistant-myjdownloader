# MyJDownloader Integration for Home Assistant

![Tests](https://github.com/doudz/homeassistant-myjdownloader/workflows/Tests/badge.svg)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

**This is still beta! Feedback, bug reports and contributions welcome!**

![Device](jdownloader.png)

## Configuration

Add this repository to HACS, install it, then go to Configuration > Integrations > Add Integration > Choose "MyJDownloader" and enter your email address and password.

**Note:** Do not disable the `sensor.jdownloaders_online` entity, as it is responsible for checking for new JDownloaders which become online.

## Features

**Sensor**

- status
- number of links
- number of packages

**Binary Sensor**

- update available

**Switch**

- pause downloads
- limit download speed

**Service**

- `myjdwonloader.run_update_check`
- `myjdwonloader.restart_and_update`
- `myjdwonloader.start_downloads`
- `myjdwonloader.stop_downloads`

## Known Issues

- [ ] When using the pause switch, it might take a while for the status sensor to reflect the new pause state.
- [ ] There is not much error handling yet, e.g. when you change your password, you need to remove and add the integration again.
