import machine, time, struct


def response_bytes(cmd, bs):
	if csum := sum(bs[1:-1]) % 0x100: csum = 0xff - csum + 1
	if ( bs and len(bs) == 9 and bs[0] == 0xff
			and bs[1] == cmd and csum == bs[-1] ):
		return bs[2:-1] # 6B of actual payload


def read_co2(sensor):
	for n in range(5):
		bs = sensor.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
		bs = sensor.read(bs)
		print('raw-read:', bs)
		if bs := response_bytes(0x86, bs): return bs[0]*256 + bs[1]
		time.sleep(0.1)


# TODO: see if ABCCheck from MHZ19.cpp, might be needed
#  runs provisioning(ABC, MHZ19_ABC_PERIOD_OFF) every 12h, not sure why

def check_abc(sensor):
	for n in range(5):
		bs = sensor.write(b'\xff\x01\x7d\x00\x00\x00\x00\x00\x82')
		bs = sensor.read(bs)
		print('raw-read:', bs)
		if bs := response_bytes(0x7d, bs): return bs[5]
		time.sleep(0.1)


sensor = machine.UART(
	0, tx=machine.Pin(16), rx=machine.Pin(17),
	baudrate=9600, bits=8, stop=1, parity=None )
print('CO2:', read_co2(sensor))
# print('ABC:', check_abc(sensor))
