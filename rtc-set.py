import machine, time

def rtc_conf_parse(conf_file):
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
	return conf_lines

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

	def read(self):
		bs = self.i2c.readfrom_mem(0x68, 0x00, 7)
		return time.mktime(self._decode(bs))

if __name__ == '__main__':
	tt_now = (2024, 9, 7, 19, 2, 6, 5, 251)

	conf = dict(i2c=0, pin_sda=16, pin_scl=17)
	try: conf_lines = rtc_conf_parse('config.ini')
	except OSError: pass
	else:
		for key_raw, key, val in conf_lines.get('rtc') or list():
			if key in conf: conf[key] = int(val)

	rtc = RTC_DS3231(machine.I2C( conf['i2c'],
		sda=machine.Pin(conf['pin_sda']), scl=machine.Pin(conf['pin_scl']) ))
	rtc.set(tt_now)

	ts = rtc.read()
	yy, mo, dd, hh, mm, ss, wd, yd = time.localtime(ts)
	print( f'{yy:04d}-{mo:02d}-{dd:02d}' +
		f' {hh:02d}:{mm:02d}:{ss:02d} [wd={wd} yd={yd}]' )
