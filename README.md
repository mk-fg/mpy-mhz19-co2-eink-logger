Micropython MH-Z19x CO2 EInk Logger
===================================

Code for running an autonomous CO2 meter device, showing timestamped log
of its measurements on a persistent EInk screen (or ePaper one actually).

Components involved:

- RPi-Pico-like rp2040 board running [micropython firmware].
- [Winsen MH-Z19E NDIR CO2 Sensor], or any other MH-Z19 one.
- WaveShare 3-color (black-white-red) [2.13inch e-Paper HAT (B) V4] display.
- Analog Devices (ex Dallas Semiconductor) [DS3231 RTC] with a battery.
- 5V ± 0.1V power supply - [needs to be this stable for MH-Z19C+ sensors].

This particular small display/layout fits ~25 lines of readings
(some 6-8h at default 20min intervals).
EInk display keeps the info even when powered-off, but it does not get
stored anywhere else, so will be lost when it's cleared (e.g. on next use).

Intended use is to plug or drop the thing with a powerbank in a place
temporarily, to pick it up and check how CO2 levels vary there over time later.

[micropython firmware]: https://micropython.org/
[Winsen MH-Z19E NDIR CO2 Sensor]:
  https://www.winsen-sensor.com/sensors/co2-sensor/mh-z19e.html
[2.13inch e-Paper HAT (B) V4]:
  https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_(B)_Manual
[DS3231 RTC]: https://www.analog.com/en/products/ds3231.html
[needs to be this stable for MH-Z19C+ sensors]:
  https://emariete.com/en/sensor-co2-mh-z19b/#Variacion_con_el_voltaje_de_alimentacion

Table of Contents for this README:

- [How to use](#hdr-how_to_use)
- [Helper scripts](#hdr-helper_scripts_and_debugging)
- [Links](#hdr-links)
- [TODO](#hdr-todo)

Repository URLs:

- <https://github.com/mk-fg/mpy-mhz19-co2-eink-logger>
- <https://codeberg.org/mk-fg/mpy-mhz19-co2-eink-logger>
- <https://fraggod.net/code/git/mpy-mhz19-co2-eink-logger>


<a name=hdr-how_to_use></a>
## How to use

It's just one self-contained [main.py] micropython script, using an
[ini configuration file] with a list of pins and tunable parameters.

One possible wiring diagram for e.g. [RPi Pico (rp2040) board],
and pins/interfaces from [config.example.ini] file:

![WireViz rp2040 wiring diagram][]

(generated by `wireviz -fs rp2040-wiring.yaml`
from [rp2040-wiring.yaml] file using [WireViz tool])

Screen used in this script is a hat/cape specific to RPi Pico pin layout, so
realistically it'll probably only work as-is with pico and compatible knock-offs.

[main.py]: main.py
[ini configuration file]: config.example.ini
[RPi Pico (rp2040) board]: https://pico.pinout.xyz/
[config.example.ini]: config.example.ini
[rp2040-wiring.yaml]: rp2040-wiring.yaml
[WireViz rp2040 wiring diagram]:
  https://mk-fg.github.io/mpy-mhz19-co2-eink-logger/rp2040-wiring.svg
[WireViz tool]: https://github.com/wireviz/WireViz/

Main script can be configured, uploaded and run like this:

``` console
## Upload micropython firmware to the device, install "mpremote" tool

% cp config.example.ini config.ini
## Edit that config.ini file, to setup local device/network parameters

% mpremote cp config.ini :
% mpremote run main.py
## Should either work to print some errors to console

## To setup this to run on board boot
% mpremote cp main.py :
% mpremote reset
```

Running it should clear the screen on start, then wait for sensor `init-delay`
(aka "preheat time", 3-4 minutes by default), then get and add every new sensor
readings with configured `interval` value (15-20 min).

Default configuration disables sensor self-calibration (also known as Automatic
Baseline Correction mode), so make sure to either calibrate it manually using
"HD" pin, or enable it using `self-calibration = yes` option, if measured space
is expected to be ventilated daily.
See [Bible of MH-Z19x CO2 sensors] for a lot more details on all this.

[Bible of MH-Z19x CO2 sensors]: https://emariete.com/en/sensor-co2-mh-z19b/


<a name=hdr-helper_scripts_and_debugging></a>
## Helper scripts and debugging

Every component can have `verbose = yes` option in the config file to enable
verbose logging to USB/UART console - wherever micropython dumps output by default.
[mpremote] or any other serial console tool can be used to see these logs as
script produces them.

Repository also has couple scripts for testing and configuring individual components.

[mpremote]: https://docs.micropython.org/en/latest/reference/mpremote.html

**[edp-png.py]**

Regular-python script to use with `test-export = yes` screen-config option,
to convert and see bitmaps output to console (instead of display) as PNG files.
Related `test-fill = yes` option can be used to also generate fake data to
test various text layout and graphical tweaks.

For example, to run the script, dump images to `test.b64` file, then parse it
and see a last display state as PNG image (using common [feh] image viewer):

```
mpremote run main.py | tee test.b64
./edp-png.py -i test.b64 -o test.png && feh --zoom 400 test.png
```

Requires [python "pillow" module] (aka PIL) to make PNG.

[edp-png.py]: edp-png.py
[feh]: https://wiki.archlinux.org/title/Feh
[python "pillow" module]: https://pypi.org/project/pillow/

**[rtc-set.py]**

Script to set correct time on Real-Time Clock module, using mpremote from console:

```
tt=`python -c 'import time; print((time.localtime()[:-1]))'` && \
  sed "s/tt_now =.*/tt_now = $tt/" rtc-set.py > rtc-set.py.tmp && \
  mpremote a1 run rtc-set.py.tmp
```

These three chained commands get the current localtime tuple for the script, use
`sed` to put that onto `tt_now = ...` line in it, then run the script to set time.

It parses same `config.ini` file for `[rtc]` section i2c/pin info on device, if any.
Will read and print RTC time back after updating it.

Local time is used for RTC (as opposed to more conventional UTC) to avoid needing
to configure timezones and their DST quirks, so in timezones with DST, such time
adjustment has to be run every six months (or TZ offsets handling added to main.py).

[rtc-set.py]: rtc-set.py


<a name=hdr-links></a>
## Links

- [The Bible of MH-Z19x CO2 sensors] - great rundown of everything related
  to these devices (up to MH-Z19D variant), including all sorts of quirks.

- [WifWaf/MH-Z19 driver for MH-Z19x CO2 sensors] - not used here,
  but has a good amount of technical and protocol information and
  documentation on these devices, which datasheets lack.

- [Waveshare ePaper Display "Precautions" section] - for recommendations on
  minimum refresh interval, how long-term storage, etc - to avoid damaging it.

- [ESPHome] - more comprehensive home automation system, which also supports
  this family of sensors (among many others) connected to microcontrollers,
  for a more complex setup to see/control everything in a centralized manner.

- [rp2040-sen5x-air-quality-webui-monitor] - similar project to monitor
  particulate matter (PM) air pollution via autonomous device.

[The Bible of MH-Z19x CO2 sensors]: https://emariete.com/en/sensor-co2-mh-z19b/
[WifWaf/MH-Z19 driver for MH-Z19x CO2 sensors]: https://github.com/WifWaf/MH-Z19
[Waveshare ePaper Display "Precautions" section]:
  https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_(B)_Manual#Precautions
[ESPHome]: https://esphome.io/components/sensor/mhz19.html
[rp2040-sen5x-air-quality-webui-monitor]:
  https://github.com/mk-fg/rp2040-sen5x-air-quality-webui-monitor


<a name=hdr-todo></a>
## TODO

- Finish leftover XXX not-implemented things in the code.

- Add on-screen error output, if there are any.
