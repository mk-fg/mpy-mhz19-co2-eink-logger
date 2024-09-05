#!/usr/bin/env python

import pathlib as pl, contextlib as cl, itertools as it
import os, sys, io, base64

import PIL.Image # pillow module


def main(args=None):
	import argparse, textwrap, re
	dd = lambda text: re.sub( r' \t+', ' ',
		textwrap.dedent(text).strip('\n') + '\n' ).replace('\t', '  ')
	parser = argparse.ArgumentParser(
		formatter_class=argparse.RawTextHelpFormatter, description=dd('''
			Merge b64-exported black/red image buffers to a png file.'''))
	parser.add_argument('-i', '--in-b64-file', metavar='file', help=dd('''
		File exported by epd.export_image_buffers() func in micropython script.
		Format is empty-line-separated base64 lines with "<w> <h> <len>" prefix.
		File should have exactly two MONO_HLSB bitmap buffers, black then red.
		"-" can be used to read data from stdin instead, which is the default.'''))
	parser.add_argument('-o', '--out-png-file', metavar='file', help=dd('''
		PNG file to produce by combining exported black/red input buffers.
		"-" can be used to output data to stdout instead, which is the default.'''))
	parser.add_argument('--invert', action='store_true', help=dd('''
		Do not assume that bitmaps are inverted,
			which is the default, as bitmaps sent to ePaper screen are inverted.'''))
	opts = parser.parse_args(sys.argv[1:] if args is None else args)

	@cl.contextmanager
	def in_file(path):
		if not path or path == '-': return (yield sys.stdin)
		with open(path) as src: yield src

	@cl.contextmanager
	def out_func_bin(path):
		if not path or path == '-': return (yield sys.stdout.buffer.write)
		p = pl.Path(f'{path}.new')
		try:
			with open(p, 'wb') as tmp: yield tmp.write
		finally: p.unlink(missing_ok=True)

	buff_wh, buffs = None, dict(black=None, red=None)
	with in_file(opts.in_b64_file) as src:
		for k in buffs:
			w = h = sz = None; b64 = list()
			while line := src.readline():
				if not (line := line.strip()) and b64: break
				elif not line: continue
				if not sz: w, h, sz = map(int, line.split()); continue
				b64.append(line)
			buff = buffs[k] = base64.b64decode(''.join(b64))
			if (n := len(buff)) != sz: raise ValueError(
				f'Buffer size mismatch [{k}]: expected={sz or 0:,d} actual={len(buff):,d}' )
			if w*h//8 != sz or (buff_wh and buff_wh != (w, h)): raise ValueError(
				f'Bitmap dimensions mismatch [{k}]: sz={sz:,d} wh={buff_wh} actual={(w,h)}' )
			buff_wh = w, h

	(w, h), C, invert = buff_wh, 0xff, not opts.invert
	colors = dict(black=(0,0,0,C), red=(C,0,0,C))
	with (
			PIL.Image.new('RGBA', buff_wh) as img,
			out_func_bin(opts.out_png_file) as out ):
		for c, buff in buffs.items():
			c, sz, wb = colors[c], len(buff), w//8
			for y, x in it.product(range(0, sz, wb), range(wb)):
				bits = buff[y+x]
				for n in range(8):
					if ((bits >> (7 - n)) & 1) ^ invert: img.putpixel((x*8 + n, y//wb), c)
		img.save(buff := io.BytesIO(), format='png', optimize=True)
		out(buff.getvalue())


if __name__ == '__main__':
	try: sys.exit(main())
	except BrokenPipeError: # stdout pipe closed
		os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
		sys.exit(1)
