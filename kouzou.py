from functools import partial
import struct as _struct
from collections import defaultdict, ChainMap
from contextlib import contextmanager

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
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(key)

	def __setattr__(self, key, value):
		self[key] = value

	def __delattr__(self, key):
		try:
			del self[key]
		except KeyError:
			raise AttributeError(key)


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

	def __rshift__(self, other): return _after(self, other)
	def __rrshift__(self, other): return _after(other, self)
	def __lshift__(self, other): return _before(self, other)
	def __rlshift__(self, other): return _before(other, self)

	def read(self, ctx, nil_ok=False, inner=None):
		raise NotImplementedError(self)
	def write(self, ctx, v, inner=None):
		raise NotImplementedError(self)

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
		return self._lhs.size(self._rhs)

	def __repr__(self): return f"{self._lhs!r}@{self._rhs!r}"

class _before(element):
	def __init__(self, lhs, rhs):
		self._lhs = element.one(lhs)
		self._rhs = element.one(rhs)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		a = self._lhs.read(ctx)
		b = self._rhs.read(ctx, True)
		if b is not NIL:
			raise ValueError(f"... << {self._rhs!r} ... must return nil")
		return a

	def write(self, ctx, v, inner=None):
		assert inner is None
		self._lhs.write(ctx, v)
		self._rhs.write(ctx, v)

	def size(self, inner=None):
		assert inner is None
		return self._lhs.size() + self._rhs._size

	def __repr__(self): return f"{self._lhs!r} << {self._rhs!r}"

class _after(element):
	def __init__(self, lhs, rhs):
		self._lhs = element.one(lhs)
		self._rhs = element.one(rhs)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		a = self._lhs.read(ctx, True)
		b = self._rhs.read(ctx)
		if a is not NIL:
			raise ValueError(f"{self._lhs!r} >> ... must return nil")
		return b

	def write(self, ctx, v, inner=None):
		assert inner is None
		self._lhs.write(ctx, v)
		self._rhs.write(ctx, v)

	def size(self, inner=None):
		assert inner is None
		return self._lhs.size() + self._rhs._size

	def __repr__(self): return f"{self._lhs!r} >> {self._rhs!r}"


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
			inner.write(ctx, self._val)

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

class lazy(element):
	def __init__(self, provider):
		assert callable(provider)
		self._provider = provider
		self._init = False
		self._value = None

	@property
	def value(self):
		if not self._init:
			self.value = self._provider()
		return self._value

	@value.setter
	def value(self, v):
		self._value = v
		self._init = True

	def read(self, ctx, nil_ok=False, inner=None):
		return self.value.read(ctx, nil_ok, inner)

	def write(self, ctx, v, inner=None):
		return self.value.write(ctx, v, inner)

	def size(self, ctx, v, inner=None):
		return self.value.write(ctx, v, inner)

	def __repr__(self):
		return f"lazy({self._provider!r})"

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
	def write(self, ctx, v, inner=None):
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
		with ctx.newscope():
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
		with ctx.newscope():
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
		assert len(v) == len(self._items), (self, v)
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

	def size(self, inner=None):
		assert inner is not None
		return self._addend.size() + inner.size()

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
			ctx.later(ctx.tell(), inner, lambda: ctx.scope[self._name])
			ctx.write(_bytes(inner.size()))

	def size(self, inner=None):
		assert inner is None
		return 0

	def __repr__(self):
		if isinstance(self._name, str) and self._name.isidentifier():
			return f"ref.{self._name}"
		return f"ref({self._name!r})"

# {{{2 Later/now
class later(element):
	def __init__(self, key, pos):
		self._key = key
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
		ctx.root.setdefault("_later", defaultdict(_list))[self._key].append(
			(self._pos, pos, inner, v, ctx.scope)
		)

	def size(self, inner=None):
		assert inner is not None
		return self._pos.size()

	def __repr__(self):
		return f"later({self._key!r}, {self._pos!r})"

class now(element):
	def __init__(self, key):
		self._key = key

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		assert nil_ok
		return NIL

	def write(self, ctx, v, inner=None):
		assert inner is None

		for (posT, pos, valT, val, scope) in ctx.root.get("_later", defaultdict(_list)).pop(self._key, []):
			ctx.later(pos, posT, lambda p=ctx.tell(): p)
			with ctx.newscope(scope):
				valT.write(ctx, val)

	def __repr__(self):
		return f"now({self._key!r})"

# {{{2 Cursor/advance/nowC
class cursor(element):
	def __init__(self, key, pos):
		self._key = key
		self._pos = pos

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		assert nil_ok
		v = self._pos.read(ctx)
		ctx.root.setdefault("_cursors", {})[self._key] = v
		return NIL

	def write(self, ctx, v, inner=None):
		assert inner is None
		ctx.root.setdefault("_cursorItems", {})[self._key] = []
		ctx.later(ctx.tell(), self._pos, lambda: ctx.root["_cursors"].pop(self._key))
		ctx.write(_bytes(self._pos.size()))

	def size(self, inner=None):
		assert inner is None
		return self._pos.size()

	def __repr__(self):
		return f"cursor({self._key!r}, {self._pos!r})"


class advance(element):
	def __init__(self, key):
		self._key = key

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		pos = ctx.root["_cursors"][self._key]
		origpos = ctx.tell()
		try:
			ctx.seek(pos)
			v = inner.read(ctx)
			ctx.root["_cursors"][self._key] = ctx.tell()
			return v
		finally:
			ctx.seek(origpos)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		ctx.root["_cursorItems"][self._key].append((inner, v))

	def __repr__(self):
		return f"advance({self._key!r})"

class nowC(element):
	def __init__(self, key):
		self._key = key

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		assert nil_ok
		return NIL

	def write(self, ctx, v, inner=None):
		assert inner is None

		ctx.root.setdefault("_cursors", {})[self._key] = ctx.tell()
		for valT, val in ctx.root["_cursorItems"].pop(self._key):
			valT.write(ctx, val)

	def __repr__(self):
		return f"nowC({self._key!r})"

# {{{2

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
		v = np.array(v, dtype=self._dtype)
		self._shape.write(ctx, v.shape)
		ctx.write(v.tobytes())

	def __repr__(self):
		return "numpy({self._shape!r}, {self._dtype!r})"

# {{{1 IO

class Context:
	def __init__(self, file, scope=None):
		self.file = file
		self.root = {}
		self.scope = ChainMap()
		if scope is not None:
			self.scope.maps.append(scope)

	def tell(self):
		return self.file.tell()

	def seek(self, where, whence=0):
		self.file.seek(where, whence)

	@contextmanager
	def newscope(self, scope=None):
		old_scope = self.scope
		try:
			self.scope = scope if scope is not None else self.scope.new_child()
			yield
		finally:
			self.scope = old_scope

class ReadContext(Context):
	def read(self, size):
		v = self.file.read(size)
		if len(v) < size: raise ValueError(f"could not read {size} bytes")
		return v

class WriteContext(Context):
	def __init__(self, file, scope):
		super().__init__(file, scope)
		self._later = []

	def write(self, bytes):
		self.file.write(bytes)

	def later(self, pos, type, val):
		self._later.append((pos, type, val, self.scope))

def read(type, f, scope=None):
	ctx = ReadContext(f, scope)
	v = type.read(ctx)
	return v

def write(type, f, v, scope=None):
	ctx = WriteContext(f, scope)
	type.write(ctx, v)
	if v := ctx.root.get("_later"): raise ValueError("Unhandled later(): ", v)
	if v := ctx.root.get("_cursor"): raise ValueError("Unhandled cursor(): ", v)
	while ctx._later:
		pos, type, v, sc = ctx._later.pop()
		ctx.seek(pos)
		with ctx.newscope(sc):
			type.write(ctx, v())

class tracing:
	def __enter__(self):
		import sys
		self.origtrace = sys.gettrace()

		depth = 0

		@sys.settrace
		def trace(frame, what, obj):
			nonlocal depth
			if what == "call" and frame.f_code.co_name in ["read", "write"]:
				self = frame.f_locals.get("self")
				if isinstance(self, element) and not isinstance(self, _compose):
					if frame.f_code.co_name == "write" and not isinstance(self, field):
						print(*" "*depth, frame.f_locals["ctx"].tell(), self, repr(frame.f_locals["v"]))
					else:
						print(*" "*depth, frame.f_locals["ctx"].tell(), self)
					depth += 1
					def traceinner(frame, what, obj):
						nonlocal depth
						if what == "return":
							depth -= 1
							print(*" "*depth, what, obj)
					return traceinner

	def __exit__(self, *a):
		import sys
		sys.settrace(self.origtrace)
