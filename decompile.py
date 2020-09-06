from itertools import groupby
import insn

def till(asm, end, brk=None, hasaddr=True):
	body = []
	addr = None
	while asm[0].pos != end:
		a, asm = parse(asm, brk=brk)
		if not asm:
			raise ValueError(f"Did not find {int(end)}")

		if hasaddr and a.name == "GOTO" and asm[0].pos == end:
			(addr,) = a.args
		else:
			body.append(a)
	return body, addr, asm

def parse(asm, brk=None):
	if asm[0].name == "GOTO" and asm[0].args[0] == brk:
		return insn.Insn("BREAK"), asm[1:]

	if asm[0].name == "IF":
		head = asm[0]
		body, addr, asm_ = till(asm[1:], head.args[1], brk=head.args[1])
		if addr == head.pos:
			return insn.Insn("WHILE", head.args[0], body), asm_

		iftrue, addr, asm_ = till(asm[1:], head.args[1], brk=brk)
		iffalse = None
		if addr is not None:
			iffalse, _, asm_ = till(asm_, addr, brk=brk, hasaddr=False)
		return insn.Insn("IF", head.args[0], iftrue, iffalse), asm_

	if asm[0].name == "SWITCH":
		head = asm[0]
		asm_ = asm[1:]
		groups = groupby(sorted(head.args[1] + [(None, head.args[2])], key=lambda a: a[1]), key=lambda a: a[1])
		groups = [(a, tuple(b for b, _ in b)) for a, b in groups]
		assert len(groups) >= 2

		_, endpos, _ = till(asm_, groups[1][0])
		if endpos is None:
			assert groups[-1][1] == (None,)
			endpos = groups[-1][0]
			_, endpos2, _ = till(asm_, groups[-1][0])
			if endpos2 is not None:
				endpos = endpos2
			else:
				groups.pop()

		cases = {}
		ends = [addr for addr, _ in groups[1:]] + [endpos]
		for (addr, k), end in zip(groups, ends):
			for k_ in k[:-1]:
				cases[k_] = []
			cases[k[-1]], _, asm_ = till(asm_, end, brk=endpos, hasaddr=False)
		return insn.Insn("SWITCH", head.args[0], cases), asm_

	return asm[0], asm[1:]

def decompile(asm):
	asm0 = asm
	o = []
	asm = asm0
	while asm:
		a, asm = parse(asm)
		o.append(a)
	return o

def compile(expr, label, brk=None):
	for op in expr:
		if op.name == "BREAK":
			yield insn.Insn("GOTO", brk)

		elif op.name == "IF":
			if op.args[2] is None:
				l = label()
				yield insn.Insn("IF", op.args[0], l)
				yield from compile(op.args[1], label, brk)
				yield l
			else:
				l = label()
				l2 = label()
				yield insn.Insn("IF", op.args[0], l)
				yield from compile(op.args[1], label, brk)
				yield insn.Insn("GOTO", l2)
				yield l
				yield from compile(op.args[2], label, brk)
				yield l2

		elif op.name == "WHILE":
			l = label()
			l2 = label()
			yield l
			yield insn.Insn("IF", op.args[0], l2)
			yield from compile(op.args[1], label, l2)
			yield insn.Insn("GOTO", l)
			yield l2

		elif op.name == "SWITCH":
			end = label()
			labels = [label() for _ in op.args[1]]
			yield insn.Insn(
				"SWITCH",
				op.args[0],
				[(k, l) for k, l in zip(op.args[1], labels) if k is not None],
				labels[-1] if None in op.args[1] else end
			)
			for l, code in zip(labels, op.args[1].values()):
				yield l
				yield from compile(code, label, end)
			yield end

		else:
			yield op
