import machine, framebuf, time, math


class EPD_2in13_B_V4_Portrait:

	class Pins:
		def __init__(self, pins):
			if err := {'reset', 'busy', 'cs', 'dc'}.symmetric_difference(pins):
				raise ValueError(f'Pin specs mismatch: {" ".join(err)}')
			for k, v in pins.items(): setattr(self, k, v)

	class EPDInterface: # to hide all implementation internals
		def __init__(self, epd):
			for k in 'black red display clear sleep'.split():
				setattr(self, k, getattr(epd, k))

	def __init__(self, spi_id=None, w=122, h=250, verbose=False, **pins):
		self.p, self.log = pins, verbose and (lambda *a: print('[epd]', *a))
		self.spi, self.h, self.w = spi_id, h, math.ceil(w/8)*8

		for c in 'black', 'red':
			setattr(self, f'{c}_buff', buff := bytearray(math.ceil(self.w * self.h / 8)))
			setattr(self, c, framebuf.FrameBuffer(buff, self.w, self.h, framebuf.MONO_HLSB))

	def __enter__(self):
		log, Pin = self.log, machine.Pin

		log and log('Init: spi/pins')
		pins = self.p = self.Pins(self.p)
		for k in 'reset', 'cs', 'dc':
			setattr(pins, k, Pin(getattr(pins, k), Pin.OUT))
		pins.busy = Pin(pins.busy, Pin.IN, Pin.PULL_UP)
		self.spi = machine.SPI(self.spi)
		self.spi.init(baudrate=4000_000)

		def wait_ready(_p_busy=pins.busy):
			while _p_busy.value(): time.sleep_ms(10)
			time.sleep_ms(20)
		def cmd(b, _p_dc=pins.dc, _p_cs=pins.cs):
			_p_dc.value(0)
			_p_cs.value(0)
			self.spi.write(bytes([b]))
			_p_cs.value(1)
		def data(bs, _p_dc=pins.dc, _p_cs=pins.cs):
			if isinstance(bs, int): bs = bytes([bs])
			_p_dc.value(1)
			_p_cs.value(0)
			self.spi.write(bs)
			_p_cs.value(1)
		self.wait_ready, self.cmd, self.data = wait_ready, cmd, data

		log and log('Init: reset')
		pins.reset.value(1)
		time.sleep_ms(50)
		pins.reset.value(0)
		time.sleep_ms(2)
		pins.reset.value(1)
		time.sleep_ms(50)
		wait_ready()
		cmd(0x12) # swreset
		wait_ready()

		log and log('Init: configuration')
		# XXX: maybe write data bytes as one block?
		# Output control
		cmd(0x01)
		data(0xf9)
		data(0x00)
		data(0x00)
		# Data entry mode
		cmd(0x11)
		data(0x03) # landscape mode uses 0x07
		# Window configuration
		cmd(0x44) # set_ram_x_address_start_end_position
		data(((x0 := 0)>>3) & 0xff)
		data(((x1 := self.w-1)>>3) & 0xff)
		cmd(0x45) # set_ram_y_address_start_end_position
		data((y0 := 0) & 0xff)
		data((y0>>8) & 0xff)
		data((y1 := self.h-1) & 0xff)
		data((y1>>8) & 0xff)
		# Cusor position - not sure if x0/y0 are window or abs coordinates
		cmd(0x4e) # set_ram_x_address_counter
		data(x0 & 0xff)
		cmd(0x4f) # set_ram_y_address_counter
		data(y0 & 0xff)
		data((y0 >> 8) & 0xff)
		# BorderWaveform
		cmd(0x3c)
		data(0x05)
		# Read built-in temperature sensor
		cmd(0x18)
		data(0x80)
		# Display update control
		cmd(0x21)
		data(0x80)
		data(0x80)
		wait_ready()

		log and log('Init: finished')
		return self.EPDInterface(self)

	def __exit__(self, *err):
		self.cmd = self.data = self.p = self.spi = None
		self.log and self.log('Closed')

	def update(self): # activate display update sequence
		self.cmd(0x20)
		self.wait_ready()

	def display(self, fill=None, op='Display'):
		self.log and self.log(op)
		if fill: fill = bytes([fill]) * math.ceil(self.h * self.w / 8)
		self.cmd(0x24)
		self.data(fill or self.black_buff)
		self.cmd(0x26)
		self.data(fill or self.red_buff)
		self.update()

	def clear(self, fill=0xff):
		self.display(fill, 'Clear')

	def sleep(self):
		self.log and self.log('Sleep mode')
		self.cmd(0x10)
		self.data(0x01)
		time.sleep_ms(2_000)
		self.p.reset.value(0)

	def export_image_buffers(self):
		import sys, binascii
		line_len = 90
		for buff in self.black_buff, self.red_buff:
			print(f'\n{self.w} {self.h} {len(buff)}')
			for n in range(0, len(buff), line_len):
				sys.stdout.buffer.write(binascii.b2a_base64(buff[n:n+line_len]))


def draw(epd):
	# base fill
	epd.black.fill(0xff)
	epd.red.fill(0xff)

	# text
	epd.black.text('Waveshare', 0, 10, 0x00)
	epd.red.text('ePaper-2.13B', 0, 25, 0x00)
	epd.black.text('RPi Pico', 0, 40, 0x00)
	epd.red.text('Hello World', 0, 55, 0x00)

	# lines
	epd.red.vline(10, 90, 40, 0x00)
	epd.red.vline(90, 90, 40, 0x00)
	epd.black.hline(10, 90, 80, 0x00)
	epd.black.hline(10, 130, 80, 0x00)
	epd.red.line(10, 90, 90, 130, 0x00)
	epd.black.line(90, 90, 10, 130, 0x00)

	# rectangles
	epd.black.rect(10, 150, 40, 40, 0x00)
	epd.red.fill_rect(60, 150, 40, 40, 0x00)


epd = EPD_2in13_B_V4_Portrait()
draw(epd)
epd.export_image_buffers()


# with EPD_2in13_B_V4_Portrait(1, dc=8, cs=9, reset=12, busy=13, verbose=True) as epd:
# 	draw(epd)

# 	epd.scr.display()
# 	print('display delay')
# 	time.sleep(60)

# 	epd.scr.clear()
# 	time.sleep(2)

# 	epd.scr.sleep()
