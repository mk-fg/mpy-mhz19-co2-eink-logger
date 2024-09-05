Micropython MH-Z19x CO2 EInk Logger
===================================

Work-in-progress project to put together a CO2 sensor device with timestamped
log of its measurements on a persistent EInk screen (or ePaper one actually).

Components involved:

- RPi-Pico-like rp2040 board running micropython firmware.
- [Winsen MH-Z19E NDIR CO2 Sensor], or any other MH-Z19 one.
- WaveShare 3-color (black-white-red) [2.13inch e-Paper HAT (B) V4] display.
- Analog Devices (ex Dallas Semiconductor) [DS3231 RTC] with a battery.

[Winsen MH-Z19E NDIR CO2 Sensor]:
  https://www.winsen-sensor.com/sensors/co2-sensor/mh-z19e.html
[2.13inch e-Paper HAT (B) V4]:
  https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_(B)_Manual
[DS3231 RTC]: https://www.analog.com/en/products/ds3231.html

Idea is an autonomous CO2 logger device, which can be enabled when/where needed
for a while to get a temporary log of results, easily visible on its screen even
after picking it up and disconnecting from power.
With measurements timestamped, to indicate/remind when they were taken,
but only persistent on the screen until its reset or next use.

Currently just a bunch of scripts for testing various hw components:

```
### Wiring diagram
wireviz -fp rp2040-wiring.yaml && feh rp2040-wiring.png

### MH-Z19 CO2 sensor
mpremote a1 run mhz19e-test.py

### DS3231 RTC
mpremote a1 run rtc-test.py
# For setting time - should only be needed once
tt=`python -c 'import time; print((time.localtime()[:-1]))'` && \
  sed "s/tt_now = .*/tt_now = $tt/" rtc-test.py > /tmp/rtc-test.py && \
  mpremote a1 run /tmp/rtc-test.py

### WS 2.13B4 ePaper screen
mpremote a1 run screen-test.py
# To generate image and see it on-screen (in "feh" viewer)
mpremote a1 run screen-test.py | tee test.b64
./screen-test-png.py <test.b64 >test.png && feh --zoom 400 test.png
```

Repository URLs:

- <https://github.com/mk-fg/mpy-mhz19-co2-eink-logger>
- <https://codeberg.org/mk-fg/mpy-mhz19-co2-eink-logger>
- <https://fraggod.net/code/git/mpy-mhz19-co2-eink-logger>


Links
-----

- [The Bible of MH-Z19x CO2 sensors] - great rundown of everything related
  to these devices (up to MH-Z19D variant), including all sorts of quirks.

- [WifWaf/MH-Z19 driver for MH-Z19x CO2 sensors] - not used here,
  but has a good amount of technical and protocol information and
  documentation on these devices, which datasheets lack.

[The Bible of MH-Z19x CO2 sensors]: https://emariete.com/en/sensor-co2-mh-z19b/
[WifWaf/MH-Z19 driver for MH-Z19x CO2 sensors]: https://github.com/WifWaf/MH-Z19
