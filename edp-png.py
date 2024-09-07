#!/usr/bin/env python

import pathlib as pl, contextlib as cl, collections as cs, itertools as it
import os, sys, io, base64

import PIL.Image # pillow module


def main(args=None):
	import argparse, textwrap, re
	dd = lambda text: re.sub( r' \t+', ' ',
		textwrap.dedent(text).strip('\n') + '\n' ).replace('\t', '  ')
	parser = argparse.ArgumentParser(
		formatter_class=argparse.RawTextHelpFormatter, description=dd('''
			Merge b64-exported black/red screen bitmaps from script log to a PNG file.
			Intended to be used with [screen] test-export = yes option,
				something like this: mpremote run main.py | tee test.log
			Where "test.log" will then have exported screen dumps for this script, which can
				convert e.g. last of these to PNG like this: %(prog)s -i test.b64 -o test.png'''))
	parser.add_argument('-i', '--in-b64-file', metavar='file', help=dd('''
		Output with epd.export_image_buffers() data from main.py micropython script.
		Every line relevant to this script should start with -p/--prefix (e.g. "-epd-:").
		Data format is "<BK/RD> <w> <h> <len-B>" first line, then base64 bitmap lines.
		File should have exactly two MONO_HLSB bitmap buffers, black then red.
		"-" can be used to read data from stdin instead, which is the default.'''))
	parser.add_argument('-o', '--out-png-file', metavar='file', help=dd('''
		PNG file to produce by combining exported black/red input buffers.
		"-" can be used to output data to stdout instead, which is the default.'''))
	parser.add_argument('-p', '--prefix', metavar='prefix', default='-epd-:',
		help='Line-prefix used for exported bitmaps -i/--in-b64-file. Default: %(default)s')
	parser.add_argument('-n', '--in-img-num', metavar='n', type=int, default=-1, help=dd('''
		Offset/index of image from the -i/--in-b64-file data to convert,
			using python list-index notation (0 - first, -1 - last, etc).
		Input can contain multiple images, and by default last one is used.'''))
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
			p.rename(path)
		finally: p.unlink(missing_ok=True)

	def iter_bitmaps(src):
		buff, pre_n = list(), len(pre := opts.prefix)
		while line := src.readline():
			if not (line := line.strip()):
				if buff: yield buff
				buff.clear(); continue
			if line.startswith(pre): buff.append(line[pre_n:])
		if buff: yield buff

	bitmap_t = cs.namedtuple('Bitmap', 'bt w h buff')
	def parse_bitmap(lines):
		bt, (w, h, sz) = (line := lines[0].split())[0], map(int, line[1:])
		buff = base64.b64decode(''.join(lines[1:]))
		if (n := len(buff)) != sz: raise ValueError(
			f'Buffer size mismatch [{bt}]: expected={sz or 0:,d} actual={len(buff):,d}' )
		if w*h//8 != sz: raise ValueError(
			f'Buffer dimensions mismatch [{bt}]: sz={sz:,d} actual={(w,h)}' )
		return bitmap_t(bt, w, h, buff)

	bitmaps = list()
	with in_file(opts.in_b64_file) as src:
		for bk, rd in it.batched(map(parse_bitmap, iter_bitmaps(src)), 2):
			if (bk.bt, rd.bt) != ('BK', 'RD') or (bk.w, bk.h) != (rd.w, rd.h):
				raise ValueError( 'Black/red bitmap type/dimensions'
					' mismatch: black{(bk.bt, bk.w, bk.h)} != red{(rd.bt, rd.w, rd.h)}' )
			bitmaps.append((bk, rd))
	bk, rd = bitmaps[opts.in_img_num]

	C, invert, (w, h) = 0xff, not opts.invert, (buff_wh := (bk.w, bk.h))
	with (
			PIL.Image.new('RGBA', buff_wh) as img,
			out_func_bin(opts.out_png_file) as out ):
		for c, bm in [(0,0,0,C), bk], [(C,0,0,C), rd]:
			sz, wb = len(buff := bm.buff), w//8
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
