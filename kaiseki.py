import numpy as np
from dataclasses import dataclass, field
from contextlib import contextmanager
from os import isatty
import mmap as _mmap
import sys
import re
import bisect

__all__ = ["Reader"]

escape = re.compile("[\x00-\x1F\x7F\x80-\x9F]")

class B(bytes):
	def __repr__(self):
		return " ".join("%02X" % x for x in self)
	__str__ = __repr__

	def __getitem__(self, key):
		data = super().__getitem__(key)
		if type(data) is bytes:
			return B(data)
		return data

@dataclass
class Reader:
	dt: bytes = field(repr=False)
	encoding: str = "ascii"
	errors: str = "strict"
	i: int = 0

	from dataclasses import replace

	def __setitem__(self, n, v):
		if isinstance(n, tuple):
			assert len(v) == len(n)
			for a, b in zip(n, v):
				self[a] = b
			return

		start = self.i

		if callable(n):
			v2 = n()
			if v is Ellipsis:
				v = v2

		elif isinstance(v, int):
			if   n == 1: v2 = self.u1() if v >= 0 else self.i1()
			elif n == 2: v2 = self.u2() if v >= 0 else self.i2()
			elif n == 4: v2 = self.u4() if v >= 0 else self.i4()
			elif n == 8: v2 = self.u8() if v >= 0 else self.i8()
			elif v == 0: v2 = self[n]; v = bytes(n)
			else: raise ValueError(n, int)

		elif isinstance(v, float):
			if   n == 4: v2 = self.f4()
			elif n == 8: v2 = self.f8()
			else: raise ValueError(n, float)

		elif isinstance(v, bytes):
			if n is Ellipsis: n = len(v)
			v2 = bytes(self._get(n))

		elif v is Ellipsis:
			v = v2 = bytes(self._get(n))

		elif v is None:
			v = bytes(n)
			v2 = bytes(self._get(n))

		elif isinstance(v, str):
			if n is Ellipsis: n = len(v.encode(self.encoding))
			v2 = self._get(n).decode(self.encoding, errors="replace")

		else: raise TypeError(v)

		if v != v2:
			raise ValueError(f"At 0x{start:04x}:\n  expected {v!r}\n  found    {v2!r}")

	def __getitem__(self, n):
		return B(self._get(n))

	def _get(self, n):
		v = self.dt[self.i:self.i+n]
		if len(v) != n:
			raise ValueError(f"At 0x{self.i:04x}: tried to read {n} bytes, but only {len(v)} were available")
		self.i += n
		return v

	def byte(self):
		v = self.dt[self.i]
		self.i += 1
		return v

	@property
	def remaining(self):
		return len(self.dt) - self.i

	def __bool__(self):
		return self.remaining != 0

	def __len__(self):
		return len(self.dt)

	def one(self, dtype):
		return self.some(1, dtype)[0]

	def some(self, shape, dtype):
		x = np.ndarray(shape, dtype, buffer=self.dt, offset=self.i)
		self.i += x.nbytes
		return x

	def until(self, delim, size=None, junk=False):
		assert delim
		if size is not None:
			v = self[size]
			if delim in v:
				idx = v.index(delim)
				if not junk:
					assert v[idx:] == b"\0" * (size-idx), v[idx:]
				v = v[:idx]
		else:
			assert not junk, "junk is not applicable in this context"
			if isinstance(self.dt, (bytes, bytearray)):
				i = self.dt.index(delim, self.i)
			else:
				for i, b in enumerate(self.dt[self.i:], self.i):
					if b == delim[0]:
						if self.dt[i:i+len(delim)] == delim:
							break
				else:
					raise ValueError(f"Did not find delimiter {delim!r}")

			v = self.dt[self.i:i]
			self.i = i+len(delim)
		return B(v)

	def at(self, i=None):
		return self.replace(i=i if i is not None else self.i)

	def sub(self, n):
		dt = memoryview(self.dt)[self.i:self.i+n]
		self.i += n
		return self.replace(i=0, dt=dt)

	def u1(self): return self.byte()
	def u2(self): return self.u1() | self.u1() <<  8
	def u4(self): return self.u2() | self.u2() << 16
	def u8(self): return self.u4() | self.u4() << 32

	def i1(self): return _sign(self.u1(), 1<< 7)
	def i2(self): return _sign(self.u2(), 1<<15)
	def i4(self): return _sign(self.u4(), 1<<31)
	def i8(self): return _sign(self.u8(), 1<<63)

	def f4(self, *, allow_nan=False):
		a = self.one("f4")
		if not allow_nan and not np.isfinite(a):
			raise ValueError(float(a))
		return float(a)

	def f8(self, *, allow_nan=False):
		a = self.one("f8")
		if not allow_nan and not np.isfinite(a):
			raise ValueError(float(a))
		return float(a)

	def zstr(self, size=None, encoding=None, errors=None, junk=False):
		data = self.until(b"\0", size, junk=junk)
		try:
			return data.decode(encoding or self.encoding, errors=errors or self.errors)
		except Exception as e:
			raise ValueError(bytes(data)) from e

	def __iter__(self):
		end = len(self.dt)
		while self.i < end:
			yield self.byte()

	@classmethod
	@contextmanager
	def open(cls, file, *args, **kwargs):
		with open(file, "rb") as f:
			with cls.openfd(f, *args, **kwargs) as f:
				yield f

	@classmethod
	@contextmanager
	def openfd(cls, f, *args, mmap: bool = False, **kwargs):
		if mmap:
			with _mmap.mmap(f.fileno(), 0, prot=_mmap.PROT_READ, flags=_mmap.MAP_PRIVATE) as m:
				yield cls(memoryview(np.frombuffer(m, dtype="u1")), *args, **kwargs)
		else:
			yield cls(memoryview(np.frombuffer(f.read(), dtype="u1")), *args, **kwargs)
			# The np there makes it not complain about exported pointers

	def dump(self, *,
			start=None, lines=None, length=None, end=None, width=None,
			num=1, encoding="auto", mark=frozenset(), blank=None,
			color=None, gray=False, binary=False,
			file=sys.stdout, skip=False):
		mark = frozenset(mark)

		if encoding == "auto":
			encoding = self.encoding
		if width is None:
			if binary:
				width = 24 if encoding is None else 16
			else:
				width = 72 if encoding is None else 48

		assert (lines is not None) + (length is not None) <= 1
		if lines is not None: length = lines * width
		oneline = lines == 1 if blank is None else not blank
		del lines

		assert (length is not None) + (start is not None) + (end is not None) <= 2
		if length is None:
			if start is None: start = self.i
			if end   is None: end = len(self)
		else:
			if start is None: start = end - length if end is not None else self.i
			if end   is None: end = start + length
		del length

		if start < 0: start = 0
		if end > len(self): end = len(self)

		if hasattr(file, "fileno") and isatty(file.fileno()) if color is None else color:
			fmt = ""
			def format(*f):
				nonlocal fmt
				if f != fmt:
					hl.append("\x1B[%sm" % ";".join(map(str, [0, *f])))
					fmt = f
		else:
			def format(*f): pass

		if start == end:
			hl = []
			format(2)
			hl.append("--empty--")
			format()
			print("".join(hl), file=file)
			if not oneline:
				print(file=file)
			return

		numwidth = len("%X" % max(0, len(self)-1))

		for i in range(start, end, width):
			hl = []
			chunk = bytes(self.dt[i:min(i+width, end)])
			chunkl = list(chunk)
			if not chunk: break
			while len(chunkl) < width:
				chunkl.append(None)

			if num:
				if numwidth < num:
					format(2,33)
					hl.append("0" * (num - numwidth))
				format(33)
				hl.append("{:0{}X} ".format(i, numwidth))

			for j, b in enumerate(chunkl, i):
				if b is None:
					format()
					hl.append("   ")
					continue
				if gray:
					if   0x00 == b: newfmt = [48,5,237,38,5,244]
					else:           newfmt = [48,5,238+b//16]
					if b < 0x30: newfmt += [38,5,245]
					else:        newfmt += [38,5,236]
				else:
					if   0x00 == b       : newfmt = [2]
					elif 0x20 <= b < 0x7F: newfmt = [38,5,10]
					elif 0xFF == b       : newfmt = [38,5,9]
					else:                  newfmt = []

				format(*newfmt)
				hl.append(f"{b:08b}" if binary else f"{b:02X}")

				if j+1 == self.i:
					format(1,34,7)
				elif j+1 in mark:
					format(1,34)

				hl.append("•" if j+1 in mark else " ")

			if encoding is not None:
				format()
				hl.append(escape.sub("\x1B[2m·\x1B[m", chunk.decode(encoding, errors="replace")))
			elif j+1 not in mark and not gray:
				hl.pop() # Trailing space
			format()
			print("".join(hl), file=file)

		if not oneline:
			print(file=file)

		if skip:
			self.i = end

def _sign(x, y): return x - 2*(x & y)

@dataclass
class BEReader(Reader):
	def u2(self): return self.u1() <<  8 | self.u1()
	def u4(self): return self.u2() << 16 | self.u2()
	def u8(self): return self.u4() << 32 | self.u4()
	def some(self, n, dtype): return super().some(n, np.dtype(dtype).newbyteorder())

@dataclass
class CoverageReader(Reader):
	_ranges: [range] = field(default_factory=list)
	_current: int = None
	_offset: int = 0

	@contextmanager
	def see(self):
		i = self.i + self._offset
		yield
		j = self.i + self._offset
		assert i <= j
		if i == j: return

		if self._current is not None \
				and self._ranges[self._current][0] <= j \
				and i <= self._ranges[self._current][1]:
			self._ranges[self._current] = (
				min(self._ranges[self._current][0], i),
				max(j, self._ranges[self._current][1]),
			)
		else:
			self._current = bisect.bisect(self._ranges, (i, j))
			self._ranges.insert(self._current, (i, j))

		while 0 < self._current:
			(a, b), (c, d) = self._ranges[self._current-1:self._current+1]
			if c <= b:
				self._ranges[self._current-1:self._current+1] = [(min(a, c), max(b, d))]
				self._current -= 1
			else:
				break

		while self._current < len(self._ranges) - 1:
			(a, b), (c, d) = self._ranges[self._current:self._current+2]
			if c <= b:
				self._ranges[self._current:self._current+2] = [(min(a, c), max(b, d))]
			else:
				break

	def byte(self):
		with self.see():
			return super().byte()

	def __getitem__(self, n):
		with self.see():
			return super().__getitem__(n)

	def __setitem__(self, n, v):
		with self.see():
			return super().__setitem__(n, v)

	def some(self, *a, **kw):
		with self.see():
			return super().some(*a, **kw)

	def until(self, *a, **kw):
		with self.see():
			return super().until(*a, **kw)

	def seen(self):
		return list(self._ranges)

	def unseen(self, minsize=1):
		x = 0
		uns = []
		for a, b in self.seen():
			uns.append((x, a))
			x = b
		uns.append((x, len(self)))
		return list((a, b) for a, b in uns if b - a >= minsize)

	def unlink(self):
		return self.replace(_ranges=[], _current=None, _offset=0)

	def sub(self, *a, **kw):
		return super().sub(*a, **kw).replace(_offset=self._offset+self.i)
