[![Build Status](https://travis-ci.com/doudz/homeassistant-myjdownloader.svg?branch=master)](https://travis-ci.com/doudz/homeassistant-myjdownloader)
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://paypal.me/sebramage)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-green.svg)](https://github.com/custom-components/hacs)

A simple sensor for MyJDownloader state

# Configuration

```
sensor:
  - platform: myjdownloader
    email: myname@email.com
    password: mypassword
    name: JDownloader@doudz
```

`name` is optionnal, if not provided it will generated as many as found JDownloader device
