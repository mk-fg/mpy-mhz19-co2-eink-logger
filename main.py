import machine, time, framebuf, gc, math, re, collections as cs

try: import network # required for wifi stuff
except ImportError: network = None
try: import socket # required for webui
except ImportError: socket = None

try: import uasyncio as asyncio
except ImportError: import asyncio # newer mpy naming


class CO2LogConf:

	wifi_sta_conf = dict(scan_interval=20.0, check_interval=10.0)
	wifi_sta_aps = dict()
	wifi_ap_conf = dict()

	sensor_verbose = False
	sensor_enabled = True
	sensor_uart = 1
	sensor_pin_tx = 20
	sensor_pin_rx = 21
	sensor_init_delay = 210.0
	sensor_interval = 1021.0
	sensor_detection_range = 2_000
	sensor_self_calibration = False
	sensor_ppm_offset = 0
	sensor_ewma_alpha = 0.4
	sensor_ewma_read_delays = ''
	sensor_read_delays = '0.1 0.1 0.1 0.2 0.3 0.5 1.0'
	sensor_read_retry_delays = '0.1 1 5 10 20 40 80 120 180'

	rtc_i2c = 0
	rtc_pin_sda = 16
	rtc_pin_scl = 17

	screen_verbose = False
	screen_spi = 1
	screen_pin_dc = 8
	screen_pin_cs = 9
	screen_pin_reset = 12
	screen_pin_busy = 13
	screen_x0 = 1
	screen_y0 = 3
	screen_y_line = 10
	screen_test_fill = False
	screen_test_export = False
	screen_timeout = 80.0

p_err = lambda *a: print('ERROR:', *a)
err_fmt = lambda err: f'[{err.__class__.__name__}] {err}'


def conf_parse(conf_file):
	with open(conf_file, 'rb') as src:
		sec, conf_lines = None, dict()
		for n, line in enumerate(src, 1):
			if n == 1 and line[:3] == b'\xef\xbb\xbf': line = line[3:]
			try: line = line.decode().strip()
			except UnicodeError:
				p_err(f'[conf] Ignoring line {n} - failed to decode utf-8: {line}')
				continue
			if not line or line[0] in '#;': continue
			if line[0] == '[' and line[-1] == ']':
				sec = conf_lines[line[1:-1].lower()] = list()
			else:
				key, _, val = map(str.strip, line.partition('='))
				if sec is None:
					p_err(f'[conf] Ignoring line {n} key before section header(s) - {repr(key)}')
				else: sec.append((key, key.replace('-', '_').lower(), val))

	conf = CO2LogConf()
	bool_map = {
		'1': True, 'yes': True, 'y': True, 'true': True, 'on': True,
		'0': False, 'no': False, 'n': False, 'false': False, 'off': False }
	wifi_sec_map = {'wpa2-psk': 3, 'wpa/wpa2-psk': 4, 'wpa-psk': 2}
	wifi_conf_keys = dict(
		country=str, verbose=lambda v: bool_map[v],
		scan_interval=float, check_interval=float, ssid=str, key=str,
		hostname=str, channel=int, reconnects=int, txpower=float,
		mac=lambda v: v.encode(), hidden=lambda v: bool_map[v],
		security=lambda v: wifi_sec_map[v.lower() or 'wpa2-psk'],
		pm=lambda v: network and getattr(network.WLAN, f'PM_{v.upper()}') )

	if sec := conf_lines.get('wifi-ap'):
		ap, prefix = dict(), '[conf.wifi-ap]'
		for key_raw, key, val in sec:
			if not (key_func := wifi_conf_keys.get(key)):
				p_err(f'{prefix} Unrecognized config key [ {key_raw} ]')
				continue
			try: ap[key] = key_func(val)
			except Exception as err:
				p_err(f'{prefix} Failed to process {key_raw}=[ {val} ]: {err_fmt(err)}')
		if ap.get('ssid') and ap.get('key'): conf.wifi_ap_conf = ap

	if sec := conf_lines.get('wifi-client'):
		ap_map = {None: conf.wifi_sta_conf}
		ssid, ap, ck = None, dict(), 'conf.wifi-client'
		sec.append(('ssid', 'ssid', None)) # close last ssid= section
		for key_raw, key, val in sec:
			if key == 'country': ap_map[None][key] = val
			elif key == 'verbose': ap_map[None][key] = bool_map[val]
			elif key == 'ssid':
				if ssid and not ap:
					p_err(f'{prefix} Skipping ssid without config [ {ssid} ]')
				else:
					if ssid not in ap_map: ap_map[ssid] = ap_map[None].copy()
					ap_map[ssid].update(ap)
					ap.clear()
				ssid = val
			elif key_func := wifi_conf_keys.get(key):
				try: ap[key] = key_func(val)
				except Exception as err:
					p_err(f'{prefix} Failed to process [ {ssid} ] {key_raw}=[ {val} ]: {err_fmt(err)}')
			else: p_err(f'{prefix} Unrecognized config key [ {key_raw} ]')
		conf.wifi_sta_conf, conf.wifi_sta_aps = ap_map.pop(None), ap_map

	for sk in 'sensor', 'rtc', 'screen':
		if not (sec := conf_lines.get(sk)): continue
		for key_raw, key, val in sec:
			key_conf = f'{sk}_{key}'
			if (val_conf := getattr(conf, key_conf, None)) is None:
				p_err(f'[conf.{sk}] Skipping unrecognized config key [ {key_raw} ]')
			else:
				if isinstance(val_conf, bool): val = bool_map[val.lower()]
				elif isinstance(val_conf, (int, float)): val = type(val_conf)(val)
				elif not isinstance(val_conf, str): raise ValueError(val_conf)
				setattr(conf, key_conf, val)

	return conf

def conf_vals(conf, sec, keys, flat=False):
	if isinstance(keys, str): keys = keys.split()
	vals = tuple(getattr(conf, f'{sec}_{k}') for k in keys)
	return vals if flat else dict(zip(keys, vals))


def wifi_ap_setup(ap):
	p_log = ap.get('verbose') and (lambda *a: print('[wifi]', *a))
	if cc := ap.get('country'): network.country(cc)
	ap_keys = [ 'ssid', 'key', 'hostname', 'security',
		'pm', 'channel', 'reconnects', 'txpower', 'mac', 'hidden' ]
	wifi = network.WLAN(network.AP_IF)
	wifi.config(**dict((k, ap[k]) for k in ap_keys if k in ap))
	wifi.active(True)
	ip, net, gw, dns = wifi.ifconfig()
	print(f'Setup Access Point [ {ap.get("ssid")} ] with IP {ip} (mask {net})')

async def wifi_client(conf_base, ap_map):
	def ssid_str(ssid):
		try: return ssid.decode() # mpy 1.20 doesn't support errors= handling
		except UnicodeError: return repr(ssid)[2:-1] # ascii + backslash-escapes
	p_log = conf_base.get('verbose') and (lambda *a: print('[wifi]', *a))
	if cc := conf_base.get('country'): network.country(cc)
	wifi = network.WLAN(network.STA_IF)
	wifi.active(True)
	p_log and p_log('Activated')
	ap_conn = ap_reconn = addr_last = None
	ap_keys = [ 'ssid', 'key', 'hostname', 'pm',
		'channel', 'reconnects', 'txpower', 'mac', 'hidden' ]
	while True:
		if not (st := wifi.isconnected()):
			p_log and p_log(
				f'Not-connected (reconnect={(ap_reconn or dict()).get("ssid", "no")})' )
			ap_conn = None
			if ap_reconn: # reset same-ssid conn once on hiccups
				ap_conn, ap_reconn = ap_reconn, None
			if not ap_conn:
				ssid_map = dict((ssid_str(ap[0]), ap[0]) for ap in wifi.scan())
				p_log and p_log(f'Scan results [ {" // ".join(sorted(ssid_map))} ]')
				for ssid, ap in ap_map.items():
					if ssid_raw := ssid_map.get(ssid):
						ap_conn = dict(conf_base, ssid=ssid_raw, **ap)
						break
			if ap_conn:
				p_log and p_log(f'Connecting to [ {ssid_str(ap_conn["ssid"])} ]')
				wifi.config(**dict((k, ap_conn[k]) for k in ap_keys if k in ap_conn))
				wifi.connect( ssid=ap_conn['ssid'],
					key=ap_conn['key'] or None, bssid=ap_conn.get('mac') or None )
		elif ap_conn: ap_conn, ap_reconn = None, ap_conn
		if ap_conn: st, delay = 'connecting', ap_conn['scan_interval']
		elif ap_reconn or st: # can also be connection from earlier script-run
			st, delay = 'connected', (ap_reconn or conf_base)['check_interval']
		else: st, delay = 'searching', conf_base['scan_interval']
		if addrs := wifi.ifconfig():
			if p_log: st += f' [{addrs[0]}]'
			elif addr_last != addrs[0]:
				print('[wifi] Current IP Address:', addr_last := addrs[0])
		p_log and p_log(f'State = {st}, delay = {delay:.1f}s')
		await asyncio.sleep(delay)
	raise RuntimeError('BUG - wifi loop stopped unexpectedly')


class ReadingsQueue:
	def __init__(self):
		# asyncio.Event seem to be crashing mpy, hence ThreadSafeFlag
		self.data, self.ev = cs.deque((), 50), asyncio.ThreadSafeFlag()
	def put(self, value): self.data.append(value); self.ev.set()
	async def get(self):
		while True:
			await self.ev.wait()
			try: value = self.data.popleft()
			except IndexError: self.ev.clear(); continue
			if not self.data: self.ev.clear()
			else: self.ev.set() # for ThreadSafeFlag
			return value
	def is_empty(self): return not self.data


class RTC_DS3231:
	def __init__(self, i2c): self.i2c = i2c

	def _decode(self, bs):
		# (v - 6 * (v>>4)) == (10 * (v>>4) + (v & 0xf)), same for reverse op
		ss, mm, hh, wd, dd, mo, yy = bytes( (v - 6 * (v>>4))
			for v in (b & m for m, b in zip(b'\x7f\x7f\x3f\x07\x3f\x1f\xff', bs)) )
		if bs[2] & 0x40: hh += 12 * bool(bs[2] & 0x20)
		yd = int((275 * mo) / 9.0) - (1 + (yy % 4)) * int((mo + 9) / 12.0) + dd - 30
		return yy+2000, mo, dd, hh, mm, ss, wd, yd

	def set(self, tt): # set RTC from localtime timetuple
		yy, mo, dd, hh, mm, ss, wd, yd = tt
		bs = bytearray([ss, mm, hh, wd, dd, mo, yy - 2000])
		for n, v in enumerate(bs): bs[n] = v + 6 * (v//10)
		if (tt_enc := self._decode(bs)) != tt:
			p = lambda tt: '[ '+' '.join(f'{k}={v}' for k, v in zip('YMDhmswy', tt))+' ]'
			raise ValueError(f'Failed to encode time-tuple:\n    {p(tt)}\n to {p(tt_enc)}')
		self.i2c.writeto_mem(0x68, 0x00, bs)

	async def read(self): # uses hardcoded read-retry attempts
		for td in 0.05, 0.1, 0.1, 0.2, 0.3, None:
			try: bs = self.i2c.readfrom_mem(0x68, 0x00, 7)
			except:
				if td: await asyncio.sleep(td)
				else: raise
			else: return time.mktime(self._decode(bs))


class MHZ19:

	def __init__(self, uart): self.uart = uart

	def _res_bytes(self, cmd, bs):
		if not bs: return
		if csum := sum(bs[1:-1]) % 0x100: csum = 0xff - csum + 1
		if ( bs and len(bs) == 9 and bs[0] == 0xff
				and bs[1] == cmd and csum == bs[-1] ):
			return bs[2:-1] # 6B of actual payload

	async def read_ppm(self, read_delays=[0.1, 0.1, 0.2, 0.2, 0.5]):
		bs = self.uart.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
		for td in read_delays:
			await asyncio.sleep(td)
			if bs := self._res_bytes(0x86, self.uart.read(9)): return bs[0]*256 + bs[1]

	async def set_abc(self, state): # Automatic Baseline Correction
		if state: self.uart.write(b'\xff\x01\x79\xa0\x00\x00\x00\x00\xe6')
		else: self.uart.write(b'\xff\x01\x79\x00\x00\x00\x00\x00\x86')

	async def set_range(self, ppm):
		if ppm not in [2_000, 5_000, 10_000]: raise ValueError(ppm)
		bs = bytearray(b'\xff\x01\x99\x00\x00\x00\x00\x00\x00')
		bs[6], bs[7] = ppm // 256, ppm % 256
		if csum := sum(bs[1:-1]) % 0x100: bs[-1] = 0xff - csum + 1
		self.uart.write(bs)


async def sensor_read(rtc, mhz19, read_delays, retry_delays, ewma_a, ewma_tds):
	ewma, retries = None, 0
	for td in ewma_tds:
		if td: await asyncio.sleep(td)
		for n, td_retry in enumerate(retry_delays):
			if ppm := await mhz19.read_ppm(read_delays):
				ewma = ppm if ewma is None else (ppm * ewma_a + (1-ewma_a)*ewma)
				retries += n; break
			if td_retry: await asyncio.sleep(td_retry)
		else: raise RuntimeError(
			f'CO2 sensor read failed after {len(retry_delays)} attempt(s)' )
	ts_rtc = await rtc.read()
	return retries, ts_rtc, round(ewma)

async def sensor_poller( conf, mhz19, rtc,
		readings, init_delay=0, abc_repeat=12*3593*1000, verbose=False ):
	p_log = verbose and (lambda *a: print('[sensor]', *a))
	read_delays = list(map(float, conf.sensor_read_delays.split()))
	read_retry_delays = list(map(float, conf.sensor_read_retry_delays.split())) + [None]
	ewma_read_delays = [0] + list(map(float, conf.sensor_ewma_read_delays.split()))
	ewma_td_ms = round(1000 * sum(ewma_read_delays))
	ewma_info = p_log and ( ( f'samples={len(ewma_read_delays)}' +
		f' timespan={ewma_td_ms/1000:,.1f}s' ) if ewma_td_ms else 'single-read' )
	mhz19_read = lambda: sensor_read( rtc, mhz19,
		read_delays, read_retry_delays, conf.sensor_ewma_alpha, ewma_read_delays )

	p_log and p_log('Init: configuration')
	td_cycle = int(conf.sensor_interval * 1000)
	await asyncio.sleep(0.2)
	mhz19.set_abc(ts_abc_off := conf.sensor_self_calibration)
	if not ts_abc_off: ts_abc = time.ticks_ms()
	await asyncio.sleep(0.2)
	mhz19.set_range(conf.sensor_detection_range)
	if (delay := conf.sensor_init_delay - time.ticks_ms() / 1000) > 0:
		p_log and p_log(f'Init: preheat delay [{delay:,.1f}s]')
		await asyncio.sleep(delay)
	else: p_log and p_log('Init: skipping preheat delay due to uptime')

	p_log and p_log(f'Starting poller loop ({td_cycle/1000:,.1f}s interval)...')
	while True:
		ts = time.ticks_ms()
		if not ts_abc_off and time.ticks_diff(ts, ts_abc) > abc_repeat:
			# Arduino MH-Z19 code repeats this every 12h to "skip next ABC cycle"
			# Not sure if it actually needs to be repeated, but why not
			mhz19.set_abc(ts_abc_off); ts_abc = ts
		p_log and p_log(f'datapoint read [{ewma_info}]')
		n, ts_rtc, ppm = await mhz19_read()
		p_log and p_log(f'datapoint [retries={n}]: ts={ts_rtc} ppm={ppm:,d}')
		readings.put((ts_rtc, ppm + conf.sensor_ppm_offset))
		delay = max(0, td_cycle - ewma_td_ms - time.ticks_diff(time.ticks_ms(), ts))
		p_log and p_log(f'delay: {delay/1000:,.1f} ms')
		await asyncio.sleep_ms(delay)


class EPD_2in13_B_V4_Portrait:

	class Pins:
		def __init__(self, pins):
			if err := {'reset', 'busy', 'cs', 'dc'}.symmetric_difference(pins):
				raise ValueError(f'Pin specs mismatch: {" ".join(err)}')
			for k, v in pins.items(): setattr(self, k, v)

	class EPDInterface: # hides all implementation internals
		def __init__(self, epd):
			for k in 'black red display clear w h'.split():
				setattr(self, k, getattr(epd, k))

	def __init__(self, w=122, h=250, timeout=120, verbose=False):
		self.p_log = verbose and (lambda *a: print('[epd]', *a))
		self.h, self.w, self.active, self.timeout = h, math.ceil(w/8)*8, None, timeout
		for c in 'black', 'red':
			setattr(self, f'{c}_buff', buff := bytearray(math.ceil(self.w * self.h / 8)))
			setattr(self, c, framebuf.FrameBuffer(buff, self.w, self.h, framebuf.MONO_HLSB))

	async def hw_init(self, spi=None, **pins):
		if spi and pins: # first init
			p_log, Pin = self.p_log, machine.Pin
			p_log and p_log('Init: spi/pins')
			pins = self.p = self.Pins(pins)
			for k in 'reset', 'cs', 'dc':
				setattr(pins, k, Pin(getattr(pins, k), Pin.OUT))
			pins.busy = Pin(pins.busy, Pin.IN, Pin.PULL_UP)
			self.spi = spi
			spi.init(baudrate=4000_000)
			if time.ticks_ms() < 20: await asyncio.sleep_ms(20)
			epd_iface = self.EPDInterface(self)
		else:
			spi, pins = self.spi, self.p
			p_log = epd_iface = None
		if self.active: return # no need for init

		async def wait_ready(_p_busy=pins.busy):
			while _p_busy.value(): await asyncio.sleep_ms(10)
			await asyncio.sleep_ms(20)
		def cmd(b, _p_dc=pins.dc, _p_cs=pins.cs, _spi=spi):
			_p_dc.value(0); _p_cs.value(0)
			_spi.write(bytes([b])); _p_cs.value(1)
		def data(bs, _p_dc=pins.dc, _p_cs=pins.cs, _spi=spi):
			if isinstance(bs, int): bs = bytes([bs])
			elif isinstance(bs, list): bs = bytes(b&0xff for b in bs)
			_p_dc.value(1); _p_cs.value(0)
			_spi.write(bs); _p_cs.value(1)
		self.wait_ready, self.cmd, self.data = wait_ready, cmd, data

		p_log and p_log('Init: reset')
		pins.reset.value(1); await asyncio.sleep_ms(50)
		pins.reset.value(0); await asyncio.sleep_ms(2)
		pins.reset.value(1); await asyncio.sleep_ms(50)
		await wait_ready()
		cmd(0x12) # swreset
		await wait_ready()

		p_log and p_log('Init: configuration')
		# Output control
		cmd(0x01); data(b'\xf9\0\0')
		# Data entry mode
		cmd(0x11); data(0x03) # landscape mode uses 0x07
		# Window configuration
		cmd(0x44) # set_ram_x_address_start_end_position
		data([(x0 := 0)>>3, (x1 := self.w-1)>>3])
		cmd(0x45) # set_ram_y_address_start_end_position
		data([y0 := 0, y0>>8, y1 := self.h-1, y1>>8])
		# Cusor position - not sure if x0/y0 are window or abs coordinates
		cmd(0x4e); data(x0 & 0xff) # set_ram_x_address_counter
		cmd(0x4f); data([y0, y0 >> 8]) # set_ram_y_address_counter
		# BorderWaveform
		cmd(0x3c); data(0x05)
		# Read built-in temperature sensor
		cmd(0x18); data(0x80)
		# Display update control
		cmd(0x21); data(b'\x80\x80')
		await wait_ready()

		p_log and p_log('Init: finished')
		self.active = True
		return epd_iface

	def close(self):
		self.cmd = self.data = self.wait_ready = self.active = None
		self.p_log and self.p_log('Closed')

	async def display(self, op='Display', final=False):
		self.p_log and self.p_log(op)
		await self.hw_init()
		self.cmd(0x24)
		self.data(self.black_buff)
		self.cmd(0x26)
		self.data(self.red_buff)
		self.cmd(0x20) # activate display update sequence
		try: await asyncio.wait_for(self.wait_ready(), self.timeout)
		except asyncio.TimeoutError:
			if final: raise
			self.close() # force reset
			await self.display(op=f'{op} [retry]', final=True)
		await self.sleep_mode()

	async def sleep_mode(self):
		self.p_log and self.p_log('Sleep mode')
		self.cmd(0x10)
		self.data(0x01)
		await asyncio.sleep(2) # not sure why, was in example code
		self.p.reset.value(0)
		self.active = False

	async def clear(self, color=1):
		self.black.fill(color)
		self.red.fill(color)
		await self.display('Clear')

	def export_image_buffers(self, line_bytes=90):
		import sys, binascii
		if flush := getattr(sys.stdout, 'flush', None): flush() # not used in mpy atm
		for bt, buff in zip(['BK', 'RD'], [self.black_buff, self.red_buff]):
			sys.stdout.buffer.write(f'\n-epd-:{bt} {self.w} {self.h} {len(buff)}\n'.encode())
			for n in range(0, len(buff), line_bytes):
				sys.stdout.buffer.write(b'-epd-:')
				sys.stdout.buffer.write(binascii.b2a_base64(buff[n:n+line_bytes]))
		sys.stdout.buffer.write(b'\n')
		if flush := getattr(sys.stdout.buffer, 'flush', None): flush()


def co2_log_fake_gen(ts_rtc=None, td=673):
	import random
	values, ts_rtc = list(), ts_rtc or 1725673478
	for n in range(30):
		if random.random() > 0.6: ppm = random.randint(400, 900)
		elif random.random() > 0.4: ppm = random.randint(500, 3000)
		else: ppm = random.randint(500, 8000)
		values.append((int(ts_rtc), ppm))
		ts_rtc -= td
	return reversed(values)

def co2_log_text(tt, co2):
	ts_rtc = f'{tt[3]:02d}:{tt[4]:02d}'
	# XXX: configurable comments for levels
	if co2 < 800: warn = ''
	elif co2 < 1500: warn = ' hi'
	elif co2 < 2500: warn = ' BAD'
	elif co2 < 5000: warn = ' WARN'
	else: warn = ' !!!!'
	return f'{ts_rtc} {co2: >04d}{warn}'

async def co2_log_scroller(epd, readings, x0=1, y0=3, y_line=10, export=False):
	# x: 0 <x0> text <epd.w-1>
	# y: 0 <y0> header hline <yh> lines[0] ... <yt> lines[lines_n-1] <epd.h-1>
	# XXX: maybe put dotted vlines to separate times and warnings
	buffs = epd.black, epd.red
	if not export: await epd.clear()
	else:
		for buff in buffs: buff.fill(1)
	ys = y_line; yh = y0 + ys + 3
	lines_n = (epd.h - yh) // ys; yt = yh + ys * (lines_n - 1)
	lines, line_t = list(), cs.namedtuple('Line', 'red tt co2 text')
	while True:
		# Wait for new reading
		ts_rtc, co2 = await readings.get()
		tt, red = time.localtime(ts_rtc), bool(lines) and lines[-1].red
		lines.append(line := line_t(not red, tt, co2, co2_log_text(tt, co2)))
		# Scroll lines up in both buffers, scrub top/bottom
		if len(lines) > lines_n:
			lines[:] = lines[1:]
			for buff in buffs:
				buff.scroll(0, -ys)
				buff.fill_rect(0, 0, epd.w, yh, 1)
				buff.fill_rect(0, yt, epd.w, yt + ys, 1)
		# Replace header line
		yy, mo, dd = lines[0].tt[:3]
		buff = buffs[not lines[0].red]
		buff.text(f'{yy%100:02d}-{mo:02d}-{dd:02d} CO2ppm', x0, y0, 0)
		epd.black.hline(0, y0 + ys, epd.w, 0)
		# Add new line at the end
		buffs[line.red].text(line.text, x0, yh + ys * (len(lines) - 1), 0)
		# Display/dump buffers
		if not export:
			if readings.is_empty(): await epd.display() # batch updates otherwise
		else: epd.export_image_buffers()


async def main_co2log(conf, wifi):
	httpd = webui = None
	components, webui_opts = list(), dict()
	if wifi: components.append(wifi)

	mhz19 = rtc = epd = None

	readings = ReadingsQueue()
	if conf.sensor_enabled:
		uart_id, rx, tx = conf_vals(conf, 'sensor', 'uart pin_rx pin_tx', flat=True)
		mhz19 = MHZ19(machine.UART(
			uart_id, rx=machine.Pin(rx), tx=machine.Pin(tx),
			baudrate=9600, bits=8, stop=1, parity=None ))
		i2c_id, sda, scl = conf_vals(conf, 'rtc', 'i2c pin_sda pin_scl', flat=True)
		rtc = RTC_DS3231(machine.I2C(i2c_id, sda=machine.Pin(sda), scl=machine.Pin(scl)))
		components.append(sensor_poller(
			conf, mhz19, rtc, readings, verbose=conf.sensor_verbose ))
	if conf.screen_test_fill:
		ts_rtc = rtc and await rtc.read()
		co2_gen = co2_log_fake_gen(ts_rtc=ts_rtc, td=conf.sensor_interval)
		for ts_rtc, ppm in co2_gen: readings.put((ts_rtc, ppm))

	epd = EPD_2in13_B_V4_Portrait(
		timeout=conf.screen_timeout, verbose=conf.screen_verbose )
	if not (epd_export := conf.screen_test_export):
		epd = await epd.hw_init( machine.SPI(conf.screen_spi),
			**conf_vals(conf, 'screen_pin', 'dc cs reset busy') )
	components.append(co2_log_scroller( epd, readings,
		export=epd_export, **conf_vals(conf, 'screen', 'x0 y0 y_line') ))

	print('--- CO2Log start ---')
	try:
		if webui: # XXX: not implemented
			httpd = await asyncio.start_server( webui.request,
				'0.0.0.0', conf.webui_port, backlog=conf.webui_conn_backlog )
			components.append(httpd.wait_closed())
		await asyncio.gather(*components)
	finally:
		if httpd: httpd.close(); await httpd.wait_closed() # to reuse socket for err-msg
		print('--- CO2Log stop ---')

async def main_fail_webui_req(fail, fail_ts, sin, sout, _html=(
		b'<!DOCTYPE html>\n<head><meta charset=utf-8>\n'
		b'<style>\nbody { margin: 0 auto; padding: 1em;\n'
		b' max-width: 960px; color: #d2f3ff; background: #09373b; }\n'
		b'a, a:visited { color: #5dcef5; } p { font-weight: bold; }\n</style>\n'
		b'<body><h2>Fatal Error - Unexpected component failure</h2>\n<pre>' )):
	try:
		fid, td = (str(v).encode() for v in [fail_ts, time.ticks_diff(time.ticks_ms(), fail_ts)])
		try:
			verb, url, proto = (await sin.readline()).split(None, 2)
			if url.lower().endswith(b'/reset.' + fid): return machine.reset()
		except ValueError: pass
		while (await sin.readline()).strip(): pass # flush request
		sout.write( b'HTTP/1.0 500 Server Error\r\nServer: co2log\r\n'
			b'Cache-Control: no-cache\r\nContent-Type: text/html\r\n' )
		tail = b'''</pre>\n<div id=tail><script>
			let tz = Intl.DateTimeFormat().resolvedOptions().timeZone,
				dt = new Intl.DateTimeFormat('sv-SE', {
					timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
					hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
				.format(new Date(Date.now() - %td))
			document.getElementById('tail').innerHTML =
				`<p>Error date/time: ${dt} [${tz}]</p><a href=reset.%fid>Reset Device</a>`
			</script>'''.replace(b'\t', b' ').replace(b'%fid', fid).replace(b'%td', td)
		sout.write(f'Content-Length: {len(_html) + len(fail) + len(tail)}\r\n\r\n')
		sout.write(_html); sout.write(fail); sout.write(tail)
		await sout.drain()
	finally:
		sin.close(); sout.close()
		await asyncio.gather(sin.wait_closed(), sout.wait_closed())

async def main():
	print('--- CO2Log init ---')
	conf = conf_parse('config.ini')
	wifi = httpd = None

	if httpd := conf.wifi_ap_conf or conf.wifi_sta_aps:
		if not getattr(network, 'WLAN', None):
			httpd = p_err('No net/wifi support detected in mpy fw, not using wifi config')
		elif conf.wifi_ap_conf: wifi_ap_setup(conf.wifi_ap_conf)
		else: wifi = asyncio.create_task(wifi_client(conf.wifi_sta_conf, conf.wifi_sta_aps))

	fail = None
	try: return await main_co2log(conf, wifi)
	except Exception as err: fail = err
	fail_ts = time.ticks_ms()

	gc.collect() # in case it was a mem shortage
	gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

	import sys, io
	p_err('One of the main components failed, traceback follows...')
	sys.print_exception(fail)
	if not (socket and httpd): return # no way to display fail-webui - just exit

	err = io.BytesIO()
	sys.print_exception(fail, err)
	err, fail = None, err.getvalue()
	fail = fail.replace(b'&', b'&amp;').replace(b'<', b'&lt;').replace(b'>', b'&gt;')

	if wifi and wifi.done():
		p_err('[wifi] Connection monitoring task failed, restarting it')
		wifi = wifi_client(conf.wifi_sta_conf, conf.wifi_sta_aps)
	p_err('Starting emergency-WebUI with a traceback page')
	httpd = await asyncio.start_server(
		lambda sin, sout: main_fail_webui_req(fail, fail_ts, sin, sout),
		'0.0.0.0', conf.webui_port, backlog=conf.webui_conn_backlog )
	await asyncio.gather(httpd.wait_closed(), *([wifi] if wifi else []))
	raise RuntimeError('BUG - fail-webui stopped unexpectedly')

def run(): asyncio.run(main())
if __name__ == '__main__': run()
