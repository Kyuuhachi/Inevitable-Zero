NULL = object()
def diff(a, b):
	import insn
	import difflib

	if type(a) != type(b):
		yield a, b

	elif isinstance(a, tuple):
		if len(a) != len(b):
			yield a, b
		else:
			for i, (a_, b_) in enumerate(zip(a, b)):
				yield from diff(a_, b_)

	elif isinstance(a, dict):
		for k in a.keys() | b.keys():
			if k not in a:
				yield NULL, b[k]
			elif k not in b:
				yield a[k], NULL
			else:
				yield from diff(a[k], b[k])

	elif isinstance(a, list):
		for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
			None,
			[repr(a) for a in a],
			[repr(b) for b in b],
			False,
		).get_opcodes():
			if tag == "equal":
				pass
			else:
				if i2-i1 == j2-j1:
					for a_, b_ in zip(a[i1:i2], b[j1:j2]):
						yield from diff(a_, b_)
				else:
					yield a[i1:i2], b[j1:j2]

	elif type(a) == insn.Insn:
		if a.name != b.name:
			yield a, b
		else:
			yield from diff(a.args, b.args)

	elif a != b:
		yield a, b
