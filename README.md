# MyJDownloader Integration for Home Assistant

![Tests](https://github.com/doudz/homeassistant-myjdownloader/workflows/Tests/badge.svg)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

**This is still beta! Feedback, bug reports and contributions welcome!**

![Device](jdownloader.png)

## Configuration

Add this repository to HACS, install this integration and restart Home Assistant. Adding MyJDownloader to your Home Assistant instance can be done via the user interface, by using this My button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=myjdownloader)

<details>
  <summary>Manual configuration steps</summary>

- Browse to your Home Assistant instance.
- In the sidebar click on [Configuration](https://my.home-assistant.io/redirect/config).
- From the configuration menu select: [Integrations](https://my.home-assistant.io/redirect/integrations).
- In the bottom right, click on the [Add Integration](https://my.home-assistant.io/redirect/config_flow_start/?domain=myjdownloader) button.
- From the list, search and select "MyJDownloader".
- Follow the instruction on screen to complete the set up.
</details>

## Features

**Sensor**

- status
- number of links
- number of packages

Note: number of links/packages sensors contain state attributes that have information on ETA while downloading.

**Update**

- update to latest version

**Switch**

- pause downloads
- limit download speed

**Button**

- start downloads
- stop downloads
- run update check

**Binary sensor**

- connected to MyJDownloader

**Actions**

- `myjdownloader.add_links`: add links to the LinkGrabber of a JDownloader, selected with `device_id`.

```yaml
action: myjdownloader.add_links
data:
  device_id: 0123456789abcdef0123456789abcdef
  links:
    - https://example.com/file.zip
  priority: default
  autostart: true
```

The actions `myjdownloader.start_downloads`, `stop_downloads`, `run_update_check` and
`restart_and_update` are deprecated since 3.0 and will be removed in 3.2. Use the buttons
and the update entity instead. Targeting entities (`entity_id`) instead of a JDownloader
(`device_id`) is deprecated as well; Home Assistant shows a repair issue when either is used.

## Development

Home Assistant does not run on Windows, so tests run in a Linux container
(Docker required; plain `pytest` works on Linux/macOS after
`pip install -r requirements_test.txt`):

```bash
scripts/test          # ruff, formatting and pytest against the latest supported Home Assistant
scripts/test --min    # tests against the minimum supported Home Assistant (2026.8)
scripts/test mypy     # any command inside the test container
```

A live environment with Home Assistant and headless JDownloaders is in `live/`;
copy `live/.env.example` to `live/.env` and use a dedicated MyJDownloader test account:

```bash
docker compose -f live/docker-compose.yml up -d
```
