import kouzou as k
class if_(k.element):
	def __init__(self, cond, val):
		self._cond = cond
		self._val = val

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		success = True
		try:
			k.lookahead.read(ctx, True, self._cond)
		except AssertionError:
			raise
		except Exception:
			success = False
		if success == self._val:
			return inner.read(ctx)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		if v is not None:
			inner.write(ctx, v)

	def __repr__(self):
		return f"if_({self._cond!r}, {self._val!r})"
