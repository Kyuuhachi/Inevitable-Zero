import kouzou as k
from kouzou import _, ref
from util import if_

scenaprefix = "0atcrme"
def toscenaref(n):
	if n == 0xFFFFFFFF: return None
	assert n & 0xFF000000 == 0x21000000, hex(n)
	a = (n & 0xF00000) >> 20
	b = (n & 0x0FFFF0) >> 4
	c = (n & 0x00000F) >> 0
	if c & 0xF:
		return f"{scenaprefix[a]}{b:04x}_{c:x}"
	else:
		return f"{scenaprefix[a]}{b:04x}"

def fromscenaref(n):
	if n is None: return 0xFFFFFFFF
	a = scenaprefix.find(n[0])
	b = int(n[1:5], 16)
	if len(n) == 7:
		assert n[5] == "_", n
		c = int(n[6], 16)
	else:
		assert len(n) == 5, n
		c = 0
	return 0x21000000 | a << 20 | b << 4 | c

scenaref = "scenaref"|k.iso(toscenaref, fromscenaref)@k.u4

monsterprefix = ["ms", "as", "bs"]
def tomonsterref(n):
	if n == 0x0: return None
	assert n & 0xFF000000 == 0x30000000, hex(n)
	a = (n & 0xF00000) >> 20
	b = n & 0x0FFFFF
	return f"{monsterprefix[a]}{b:05x}"

def frommonsterref(n):
	if n is None: return 0xFFFFFFFF
	a = scenaprefix.find(n[0])
	b = int(n[1:5], 16)
	if len(n) == 7:
		assert n[5] == "_", n
		c = int(n[6], 16)
	else:
		assert len(n) == 5, n
		c = 0
	return 0x30000000 | a << 20 | b << 4 | c

monsterref = "monsterref"|k.iso(tomonsterref, frommonsterref)@k.u4

#

POS = "POS"|k.tuple(k.i4, k.i4, k.i4)
zstr = "zstr"|k.enc("cp932")@k.zbytes()

class text(k.element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None

		elements = []
		segment = bytearray()
		def tag(k, v=None):
			if segment:
				elements.append(segment.decode("cp932"))
				segment.clear()
			if not elements or not isinstance(elements[-1], dict):
				elements.append({})
			elements[-1][k] = v

		while ch := ctx.read(1)[0]:
			if ch == 0x00: break
			elif ch == 0x01: tag("line")
			elif ch == 0x02: tag("wait")
			elif ch == 0x03: tag("page")
			elif ch == 0x05: tag("05")
			elif ch == 0x06: tag("06")
			elif ch == 0x07: tag("color", k.u1.read(ctx))
			elif ch == 0x09: tag("09")
			elif ch == 0x18: tag("18")
			elif ch == 0x1F: tag("item", k.u2.read(ctx))
			elif ch <= 0x1F: raise ValueError("%02X" % ch)
			elif ch == 0x23:
				i = 0
				while ch := ctx.read(1)[0]:
					if 0x30 <= ch <= 0x39:
						i = i*10+ch-0x30
					else:
						break

				ch = chr(ch)
				if 0: pass
				elif ch == "I": tag("icon", i)
				elif ch == "F": tag("img", i)
				elif ch == "x": tag("x", i)
				elif ch == "y": tag("y", i)
				elif ch == "S": tag("size", i)
				elif ch == "W": tag("speed", i)
				elif ch == "i": tag("item", i)
				elif ch == "R":
					b = bytearray()
					while ch := ctx.read(1)[0]:
						if ch == 0x23: break
						else: b.append(ch)
					tag("ruby", (i, b.decode("cp932")))
				elif ch == "P": tag("P", i) # something with position I think
				elif ch == "C": tag("color", i)
				elif ch == "A": tag("A", i)
				elif ch == "T": tag("T", i)
				elif ch == "K": tag("K", i)
				elif 1: tag(ch, i)
				else: raise ValueError(ch, i)
			else:
				segment.append(ch)

		if segment: elements.append(segment.decode("cp932"))

		return elements

	def __repr__(self):
		return "text"

text = text()

class Char(int): pass
CHAR = "CHAR"|k.iso(Char, int)@k.u2

class Function(int): pass
FUNCTION = "FUNCTION"|k.iso(Function, int)@k.u2

class Addr(int): pass
ADDR = "ADDR"|k.iso(Addr, int)@k.u4

class Insn:
	def __init__(self, name, *args):
		self.name = name
		self.args = args
		self.pos = None # Used mostly for decompilation

	def __eq__(self, other):
		return type(self) == type(other) and (self.name, self.args) == (other.name, other.args)

	def __repr__(self):
		return f"Insn({', '.join(map(repr, [self.name, *self.args]))})"

class insn: # Only to be used inside choice
	def __init__(self, name, *args):
		self.name = name
		self.args = k.tuple(*args)

	def __repr__(self):
		return f"insn({', '.join(map(repr, [self.name, *self.args._items]))})"

class choice(k.element):
	def __init__(self, options):
		if isinstance(options, list):
			options = {i: t for i, t in enumerate(options) if t is not None}

		names = {}
		for i, t in options.items():
			assert isinstance(i, int) and 0 <= i <= 255
			assert isinstance(t, insn) and t.name not in names
			names[t.name] = i
		self._options = options
		self._names = names

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		insn = self._options[k.u1.read(ctx)]
		v = Insn(insn.name, *insn.args.read(ctx))
		return v

	def write(self, ctx, v, inner=None):
		assert inner is None
		assert isinstance(v, Insn)
		i = self._names[v.name]
		k.u1.write(ctx, i)
		self._options[i].args.write(ctx, v)

	def __repr__(self):
		return f"choice({self._options!r})"

class script:
	class single(k.element):
		def read(self, ctx, nil_ok=False, inner=None):
			assert inner is None
			insn = ctx.scope["insn_type"]
			start = ctx.tell()
			v = insn.read(ctx)
			assert isinstance(v, Insn)
			v.pos = start
			return v

		def write(self, ctx, v, inner=None):
			assert inner is None
			assert isinstance(v, Insn)
			insn = ctx.scope["insn_type"]
			insn.write(ctx, v)

		def __repr__(self):
			return "script.single"
	single = single()

	class fork(k.element):
		def __init__(self, loop):
			self._loop = loop

		def read(self, ctx, nil_ok=False, inner=None):
			assert inner is None
			scrlen = k.u1.read(ctx)
			start = ctx.tell()
			end = start + scrlen

			scr = []
			while ctx.tell() != end:
				scr.append(script.single.read(ctx))

			if self._loop:
				(k.const(Insn("FORK_LOOP_ITER"))@script.single).read(ctx, True)
				(k.const(Insn("GOTO", Addr(start)))@script.single).read(ctx, True)
			else:
				(0@k.u1).read(ctx, True)
			return scr

		def write(self, ctx, v, inner=None):
			assert inner is None
			pos = ctx.tell()
			ctx.write(bytes(1))

			start = ctx.tell()
			script.write(ctx, v)
			end = ctx.tell()

			ctx.seek(pos)
			k.u1.write(ctx, end - start)
			ctx.seek(end)

			if self._loop:
				(k.const(Insn("FORK_LOOP_ITER"))@script.single).write(ctx, None)
				(k.const(Insn("GOTO", Addr(start)))@script.single).write(ctx, None)
			else:
				(0@k.u1).write(ctx, None)

		def __repr__(self):
			return f"script.fork({self._loop!r})"

	@staticmethod
	def read(ctx):
		xs = []
		end = ctx.tell()
		while True:
			op = script.single.read(ctx)
			if op.name == "GOTO": end = max(end, op.args[0])
			if op.name == "IF": end = max(end, op.args[1])
			if op.name == "SWITCH": end = max([end, *(x[1] for x in op.args[1]), op.args[2]])
			xs.append(op)
			if op.name == "RETURN" and ctx.tell() > end: break
		return xs


class battle(k.element):
	# Credits to Ouroboros for these structs
	layout = "battle.layout"|k.at(k.u2)@k.list(8)@k.struct(
		_.pos@k.tuple(k.u1, k.u1),
		_.angle@k.u2,
	)

	battleSetup = "battle.setup"|k.struct(
		_.enemies@k.list(8)@monsterref,
		_.position@layout,
		_.position2@layout,
		_.bgm@k.u2,
		_.bgm2@k.u2,
		_.atRoll@k.at(k.u4)@k.struct(
			_.none@k.u1,
			_.hp10@k.u1,
			_.hp50@k.u1,
			_.ep10@k.u1,
			_.ep50@k.u1,
			_.cp10@k.u1,
			_.cp50@k.u1,
			_.sepith@k.u1,
			_.critical@k.u1,
			_.vanish@k.u1,
			_.death@k.u1,
			_.guard@k.u1,
			_.rush@k.u1, # Is this and teamrush swapped?
			_.arts_guard@k.u1,
			_.teamrush@k.u1,
			_.unknown@k.u1,
		),
	)

	inner = "battle.inner"|k.at(k.u2)@k.struct(
		_.flags@k.u2,
		_.level@k.u2,
		_.unk@k.u1,
		_.vision@k.u1,
		_.moveRange@k.u1,
		_.canMove@k.u1,
		_.moveSpeed@k.u2,
		_.unk2@k.u2,
		_.battlefield@k.at(k.u4)@zstr,

		ref.sepith_start@k.u4,
		_.sepith@if_(0@ref.sepith_start, False)@k.at(ref.sepith_start)@k.list(7)@k.u1,

		ref.prob1@k.u1,
		ref.prob2@k.u1,
		ref.prob3@k.u1,
		ref.prob4@k.u1,
		_.prob@k.tuple(ref.prob1, ref.prob2, ref.prob3, ref.prob4),
		_.setups@k.tuple(
			if_(0@ref.prob1, False)@battleSetup,
			if_(0@ref.prob2, False)@battleSetup,
			if_(0@ref.prob3, False)@battleSetup,
			if_(0@ref.prob4, False)@battleSetup,
		),
	)

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		if k.lookahead.read(ctx, False, k.i2) == -1:
			return k.bytes(61).read(ctx)
		info = battle.inner.read(ctx)
		x = k.bytes(13).read(ctx)
		return (info, x)
battle = battle()
# def BATTLE():
# 	if f.at().i4() == -1:
# 		return Insn(k.u4, k.bytes(57))
# 	else:
# 		return Insn(None, k.u2, k.bytes(13))


expr_ops = [
	insn("CONST", k.i4),
	insn("END"),

	insn("EQ"), # ==
	insn("NE"), # !=
	insn("LT"), # <
	insn("GT"), # >
	insn("LE"), # <=
	insn("GE"), # >=

	insn("NOT"), # !
	insn("BOOL_AND"), # &&
	insn("AND"), # &
	insn("OR"), # | (bool-or is homomorphic)
	insn("ADD"), # +
	insn("SUB"), # -
	insn("NEG"), # -·
	insn("XOR"), # ^
	insn("MUL"), # *
	insn("DIV"), # /
	insn("MOD"), # %

	insn("SET"), # =
	insn("MUL_SET"), # *=
	insn("DIV_SET"), # /=
	insn("MOD_SET"), # %=
	insn("ADD_SET"), # +=
	insn("SUB_SET"), # -=
	insn("AND_SET"), # &=
	insn("XOR_SET"), # ^=
	insn("OR_SET"), # -=

	insn("EXEC", script.single),
	insn("BIT_NOT"), # ~
	insn("FLAG", k.u2),
	insn("VAR", k.u2),
	insn("ATTR", k.u1),
	insn("CHAR_ATTR", CHAR, k.u1),
	insn("RAND"),
	insn("0x23", k.u1),
]
expr = "expr"|k.while_(lambda a: a != Insn("END"))@choice(expr_ops)

insns_zero_pc = [
	None,
	insn("RETURN"),
	insn("IF", expr, ADDR),
	insn("GOTO", ADDR),
	insn("SWITCH", expr, k.list(k.u1)@k.tuple(k.u2, ADDR), ADDR),
	insn("CALL", FUNCTION), # u2
	insn("NEW_SCENE", scenaref, k.bytes(4)),
	None,
	insn("SLEEP", k.u2),
	insn("0x09", k.bytes(4)),
	insn("0x0A", k.bytes(4)),
	insn("FADE_ON", k.u4, k.bytes(4), k.u1),
	insn("FADE_OFF", k.u4, k.bytes(4)),
	insn("0x0D"),
	insn("CROSSFADE", k.u4),
	insn("BATTLE", battle),

	insn("EXIT_SET_ENABLED", k.u1, k.u1),
	insn("0x11", k.bytes(3), k.u4, k.u4, k.u4),
	None,
	None, # PLACE_SET_NAME in Sora
	insn("0x14", k.bytes(17)),
	insn("0x15", k.bytes(4)),
	insn("0x16", choice({ # Something with map, perhaps?
		2: insn("2", k.bytes(20)),
		3: insn("3", k.bytes(3)),
	})),
	insn("SAVE"),
	None,
	insn("EVENT_BEGIN", k.u1),
	insn("EVENT_END", k.u1),
	insn("0x1B", k.u2, k.u2),
	None,
	insn("0x1D", choice({
		0: insn("0", k.bytes(3), k.i4, k.i4, k.i4, k.i4, k.i4, k.i4),
		2: insn("2", k.bytes(2)),
		3: insn("3", k.bytes(2)),
	})),
	insn("BGM_PLAY", k.bytes(3)),
	insn("0x1F"),

	insn("BGM_SET_VOLUME", k.bytes(5)),
	insn("BGM_STOP", k.u4),
	insn("BGM_WAIT"),
	insn("SOUND_PLAY", k.u2, k.bytes(3)),
	insn("SOUND_STOP", k.u2),
	insn("SOUND_LOOP", k.u2, k.u1),
	insn("SOUND_POSITION", k.u2, k.list(5)@k.i4, k.u1, k.u4),
	insn("SOUND_LOAD", k.u2),
	insn("FORK_LOOP_ITER"),
	insn("QUEST", k.u2, choice({
		1: insn("TASK_UNSET", k.u2),
		2: insn("TASK_SET", k.u2),
		3: insn("FLAG_UNSET", k.u1),
		4: insn("FLAG_SET", k.u1),
	})),
	insn("QUEST_GET", k.u2, choice({
		0: insn("FLAG_GET", k.u1),
		1: insn("TASK_GET", k.u2),
	})),
	insn("QUEST_LIST", k.while_(lambda v: v != -1)@k.i2),
	insn("QUEST_BONUS_BP", k.u2, k.u2),
	None, # QUEST_BONUS_MIRA
	insn("0x2E", k.bytes(3)), # 2E..42 match Sora numerically, but the signatures don't match...
	insn("0x2F", k.bytes(2)),

	insn("PARTY_CLEAR"),
	insn("0x31", k.bytes(4)),
	insn("0x32", k.bytes(4)),
	None,
	None,
	insn("CRAFT_REMOVE", k.u1, k.i2),
	insn("CRAFT_ADD", k.u1, k.i2),
	insn("0x37"),
	insn("0x38", k.bytes(3)),
	insn("SEPITH_ADD", k.bytes(3)),
	insn("SEPITH_REMOVE", k.bytes(3)),
	insn("MIRA_ADD", k.bytes(2)),
	insn("MIRA_REMOVE", k.bytes(4)),
	None,
	None,
	insn("ITEM_ADD", k.u2, k.u2),

	insn("ITEM_REMOVE", k.bytes(4)),
	insn("ITEM_GET", k.bytes(3)),
	insn("0x42", k.u1, k.u2, k.bytes(1)),
	insn("PARTY_POSITION", k.u1),
	insn("FORK_FUNC", CHAR, k.u1, FUNCTION),
	insn("FORK_QUIT", CHAR, k.u1),
	insn("FORK", CHAR, k.u1, script.fork(False)),
	insn("FORK_LOOP", CHAR, k.u1, script.fork(True)),
	insn("FORK_AWAIT", CHAR, k.u1),
	insn("0x49"),
	insn("EVENT", k.u2),
	insn("0x4B", CHAR, k.i1),
	insn("0x4C", CHAR, k.i1),
	None,
	insn("EXPR_VAR", k.u2, expr),
	None,

	insn("EXPR_ATTR", k.u1, expr),
	None,
	insn("EXPR_CHAR_ATTR", CHAR, k.u1, expr),
	insn("TEXT_START", CHAR),
	insn("TEXT_END", CHAR),
	insn("TEXT_MESSAGE", CHAR, text),
	None,
	insn("TEXT_RESET", k.bytes(1)),
	insn("MENU_TITLE", k.bytes(6), zstr),
	insn("TEXT_WAIT"),
	insn("0x5A"),
	insn("TEXT_SET_POS", k.i2, k.i2, k.i2, k.i2),
	insn("TEXT_TALK", CHAR, text),
	insn("TEXT_TALK2", CHAR, zstr, text),
	insn("MENU", k.u2, k.i2, k.i2, k.u1, text),
	insn("MENU_WAIT", k.u2),

	insn("0x60", k.u2), # Something to do with menu
	insn("TEXT_SET_NAME", zstr),
	insn("0x62", CHAR),
	insn("EMOTE", CHAR, k.i4, k.u4, k.tuple(k.u1, k.u1, k.u4, k.u1)),
	insn("EMOTE_STOP", CHAR),
	insn("0x65", k.u1, k.u2),
	insn("0x66", k.u1, k.u2),
	insn("0x67", k.u2), # Cam
	insn("CAM_OFFSET", POS, k.u4),
	insn("0x69", k.bytes(3)),
	insn("0x6A", k.bytes(10)),
	insn("0x6B", CHAR),
	insn("CAM_DISTANCE", k.bytes(8)),
	insn("CAM_MOVE", k.bytes(10)),
	insn("0x6E", k.bytes(8)),
	insn("0x6F", k.bytes(1)),

	insn("0x70", k.u1, k.bytes(2)),
	insn("0x71", k.u1, k.bytes(2), k.u4, k.u4),
	insn("OBJ_FLAG_SET", k.u1, k.u4),
	insn("OBJ_FLAG_UNSET", k.u1, k.u4),
	insn("0x74", k.bytes(3)),
	None,
	insn("OBJ_SET_FRAME", k.u1, zstr, choice({
		0: insn("0", k.u4),
		1: insn("1", k.u4),
		2: insn("2", zstr),
		3: insn("3", k.i4), # Vita only — don't know if it works on PC
	})),
	insn("0x77", k.bytes(3)),
	insn("0x78", k.bytes(1), CHAR),
	insn("0x79", k.bytes(2)),
	None,
	None,
	None,
	insn("0x7D", k.bytes(8)),
	None,
	None,

	insn("0x80", k.bytes(4)),
	None,
	insn("0x82", k.bytes(16)),
	insn("0x83", k.bytes(7)),
	None,
	insn("EFF_LOAD", k.bytes(1), zstr),
	insn("EFF_PLAY", k.bytes(4), k.bytes(6), k.u2, k.bytes(12), k.u4, k.u4, k.u4, k.bytes(18)),
	insn("EFF_PLAY_3D", k.u2, k.u1, zstr, POS, k.u2, k.u2, k.u2, k.u4, k.u4, k.u4, k.u4, k.bytes(2)),
	insn("EFF_STOP", k.bytes(2)),
	insn("0x89", k.bytes(2)),
	None,
	None,
	insn("0x8C", CHAR, k.bytes(1)),
	insn("0x8D", k.bytes(3)),
	insn("0x8E", CHAR, zstr),
	insn("0x8F", CHAR, POS, k.u2),

	insn("0x90", CHAR, POS, k.bytes(2)),
	insn("0x91", CHAR, k.bytes(4)),
	insn("0x92", CHAR, k.i4, k.i4, k.u2),
	insn("0x93", CHAR, k.u2, k.u2),
	insn("0x94", CHAR, k.i4, k.i4, k.i4, k.i4, k.u4),
	insn("0x95", CHAR, k.i4, k.i4, k.i4, k.u4, k.u1),
	insn("0x96", CHAR, POS, k.u4, k.u1),
	insn("0x97", CHAR, k.u4, k.u4, k.u4, k.u4, k.u1),
	insn("0x98", CHAR, k.i4, k.i4, k.u4, k.u4, k.bytes(1)),
	insn("0x99", CHAR, k.bytes(11)),
	insn("0x9A", CHAR, k.bytes(2), k.u4, k.u4, k.bytes(1)),
	insn("0x9B", k.bytes(1), CHAR, k.bytes(11)),
	insn("0x9C", k.bytes(22)),
	insn("0x9D", CHAR, k.u4, k.u4, k.u4, k.u4, k.u4),
	insn("0x9E", CHAR, k.i4, k.i4, k.i4, k.i4, k.bytes(2)),
	insn("0x9F", choice({
		0: insn("0", CHAR),
		1: insn("1", POS),
		2: insn("2", CHAR, k.u1, k.u4),
	})),

	insn("0xA0", k.bytes(6)),
	insn("0xA1", CHAR, k.u2, k.bytes(k.u1)),
	insn("0xA2", CHAR, k.bytes(2)),
	insn("0xA3", CHAR, k.bytes(2)),
	insn("0xA4", CHAR, k.bytes(2)),
	insn("0xA5", CHAR, k.bytes(2)),
	insn("0xA6", CHAR, k.u4, k.u4, k.u4, k.u4),
	insn("0xA7", k.bytes(10)),
	insn("0xA8", k.bytes(9)),
	insn("0xA9", k.u2),
	insn("0xAA", k.u2),
	None,
	None,
	insn("0xAD", k.bytes(2)),
	None,
	insn("0xAF", k.bytes(1)),

	insn("0xB0", k.bytes(2)),
	insn("0xB1", k.bytes(1)),
	None,
	None,
	None,
	insn("0xB5", k.bytes(4)),
	insn("0xB6", k.u1, zstr, k.u4),
	insn("0xB7", k.bytes(1)),
	insn("0xB8", k.u2, k.u2),
	None,
	insn("0xBA", k.u1),
	insn("0xBB", k.bytes(4)),
	None,
	insn("0xBD", k.bytes(2)),
	insn("0xBE", k.bytes(2), k.u4),
	None,

	insn("0xC0"),
	insn("0xC1", k.bytes(33)),
	None,
	insn("MINIGAME", k.u1, k.u4, k.list(7)@k.i4),
	None,
	insn("ACHIEVEMENT", k.bytes(2)),
	None,
	insn("0xC7", k.bytes(5)),
	insn("0xC8", k.bytes(30), zstr),
	insn("0xC9", k.bytes(2), k.i4, k.u4, k.u4),
	insn("0xCA", k.bytes(3)),
	insn("0xCB", k.bytes(4), zstr, k.bytes(3)),
	None,
	None,
	insn("0xCE", choice({
		0: insn("0", k.bytes(1)),
		1: insn("1", k.bytes(1), zstr),
		2: insn("2", k.bytes(6)),
		3: insn("3", k.bytes(2)),
		4: insn("4", k.bytes(2)),
		5: insn("5", k.bytes(2)),
	})),
	None,

	insn("0xD0", k.u1, expr),
	insn("0xD1", k.bytes(3), zstr),
	None,
	insn("0xD3", CHAR, k.bytes(16)),
	insn("0xD4", k.bytes(5)),
	insn("0xD5", k.bytes(1)),
	insn("0xD6", k.bytes(2)),
	None,
	None,
	None,
	insn("0xDA", k.bytes(1)),
	insn("0xDB"),
	None,
	None,
	insn("0xDE", k.bytes(2)),
	None,

	insn("0xE0", k.bytes(1)),
	insn("0xE1", POS),
	insn("0xE2", choice({
		0: insn("0", k.bytes(2)),
		1: insn("1", k.bytes(1)),
	})),
	insn("0xE3", k.bytes(1)),
	None,
	insn("0xE5"),
	insn("0xE6"),
	insn("0xE7"),
	insn("0xE8", k.bytes(2), POS),
	None,
	None,
	None,
	None,
	None,
	insn("0xEE", k.bytes(3)),
	None,

	None,
	None,
	insn("0xF2", k.bytes(1)),
	None,
	None,
	None,
	None,
	None,
	insn("0xF8", k.bytes(2)),
	None,
	None,
	None,
	None,
	None,
	None,
	None,
]
assert len(insns_zero_pc) == 256
insn_zero_pc = choice(insns_zero_pc)
