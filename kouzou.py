from functools import partial
import struct as _struct

CONSTANT_TYPES = (int, bytes, str, float)

_int = int
_bytes = bytes
_list = list
_tuple = tuple

class NIL:
	def __bool__(self): raise ValueError
	def __repr__(self): return "NIL"
NIL = NIL()


class dotdict(dict):
	__getattr__ = dict.__getitem__
	__setattr__ = dict.__setitem__
	__delattr__ = dict.__delitem__


class element:
	@staticmethod
	def one(v, /):
		if isinstance(v, CONSTANT_TYPES): return const(v)
		assert isinstance(v, element), v
		return v

	def __matmul__(self, other): return _compose(self, other)
	def __rmatmul__(self, other): return element.one(other) @ self
	def __ror__(self, other):
		if isinstance(other, str):
			return alias(other, self)
		return NotImplemented

	def read(self, ctx, nil_ok=False, inner=None):
		raise NotImplementedError
	def write(self, ctx, v, inner=None):
		raise NotImplementedError

	def size(self, inner=None): return NotImplemented

class _compose(element):
	def __init__(self, lhs, rhs):
		self._lhs = element.one(lhs)
		self._rhs = element.one(rhs)
		assert not isinstance(self._lhs, _compose) # Sanity check

	# Why is matmul left-associative...
	def __matmul__(self, other): return self._lhs @ (self._rhs @ other)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		return self._lhs.read(ctx, nil_ok, self._rhs)

	def write(self, ctx, v, inner=None):
		assert inner is None
		return self._lhs.write(ctx, v, self._rhs)

	def size(self, inner=None):
		assert inner is None
		return self._lhs.size(self.rhs)

	def __repr__(self): return f"{self._lhs!r}@{self._rhs!r}"


class const(element):
	def __init__(self, val):
		self._val = val

	def read(self, ctx, nil_ok=False, inner=None):
		if inner is None:
			return self._val
		else:
			assert nil_ok
			v = inner.read(ctx, False)
			if v != self._val:
				raise ValueError(f"Expected {self._val!r}, got {v!r}")
			return NIL

	def write(self, ctx, v, inner=None):
		if inner is None:
			if v != self._val:
				raise ValueError(f"Expected {self._val!r}, got {v!r}")
		else:
			inner.write(ctx, self._val, False)

	def size(self, inner=None):
		assert inner is None
		return 0

	def __repr__(self):
		if isinstance(self._val, CONSTANT_TYPES):
			return f"{self._val!r}"
		else:
			return f"const({self._val!r})"

class iso(element):
	def __init__(self, read, write):
		self._read = read
		self._write = write
	
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		return self._read(inner.read(ctx))

	def write(self, ctx, v, inner=None):
		assert inner is not None
		return inner.write(ctx, self._write(v))

	def size(self, inner):
		assert inner is not None
		return inner.size()

	def __repr__(self): return f"iso({self._read!r}, {self._write!r})"

	def __invert__(self):
		return iso(self._write, self._read)

class alias(element):
	def __init__(self, name, el):
		self._name = name
		self._el = el

		self.read = el.read
		self.write = el.write
		self.size = el.size

	def __repr__(self):
		return self._name

# {{{1 Primitives

class int(element):
	def __init__(self, size, *, signed, endian="little"):
		size = size.__index__()
		assert type(signed) is bool
		assert endian in ("little", "big")
		self._size = size
		self._signed = signed
		self._endian = endian

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		return _int.from_bytes(ctx.read(self._size), self._endian, signed=self._signed)
	def write (self, ctx, v, inner=None):
		assert inner is None
		ctx.write(v.__index__().to_bytes(self._size, self._endian, signed=self._signed))

	def size(self, inner=None):
		assert inner is None
		return self._size

	def __repr__(self):
		return f"int({self._size}, signed={self._signed!r}, endian={self._endian!r})"

u1 = "u1"|int(1, signed=False)
u2 = "u2"|int(2, signed=False)
u4 = "u4"|int(4, signed=False)
u8 = "u8"|int(8, signed=False)

i1 = "i1"|int(1, signed=True)
i2 = "i2"|int(2, signed=True)
i4 = "i4"|int(4, signed=True)
i8 = "i8"|int(8, signed=True)

u1be = "u1be"|int(1, signed=False, endian="big")
u2be = "u2be"|int(2, signed=False, endian="big")
u4be = "u4be"|int(4, signed=False, endian="big")
u8be = "u8be"|int(8, signed=False, endian="big")

i1be = "i1be"|int(1, signed=True, endian="big")
i2be = "i2be"|int(2, signed=True, endian="big")
i4be = "i4be"|int(4, signed=True, endian="big")
i8be = "i8be"|int(8, signed=True, endian="big")

class f4(element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		return _struct.unpack("f", ctx.read(4))[0]

	def write (self, ctx, v, inner=None):
		assert inner is None
		ctx.write(_struct.pack("f", v))

	def size(self, inner=None):
		assert inner is None
		return 4

	def __repr__(self):
		return "f4"
f4 = f4()


class bytes(element):
	def __init__(self, size):
		self._size = element.one(size)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		return ctx.read(self._size.read(ctx))

	def write(self, ctx, v, inner=None):
		assert inner is None
		self._size.write(ctx, len(v))
		ctx.write(v)

	def size(self, inner=None):
		assert inner is None
		return self._size.__index__()

	def __repr__(self):
		return f"bytes({self._size!r})"

class zbytes(element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		val = bytearray()
		while x := ctx.read(1)[0]:
			val.append(x)
		return _bytes(val)

	def write(self, ctx, v, inner=None):
		assert inner is None
		if b"\0" in v:
			raise ValueError(f"{v!r} contains null bytes")
		ctx.write(v + b"\0")

	def __repr__(self): return "zbytes()"

class fbytes(element):
	def __init__(self, size):
		self._size = size.__index__()

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		return ctx.read(self._size).split(b"\0")[0]

	def write(self, ctx, v, inner=None):
		assert inner is None
		if len(v) > self._size:
			raise ValueError(f"{v!r} is longer than {self._size}")
		if b"\0" in v:
			raise ValueError(f"{v!r} contains null bytes")
		ctx.write(v + _bytes(self._size - len(v)))

	def size(self, inner=None):
		assert inner is None
		return self._size

	def __repr__(self): return f"fbytes({self._size})"

class enc(iso):
	def __init__(self, encoding):
		super().__init__(
			partial(_bytes.decode, encoding=encoding),
			partial(str.encode, encoding=encoding),
		)
		self._encoding = encoding

	def __repr__(self):
		return f"enc({self._encoding!r})"

# {{{1 Composites

class field_meta(type(element)):
	def __getattr__(cls, name):
		return cls(name)

class field(iso, metaclass=field_meta):
	def __init__(self, name):
		super().__init__(
			lambda a: dotdict({name: a}),
			lambda b: b[name],
		)
		self._name = name

	def __repr__(self):
		if isinstance(self._name, str) and self._name.isidentifier():
			return f"_.{self._name}"
		return f"field({self._name!r})"
_ = field


class struct(element):
	def __init__(self, *items):
		self._items = [element.one(i) for i in items]

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		vs = {}
		for x in self._items:
			val = x.read(ctx, True)
			if val is not NIL:
				assert isinstance(val, dict), f"Invalid struct item: {val!r} (from {x!r})"
				if dup := set(vs.keys() & val.keys()):
					raise ValueError(f"Duplicate keys in {self!r}: {dup!r}")
				vs.update(val)
		return dotdict(vs)

	def write(self, ctx, v, inner=None):
		assert inner is None
		for x in self._items:
			x.write(ctx, v)

	def size(self, inner=None):
		assert inner is None
		try:
			return sum(x.size() for x in self._items)
		except Exception:
			return NotImplemented

	def __repr__(self):
		return f"struct({', '.join(map(repr, self._items))})"


class list(element):
	def __init__(self, count):
		self._count = element.one(count)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		count = self._count.read(ctx)
		if count < 0:
			raise ValueError("negative count")
		return [inner.read(ctx) for _ in range(count)]

	def write(self, ctx, v, inner=None):
		assert inner is not None
		v = _list(v)
		self._count.write(ctx, len(v))
		for val in v:
			inner.write(ctx, val)

	def size(self, inner=None):
		assert inner is not None
		# Would be possible to find the size of non-constant-sized lists
		# if I add a ctx parameter, but doesn't seem important enough right now
		try:
			return self._count.__index__() * inner.size()
		except Exception:
			return NotImplemented

	def __repr__(self): return f"list({self._count!r})"


class while_(element):
	def __init__(self, predicate):
		self._predicate = predicate

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		xs = []
		while True:
			xs.append(inner.read(ctx))
			if not self._predicate(xs[-1]):
				break
		return xs

	def write(self, ctx, v, inner=None):
		assert inner is not None
		for i, val in enumerate(v):
			inner.write(ctx, val)
			assert self._predicate(val) == (i != len(v)-1)

	def __repr__(self): return f"while_({self._predicate!r})"


class switch(element):
	def __init__(self, cond, clauses):
		self._cond = element.one(cond)
		self._clauses = clauses # These .one are done at runtime

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		return element.one(self._clauses[self._cond.read(ctx)]).read(ctx)

	def write(self, ctx, v, inner=None):
		assert inner is None
		# The .read() here is not a typo.
		return element.one(self._clauses[self._cond.read(ctx)]).write(ctx, v)

	def __repr__(self): return f"switch({self._cond!r}, {self._clauses!r})"


class tuple(element):
	def __init__(self, *items):
		self._items = [element.one(i) for i in items]

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		return _tuple(x.read(ctx) for x in self._items)

	def write(self, ctx, v, inner=None):
		assert inner is None
		assert len(v) == len(self._items)
		for x, val in zip(self._items, v):
			x.write(ctx, val)

	def size(self, inner=None):
		assert inner is None
		try:
			return sum(x.size() for x in self._items)
		except Exception:
			return NotImplemented

	def __repr__(self):
		return f"tuple({', '.join(map(repr, self._items))})"

# {{{1 Utils

class div(iso):
	def __init__(self, divisor):
		super().__init__(self._read, self._write)
		self._divisor = divisor

	def _read(self, v):
		if v % self._divisor:
			raise ValueError(f"{v} is not divisible by {self._divisor}")
		return v // self._divisor

	def _write(self, v):
		return v * self._divisor

	def __repr__(self):
		return f"div({self._divisor!r})"

class add(element):
	def __init__(self, addend):
		self._addend = element.one(addend)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		v2 = self._addend.read(ctx)
		return inner.read(ctx) + v2

	def write(self, ctx, v, inner=None):
		assert inner is not None
		v2 = self._addend.read(ctx)
		inner.write(ctx, v - v2)

	def __repr__(self):
		return f"add({self._addend!r})"

# {{{1 Structure

class ref(element, metaclass=field_meta):
	def __init__(self, name):
		self._name = name

	def read(self, ctx, nil_ok=False, inner=None):
		if inner is None:
			return ctx.scope[self._name]
		else:
			ctx.scope[self._name] = inner.read(ctx)
			return NIL

	def write(self, ctx, v, inner=None):
		if inner is None:
			ctx.scope[self._name] = v
		else:
			pos = ctx.tell()
			ctx.write(_bytes(inner.size()))
			@ctx.later
			def fill_ref():
				ctx.seek(pos)
				inner.write(ctx, ctx.scope[self._name])

	def size(self, inner=None):
		assert inner is None
		return 0

	def __repr__(self):
		if isinstance(self._name, str) and self._name.isidentifier():
			return f"ref.{self._name}"
		return f"ref({self._name!r})"

class at(element):
	def __init__(self, pos):
		self._pos = element.one(pos)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		pos = self._pos.read(ctx)
		origpos = ctx.tell()
		try:
			ctx.seek(pos)
			return inner.read(ctx)
		finally:
			ctx.seek(origpos)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		pos = ctx.tell()
		ctx.write(_bytes(self._pos.size()))

		@ctx.later
		def fill_at():
			ctx.seek(0, 2)
			chunkpos = ctx.tell()
			inner.write(ctx, v)
			ctx.seek(pos)
			self._pos.write(ctx, chunkpos)

	def size(self, inner=None):
		assert inner is not None
		return self._pos.size()

	def __repr__(self):
		return f"at({self._pos!r})"

class lookahead(element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		origpos = ctx.tell()
		try:
			return inner.read(ctx, nil_ok)
		finally:
			ctx.seek(origpos)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		pass

	def size(self, inner=None):
		assert inner is not None
		return 0

	def __repr__(self):
		return "lookahead"
lookahead = lookahead()

# {{{1 Extras
class numpy(element):
	def __init__(self, shape, dtype):
		import numpy as np
		if not isinstance(shape, _tuple):
			shape = (shape,)
		self._shape = tuple(*shape)
		self._dtype = np.dtype(dtype)

	def read(self, ctx, nil_ok=False, inner=None):
		import numpy as np
		assert inner is None
		shape = self._shape.read(ctx)
		return np.frombuffer(
			ctx.read(self._dtype.itemsize * np.product(shape)),
			dtype=self._dtype
		).reshape(shape)

	def write(self, ctx, v, inner=None):
		import numpy as np
		assert inner is None
		v = np.array(v, dtype=self._dt)
		self._shape.write(ctx, v.shape)
		ctx.write(v.tobytes())

	def __repr__(self):
		return "numpy({self._shape!r}, {self._dtype!r})"

# {{{1 IO

class dfsqueue:
	def __init__(self, init=()):
		self.stack = _list(init)
		self.top = None

	def append(self, *item):
		self.stack.extend(item)

	def extend(self, items):
		self.stack.extend(items)

	def __iter__(self):
		assert self.top is None, "Multiple concurrent iterations not supported"
		s = self.stack
		self.top = 0
		while s:
			s[self.top:] = s[self.top:][::-1]
			val = s.pop()
			self.top = len(s)
			yield val
		self.top = None

	@property
	def items(self):
		stack = _list(self.stack)
		stack[self.top:] = stack[self.top:][::-1]
		return stack[::-1]

	def __repr__(self):
		return f"dfsqueue({self.items!r})"

class Context:
	def __init__(self, file):
		self.file = file
		self.scope = {}

	def tell(self):
		return self.file.tell()

	def seek(self, where, whence=0):
		self.file.seek(where, whence)

class ReadContext(Context):
	def read(self, size):
		v = self.file.read(size)
		if len(v) < size: raise ValueError(f"could not read {size} bytes")
		return v

class WriteContext(Context):
	def __init__(self, file):
		super().__init__(file)
		self._later = dfsqueue()
		self._last = []

	def write(self, bytes):
		self.file.write(bytes)

	def later(self, func):
		self._later.append(func)

def read(type, f):
	c = ReadContext(f)
	v = type.read(c)
	return v

def write(type, f, v):
	c = WriteContext(f)
	type.write(c, v)
	for f in c._later:
		f()
