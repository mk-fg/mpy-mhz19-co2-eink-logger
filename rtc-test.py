import machine, time


class RTC_DS3231:
	def __init__(self, i2c): self.i2c = i2c

	def _time_dec(self, bs):
		# (v - 6 * (v>>4)) == (10 * (v>>4) + (v & 0xf)), same for reverse op
		ss, mm, hh, wd, dd, mo, yy = bytes( (v - 6 * (v>>4))
			for v in (b & m for m, b in zip(b'\x7f\x7f\x3f\x07\x3f\x1f\xff', bs)) )
		if bs[2] & 40: hh += 12 * bool(bs[2] & 20)
		yd = int((275 * mo) / 9.0) - (1 + (yy % 4)) * int((mo + 9) / 12.0) + dd - 30
		return yy+2000, mo, dd, hh, mm, ss, wd, yd

	def time_set(self, tt):
		yy, mo, dd, hh, mm, ss, wd, yd = tt
		bs = bytearray([ss, mm, hh, wd, dd, mo, yy - 2000])
		for n, v in enumerate(bs): bs[n] = v + 6 * (v//10)
		if (tt_enc := self._time_dec(bs)) != tt:
			p = lambda tt: '[ '+' '.join(f'{k}={v}' for k, v in zip('YMDhmswy', tt))+' ]'
			raise ValueError(f'Failed to encode time-tuple:\n    {p(tt)}\n to {p(tt_enc)}')
		self.i2c.writeto_mem(0x68, 0x00, bs)

	def time_read(self):
		bs = self.i2c.readfrom_mem(0x68, 0x00, 7)
		return time.mktime(self._time_dec(bs))


if __name__ == '__main__':
	rtc = RTC_DS3231(machine.I2C(0, scl=machine.Pin(17), sda=machine.Pin(16)))

	# tt_now = (2024, 9, 3, 23, 59, 58, 1, 247)
	# rtc.time_set(tt_now)

	ts = rtc.time_read()
	yy, mo, dd, hh, mm, ss, wd, yd = time.localtime(ts)
	print( f'{yy:04d}-{mo:02d}-{dd:02d}' +
		f' {hh:02d}:{mm:02d}:{ss:02d} [wd={wd} yd={yd}]' )
