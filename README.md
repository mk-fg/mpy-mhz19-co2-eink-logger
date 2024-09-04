Micropython MH-Z19x CO2 eInk Logger
===================================

Work-in-progress project to put together a CO2 sensor device with timestamped
log of its measurements on a persistent eInk screen (or ePaper one actually).

Components involved:

- RPi-Pico-like rp2040 board running micropython firmware.
- [Winsen MH-Z19E NDIR CO2 Sensor], or any other MH-Z19 one.
- WaveShare 3-color (black-white-red) [2.13inch e-Paper HAT (B)] display.
- Analog Devices (ex Dallas Semiconductor) [DS3231 RTC] with a battery.

[Winsen MH-Z19E NDIR CO2 Sensor]:
  https://www.winsen-sensor.com/sensors/co2-sensor/mh-z19e.html
[2.13inch e-Paper HAT (B)]:
  https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_(B)_Manual
[DS3231 RTC]: https://www.analog.com/en/products/ds3231.html

Idea is an autonomous CO2 logger device, which can be enabled when/where needed
for a while to get a temporary log of results, easily visible on its screen even
after picking it up and disconnecting from power.
With measurements timestamped, to indicate/remind when they were taken,
but only persistent on the screen until its reset or next use.

Currently just a bunch of scripts for testing various hw components:

```
mpremote a1 run mhz19e-test.py
mpremote a1 run rtc-test.py

mpremote a1 run paper-test.py | tee test.b64
./paper-image-conv.py <test.b64 >test.png && feh --zoom 400 test.png
```

Repository URLs:

- <https://github.com/mk-fg/mpy-mhz19-co2-eink-logger>
- <https://codeberg.org/mk-fg/mpy-mhz19-co2-eink-logger>
- <https://fraggod.net/code/git/mpy-mhz19-co2-eink-logger>
