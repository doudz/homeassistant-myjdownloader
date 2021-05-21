![Tests](https://github.com/doudz/homeassistant-myjdownloader/workflows/Tests/badge.svg)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A simple sensor for MyJDownloader state

# Configuration

``` YAML
sensor:
  - platform: myjdownloader
    email: myname@email.com
    password: mypassword
    name: JDownloader@doudz # optional, if not provided all JDownloader devices will be generated.
    scan_interval: 5 # optional - default is 60
```

The name can be found via the MyJDownloader web interface <https://my.jdownloader.org/index.html>

