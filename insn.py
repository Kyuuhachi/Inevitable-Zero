import re
import kouzou as k
import decompile
import scena

POS = "POS"|k.tuple(k.i4, k.i4, k.i4)
zstr = "zstr"|k.enc("cp932")@k.zbytes()

class Translate(str): pass
ZSTR = "ZSTR"|k.iso(Translate, str)@zstr

class Flag(int): pass
FLAG = "FLAG"|k.iso(Flag, int)@k.u2

class Char(int): pass
CHAR = "CHAR"|k.iso(Char, int)@k.u2
CHAR1 = "CHAR1"|k.iso(Char, int)@k.u1

class Party(int): pass
PARTY = "PARTY"|k.iso(Party, int)@k.u1

class Object(int): pass
OBJECT = "OBJECT"|k.iso(Object, int)@k.u1

class ResId(int):
	"""
	For resources that are loaded and unloaded. I don't know if IMG_* and EFF_*
	do use the same sets of IDs, but let's go with this for now.
	"""
RESID = "RESID"|k.iso(ResId, int)@k.u1

class Function(tuple): pass
FUNCTION = "FUNCTION"|k.iso(Function, tuple)@k.tuple(k.u1, k.u1)

class Color(int):
	def __repr__(self):
		return f"Color(0x{int(self):08X})"
COLOR = "COLOR"|k.iso(Color, int)@k.u4

class Text(Translate): pass
class TEXT(k.element):
	# Apparently '＂' can be encoded as both EE FC and FA 57, which makes it not
	# roundtrippable. That character exists in a single string, so it's not
	# worth caring about.

	FORMAT_RE = re.compile(r"\{\s*(\w+)(?:\s+(\d+))?\s*\}|(\n)")
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None

		buffer = bytearray()
		read = ctx.file.read # This saves a few percent of time
		while ch := read(1)[0]:
			if 0: pass
			elif ch == 0x01: buffer.extend(b"\n") # line
			elif ch == 0x02: buffer.extend(b"{wait}")
			elif ch == 0x03: buffer.extend(b"{page}")
			elif ch == 0x05: buffer.extend(b"{0x05}")
			elif ch == 0x06: buffer.extend(b"{0x06}")
			elif ch == 0x07: buffer.extend(b"{color %d}" % k.u1.read(ctx))
			elif ch == 0x09: buffer.extend(b"{0x09}")
			elif ch == 0x0D: buffer.extend(b"\r")
			elif ch == 0x18: buffer.extend(b"{0x18}")
			elif ch == 0x1F: buffer.extend(b"{item %d}" % k.u2.read(ctx))
			elif ch <= 0x1F: raise ValueError("%02X" % ch)
			else: buffer.append(ch)
		return Text(buffer.decode("cp932"))

	def write(self, ctx, v, inner=None):
		assert inner is None
		end = 0
		for format in self.FORMAT_RE.finditer(v):
			ctx.write(v[end:format.start()].encode("cp932"))
			tag = format.group(3) or format.group(1)
			if 0: pass
			elif tag == "\n": ctx.write(b"\x01")
			elif tag == "wait": ctx.write(b"\x02")
			elif tag == "page": ctx.write(b"\x03")
			elif tag == "0x05": ctx.write(b"\x05")
			elif tag == "0x06": ctx.write(b"\x06")
			elif tag == "color":ctx.write(b"\x07"); k.u1.write(ctx, int(format.group(2)))
			elif tag == "0x09": ctx.write(b"\x09")
			elif tag == "\r": ctx.write(b"\x0D")
			elif tag == "0x18": ctx.write(b"\x18")
			elif tag == "item": ctx.write(b"\x1F"); k.u2.write(ctx, int(format.group(2)))
			else: raise ValueError(format.group())
			end = format.end()
		ctx.write(b"\0")

	def __repr__(self):
		return "TEXT"
TEXT = TEXT()

class ADDR(k.element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		return inner.read(ctx)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		(v@inner).write(ctx, None)

	def size(self, inner):
		assert inner is not None
		return inner.size()

	def __repr__(self):
		return "ADDR"
ADDR = ADDR()@k.u4

class Insn:
	def __init__(self, name, *args):
		self.name = name
		self.args = list(args)
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
		return Insn(insn.name, *insn.args.read(ctx))

	def write(self, ctx, v, inner=None):
		assert inner is None
		assert isinstance(v, Insn)
		i = self._names[v.name]
		k.u1.write(ctx, i)
		self._options[i].args.write(ctx, v.args)

	def __repr__(self):
		return f"choice((...{len(self._options)} items))"

class script(k.element):
	class single(k.element):
		def read(self, ctx, nil_ok=False, inner=None):
			assert inner is None
			start = ctx.tell()
			v = ctx.scope["_insns"].read(ctx)
			assert isinstance(v, Insn)
			v.pos = start
			return v

		def write(self, ctx, v, inner=None):
			assert inner is None
			assert isinstance(v, Insn)
			ctx.scope["_insns"].write(ctx, v)

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
				(k.const(Insn("GOTO", start))@script.single).read(ctx, True)
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
				(k.const(Insn("GOTO", start))@script.single).write(ctx, None)
			else:
				(0@k.u1).write(ctx, None)

		def __repr__(self):
			return f"script.fork({self._loop!r})"

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		tweaks = ctx.scope.get("_geofront_tweaks", {})

		xs = []
		end = ctx.tell()
		def addr(a):
			nonlocal end
			if a in tweaks:
				a = tweaks[a]
			if a > end:
				end = a
			return a

		while True:
			op = script.single.read(ctx)
			xs.append(op)

			if op.name == "GOTO":
				op.args = (addr(op.args[0]),)
			if op.name == "IF":
				op.args = (op.args[0], addr(op.args[1]))
			if op.name == "SWITCH":
				op.args = (op.args[0], [(k, addr(v)) for k, v in op.args[1]], addr(op.args[2]))
			if op.name == "RETURN" and op.pos >= end:
				break

		# I have no idea what happened in this one.
		if tweaks.get("reorder"):
			for i, op in enumerate(xs):
				if op.name == "IF" and op.args[1] < op.pos:
					toMove = []
					while True:
						toMove.append(xs.pop(i))
						if xs[i].name == "IF": break

					for j, op2 in enumerate(xs):
						if op2.pos == op.args[1]:
							xs[j:j] = toMove
							break
					break

		return decompile.decompile(xs)

	def write(self, ctx, v, inner=None):
		assert inner is None
		for op in decompile.compile(v, lambda: k.ref(object())):
			if isinstance(op, k.ref):
				op.write(ctx, ctx.tell())
			else:
				script.single.write(ctx, op)

	def __repr__(self):
		return "script"
script = script()

class Expr(list): pass

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
	insn("FLAG", FLAG),
	insn("VAR", k.u2),
	insn("ATTR", k.u1),
	insn("CHAR_ATTR", CHAR, k.u1),
	insn("RAND"),
	insn("0x23", k.u1),
]
expr = "expr"|k.iso(Expr, list)@k.while_(lambda a: a != Insn("END"))@choice(expr_ops)

# {{{
insns_zero_pc = [
	None,
	insn("RETURN"),
	insn("IF", expr, ADDR),
	insn("GOTO", ADDR),
	insn("SWITCH", expr, k.list(k.u1)@k.tuple(k.u2, ADDR), ADDR),
	insn("CALL", FUNCTION),
	insn("NEW_SCENE", k.lazy(lambda: scena.scenaref), k.bytes(4)),
	None,
	insn("SLEEP", k.u2),
	insn("0x09", k.u4), # A set/unset pair
	insn("0x0A", k.u4),
	insn("FADE_ON", k.u4, COLOR, k.u1),
	insn("FADE_OFF", k.u4, COLOR),
	insn("0x0D"),
	insn("CROSSFADE", k.u4),
	insn("BATTLE", k.lazy(lambda: scena.battle.insn)),

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
	insn("0x1B", k.u1, FUNCTION, k.u1),
	None,
	insn("0x1D", choice({
		0: insn("0", CHAR, k.u1, k.i4, k.i4, k.i4, k.i4, k.i4, k.i4),
		# 1 does not exist
		2: insn("2", CHAR),
		3: insn("3", CHAR),
	})),
	insn("BGM_PLAY", k.bytes(3)),
	insn("0x1F"),

	insn("BGM_SET_VOLUME", k.bytes(5)),
	insn("BGM_STOP", k.u4),
	insn("BGM_WAIT"),
	insn("SOUND_PLAY", k.u2, k.const(0), k.u1, k.u2),
	insn("SOUND_STOP", k.u2),
	insn("SOUND_LOOP", k.u2, k.u1),
	insn("SOUND_POSITION", k.u2, k.list(5)@k.i4, k.u1, k.u4),
	insn("SOUND_LOAD", k.u2),
	insn("FORK_LOOP_ITER"),
	insn("QUEST", k.u2, choice({
		1: insn("TASK_SET", k.u2),
		2: insn("TASK_UNSET", k.u2),
		3: insn("FLAG_SET", k.u1),
		4: insn("FLAG_UNSET", k.u1),
	})),
	insn("QUEST_GET", k.u2, choice({
		0: insn("FLAG_GET", k.u1),
		1: insn("TASK_GET", k.u2),
	})),
	insn("QUEST_LIST", k.while_(lambda v: v != -1)@k.i2),
	insn("QUEST_BONUS_DP", k.u2, k.u2),
	None, # QUEST_BONUS_MIRA
	insn("0x2E", k.bytes(3)),
	insn("0x2F", k.bytes(2)),

	insn("PARTY_CLEAR"),
	insn("0x31", k.bytes(4)),
	insn("0x32", PARTY, k.i1, k.u2),
	None,
	None,
	insn("PARTY_CRAFT_REMOVE", PARTY, k.i2),
	insn("PARTY_CRAFT_ADD", PARTY, k.i2),
	insn("0x37"),
	insn("0x38", PARTY, k.u1, k.u1),
	insn("SEPITH_ADD", k.bytes(3)),
	insn("SEPITH_REMOVE", k.bytes(3)),
	insn("MIRA_ADD", k.bytes(2)),
	insn("MIRA_REMOVE", k.bytes(4)),
	None,
	None,
	insn("ITEM_ADD", k.u2, k.u2),

	insn("ITEM_REMOVE", k.u2, k.u2),
	insn("ITEM_GET", k.u2, k.u1),
	insn("0x42", PARTY, k.u2, k.i1),
	insn("PARTY_POSITION", PARTY),
	insn("FORK_FUNC", CHAR, k.u1, FUNCTION),
	insn("FORK_QUIT", CHAR, k.u1),
	insn("FORK", CHAR, k.u1, script.fork(False)),
	insn("FORK_LOOP", CHAR, k.u1, script.fork(True)),
	insn("FORK_AWAIT", CHAR, k.u1),
	insn("0x49"),
	insn("EVENT", FUNCTION),
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
	insn("TEXT_MESSAGE", CHAR, TEXT),
	None,
	insn("TEXT_RESET", k.bytes(1)),
	insn("MENU_TITLE", k.bytes(6), ZSTR),
	insn("TEXT_WAIT"),
	insn("0x5A"),
	insn("TEXT_SET_POS", k.i2, k.i2, k.i2, k.i2),
	insn("TEXT_TALK", CHAR, TEXT),
	insn("TEXT_TALK2", CHAR, ZSTR, TEXT),
	insn("MENU", k.u2, k.i2, k.i2, k.u1, TEXT),
	insn("MENU_WAIT", k.u2),

	insn("0x60", k.u2), # Something to do with menu
	insn("TEXT_SET_NAME", ZSTR),
	insn("0x62", CHAR),
	insn("EMOTE", CHAR, k.i4, k.u4, k.tuple(k.u1, k.u1, k.u4, k.u1)),
	insn("EMOTE_STOP", CHAR),
	insn("0x65", k.u1, k.u2),
	insn("0x66", k.u1, k.u2),
	insn("0x67", k.u2), # Cam
	insn("CAM_OFFSET", POS, k.u4),
	insn("0x69", k.bytes(3)),
	insn("0x6A", k.bytes(6)),
	insn("0x6B", CHAR),
	insn("CAM_DISTANCE", k.u4, k.u4),
	insn("CAM_ROTATE", k.i2, k.i2, k.i2, k.u4),
	insn("0x6E", k.i4, k.u4),
	insn("0x6F", k.bytes(1)),

	insn("0x70", OBJECT, k.bytes(2)),
	insn("0x71", OBJECT, k.bytes(2), k.u4, k.u4),
	insn("OBJ_FLAG_SET", OBJECT, k.u4),
	insn("OBJ_FLAG_UNSET", OBJECT, k.u4),
	insn("0x74", OBJECT, k.u2),
	None,
	insn("OBJ_SET_FRAME", OBJECT, zstr, choice({
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
	insn("0x82", k.u4, k.u4, k.u4, k.u4),
	insn("0x83", k.bytes(7)),
	None,
	insn("EFF_LOAD", RESID, zstr),
	insn("EFF_PLAY",
		k.tuple(RESID, k.i1),
		CHAR,
		*[k.i2]*10,
		k.tuple(k.u4, k.u4, k.u4), # Probably size
		*[k.i2]*7,
		k.u4,
	),
	insn("EFF_PLAY_3D",
		k.tuple(RESID, k.i1),
		CHAR1,
		zstr <<
		k.const((448, 0, 0, 0, 0, 0))@k.tuple(k.u4, k.u4, k.u4, k.u2, k.u2, k.u2) <<
		k.const((65536000, 65536000, 65536000))@POS <<
		k.const((0, 0))@k.tuple(k.u4, k.u2)
	),
	insn("EFF_STOP", k.tuple(RESID, k.i1)),
	insn("0x89", k.u2), # Used twice when drinking tomato juice in c0000 to refill everyone's CP, never otherwise
	None,
	None,
	insn("CHAR_SET_CHCP", CHAR, k.u1), # Index into CHCP array
	insn("CHAR_SET_FRAME", CHAR, k.u1),
	insn("CHAR_SET_NAME", CHAR, zstr), # Only used in debug scripts
	insn("CHAR_SET_POS", CHAR, POS, k.u2),

	insn("0x90", CHAR, POS, k.bytes(2)),
	insn("CHAR_WATCH", CHAR, CHAR, k.u2),
	insn("0x92", CHAR, k.i4, k.i4, k.u2),
	insn("CHAR_ROTATE", CHAR, k.u2, k.u2),
	insn("CHAR_IDLE", CHAR, k.tuple(k.i4, k.i4), k.tuple(k.i4, k.i4), k.u4),
	insn("0x95", CHAR, POS, k.u4, k.u1),
	insn("0x96", CHAR, POS, k.u4, k.u1),
	insn("0x97", CHAR, POS, k.u4, k.u1),
	insn("0x98", CHAR, POS, k.u4, k.u1),
	insn("CHAR_WALK_TO", CHAR, CHAR, k.u4, k.u4, k.u1),
	insn("0x9A", CHAR, k.bytes(2), k.u4, k.u4, k.bytes(1)),
	insn("0x9B", k.bytes(1), CHAR, k.bytes(11)),
	insn("0x9C", CHAR, k.bytes(20)),
	insn("0x9D", CHAR, k.i4, k.i4, k.i4, k.u4, k.u4),
	insn("0x9E", CHAR, k.i4, k.i4, k.i4, k.i4, k.bytes(2)),
	insn("0x9F", choice({
		0: insn("0", CHAR),
		1: insn("1", POS),
		2: insn("2", CHAR, k.u1, k.u4),
	})),

	insn("0xA0", CHAR, k.u2, k.u2),
	insn("CHAR_ANIMATION", CHAR, k.u2, k.lazy(lambda: scena.CHAR_ANIMATION)),
	insn("CHAR_FLAG1_SET", CHAR, k.u2),
	insn("CHAR_FLAG1_UNSET", CHAR, k.u2),
	insn("CHAR_FLAG2_SET", CHAR, k.u2),
	insn("CHAR_FLAG2_UNSET", CHAR, k.u2),
	insn("0xA6", CHAR, k.u4, k.u4, k.u4, k.u4),
	insn("CHAR_SET_COLOR", CHAR, COLOR, k.u4),
	insn("0xA8", k.bytes(9)),
	insn("FLAG_SET", FLAG),
	insn("FLAG_UNSET", FLAG),
	None,
	None,
	insn("0xAD", k.bytes(2)),
	None,
	insn("OPEN_SHOP", k.u1),

	insn("RECIPE", k.u2),
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
	insn("PARTY_SET_SBREAK", PARTY, k.u1, k.u4),
	None,

	insn("0xC0"),
	insn("0xC1", k.bytes(33)),
	None,
	insn("MINIGAME", k.u1, k.u4, k.list(7)@k.i4),
	None,
	insn("ACHIEVEMENT", k.bytes(2)),
	None,
	insn("0xC7", k.bytes(5)),
	insn("IMG_LOAD", RESID, k.u2, k.u2, k.bytes(25), zstr),
	insn("IMG_0xC9", k.tuple(RESID, k.u1), COLOR, k.i4, k.u4),
	insn("IMG_0xCA", choice({
		0: insn("0", k.tuple(RESID, k.u1)),
		1: insn("1", k.tuple(RESID, k.u1)),
	})),
	insn("0xCB", k.bytes(4), zstr, k.bytes(3)),
	None,
	None,
	insn("MENU_CUSTOM", choice({
		0: insn("INIT", RESID),
		1: insn("ADD", RESID, ZSTR),
		2: insn("FINISH", RESID, k.i4, k.u1),
		3: insn("SELECT", RESID, k.u1),
		4: insn("4", RESID, k.u1),
		5: insn("5", RESID, k.u1),
	})),
	None,

	insn("0xD0", k.u1, expr),
	insn("0xD1", k.bytes(3), zstr),
	None,
	insn("0xD3", CHAR, k.i4, k.i4, k.i4, k.u4),
	insn("LOAD_CHCP", k.lazy(lambda: scena.chcp), k.u1),
	insn("0xD5", k.u1),
	insn("0xD6", k.bytes(2)),
	insn("VITA_C7", k.bytes(2)),
	None, # VITA_C7 could be this one, need to test
	None,
	insn("0xDA", k.bytes(1)),
	insn("0xDB"),
	None,
	None,
	insn("0xDE", k.bytes(2)),
	None,

	insn("0xE0", k.bytes(1)),
	insn("0xE1", POS),
	insn("GET_NOTE_FISH", choice({
		0: insn("FISH", k.u1, choice({0: insn("COUNT"), 1: insn("MAXSIZE")})),
		1: insn("BATTLE_NOTE", choice({0: insn("MONSCOUNT")})),
	})),
	insn("0xE3", k.u1),
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
	insn("0xEE", k.u1, k.u2),
	None,

	None,
	None,
	insn("0xF2", choice({ # Not sure what this instruction does, but it's used when interacting with certain kinds of objects
		1: insn("CHEST"),
		2: insn("CHARGING_STATION"),
		3: insn("BED"),
	})),
	None,
	None,
	None,
	None,
	None,
	insn("0xF8", k.u2), # Used in the dance performance (37, 48, 60, 76, 95, 125), to unknown effect. Possibly related to starting the game directly into those scenes, from the extras menu
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

insns_zero_vita = [
	None,
	*insns_zero_pc[0x01:0x11+1], # 0x01..0x11
	None,
	*insns_zero_pc[0x14:0x17+1], # 0x13..0x16
	*insns_zero_pc[0x19:0x1B+1], # 0x17..0x19
	*insns_zero_pc[0x1D:0x32+1], # 0x1A..0x2F
	*insns_zero_pc[0x35:0x79+1], # 0x30..0x74
	*insns_zero_pc[0x7D:0x7D+1], # 0x75..0x75
	*insns_zero_pc[0x82:0x83+1], # 0x76..0x77
	*insns_zero_pc[0x85:0xBE+1], # 0x78..0xB1
	*insns_zero_pc[0xC0:0xC5+1], # 0xB2..0xB7
	*insns_zero_pc[0xC7:0xCB+1], # 0xB8..0xBC
	None,
	*insns_zero_pc[0xCE:0xD6+1], # 0xBE..0xC6
	insn("VITA_C7", k.bytes(2)), # C7; either D7 or D8
	None,
	*insns_zero_pc[0xDA:0xDE+1], # 0xC9..0xCD
	*insns_zero_pc[0xE0:0xE7+1], # 0xCE..0xD5
	None,
	*insns_zero_pc[0xEE:0xF2+1], # 0xD7..0xDB
	None,
	None,
	None,
	*insns_zero_pc[0xF8:0xF8+1], # 0xDF..0xDF
	insn("VITA_E0"),
	insn("VITA_E1", k.list(12)@k.u4),
	insn("VITA_E2", k.bytes(13), k.u4, k.u4),
	insn("VITA_E3", k.bytes(1), zstr, k.u4, k.u4, k.bytes(1)),
	insn("VITA_E4", k.bytes(3)),
	insn("VITA_E5", k.u1, k.u1, zstr, zstr, POS, POS, POS, k.u1),
	insn("VITA_E6", k.u1, k.u1, POS, POS, k.u4, k.tuple(k.u1, k.u1, k.u1, k.u1), k.u4),
	insn("VITA_E7", k.u1, k.u1),
	insn("VITA_E8", k.bytes(1)),
	insn("VITA_E9", k.u2, k.bytes(32)),
	*[None]*22,
]
assert len(insns_zero_vita) == 256, len(insns_zero_vita)
insn_zero_vita = choice(insns_zero_vita)

insns_zero_22 = [
	*insns_zero_pc[0x00:0x22+1], # 0x00..0x22
	insn("SOUND_PLAY", k.u2, k.u1, k.u2, k.u2),
	*insns_zero_pc[0x24:0xFF+1], # 0x24..0xFF
]
assert len(insns_zero_22) == 256, len(insns_zero_22)
insn_zero_22 = choice(insns_zero_22)
