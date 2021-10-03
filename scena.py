import kouzou as k
from kouzou import _, ref
import insn

###

chcp_types = {
	7: "chr/ch",
	8: "apl/ch",
	9: "monster/ch",
}
def tochcp(n):
	if n == 0:
		return None
	a, b = n >> 20, n & 0xFFFFF
	return f"{chcp_types[a]}{b:05x}"

def fromchcp(n):
	if n is None:
		return 0
	for i, v in chcp_types.items():
		if n.startswith(v):
			return i << 20 | int(n[len(v):], 16)
chcp = "chcp"|k.iso(tochcp, fromchcp)@k.u4

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
	if n == 0: return None
	assert n & 0xFF000000 == 0x30000000, hex(n)
	a = (n & 0xF00000) >> 20
	b = n & 0x0FFFFF
	return f"{monsterprefix[a]}{b:05x}"

def frommonsterref(n):
	if n is None: return 0
	for i, v in enumerate(monsterprefix):
		if n.startswith(v):
			return 0x30000000 | i << 20 | int(n[len(v):], 16)
monsterref = "monsterref"|k.iso(tomonsterref, frommonsterref)@k.u4

class battle:
	# Credits to Ouroboros for these structs
	class sepith(k.element):
		def read(self, ctx, nil_ok=False, inner=None):
			assert inner is not None
			if k.lookahead.read(ctx, False, k.u4) == 0:
				k.u4.read(ctx)
				return None
			else:
				return inner.read(ctx)

		def write(self, ctx, v, inner=None):
			assert inner is not None
			if v is None:
				k.u4.write(ctx, 0)
			else:
				inner.write(ctx, v)

		def __repr__(self):
			return "battle.sepith"
	sepith = sepith()

	class setups(k.element):
		def read(self, ctx, nil_ok=False, inner=None):
			assert inner is not None
			probs = list(ctx.read(4))
			while probs and not probs[-1]: probs.pop()
			assert 0 not in probs, probs
			return [(p, inner.read(ctx)) for p in probs]

		def write(self, ctx, v, inner=None):
			assert inner is not None
			probs = [p for p, _ in v]
			assert len(probs) <= 4, probs
			assert 0 not in probs, probs
			while len(probs) < 4: probs.append(0)
			ctx.write(bytes(probs))
			for _, v in v:
				inner.write(ctx, v)

		def __repr__(self):
			return "battle.setups"
	setups = setups()

	class now(k.element):
		def read(self, ctx, nil_ok=False, inner=None):
			assert inner is None
			assert nil_ok
			return k.NIL

		def write(self, ctx, v, inner=None):
			assert inner is None

			def find_battles(code):
				for op in code:
					if op.name == "BATTLE" and not op.args[0][0]:
						yield op.args[0][1]
					if op.name == "IF":
						for _, body in op.args[0]:
							yield from find_battles(body)
					if op.name == "WHILE":
						yield from find_battles(op.args[1])
					if op.name == "SWITCH":
						for _, body in op.args[1].items():
							yield from find_battles(body)
			battles = [m["battle"] for m in v["monsters"]]
			for func in v["code"]:
				battles.extend(find_battles(func))

			def write(struct, values):
				vals = {}
				for item in values:
					r = repr(item)
					if r not in vals:
						vals[r] = ctx.tell()
						struct.write(ctx, item)
				return vals

			ctx.root["_battles"] = {}
			ctx.root["_battles"]["atRoll"] = write(battle._atRoll, [s["atRoll"] for b in battles for _, s in b["setups"]])
			ctx.root["_battles"]["sepith"] = write(battle._sepith, [b["sepith"] for b in battles if b["sepith"] is not None])
			ctx.root["_battles"]["layout"] = write(battle._layout, [
				tuple(en[k] for en in s["enemies"])
				for b in battles
				for _, s in b["setups"]
				for k in [1, 2]
			])
			ctx.root["_battles"]["battle"] = write(battle.struct, battles)

		def __repr__(self):
			return "battle.now"
	now = now()

	class later(k.later):
		def write(self, ctx, v, inner=None):
			assert inner is not None
			ctx.later(ctx.tell(), self._pos, lambda: ctx.root["_battles"][self._key][repr(v)])
			ctx.write(bytes(self._pos.size()))

		def __repr__(self):
			return f"battle.later({self._key!r}, {self._pos!r})"

	_atRoll = k.struct(
		_.none@k.u1,
		_.hp10@k.u1,
		_.hp50@k.u1,
		_.ep10@k.u1,
		_.ep50@k.u1,
		_.cp10@k.u1,
		_.cp50@k.u1,
		_.sepith_up@k.u1,
		_.critical@k.u1,
		_.vanish@k.u1,
		_.death@k.u1,
		_.guard@k.u1,
		_.rush@k.u1,
		_.arts_guard@k.u1,
		_.teamrush@k.u1,
		_.unknown@k.u1,
	)

	_layout = k.list(8)@k.tuple(k.u1, k.u1, k.u2)
	_sepith = k.iso(tuple, list)@k.list(7)@k.u1

	struct = "battle.struct"|k.struct(
		_.flags@k.u2,
		_.level@k.u2,
		_.unk@k.u1,
		_.vision@k.u1,
		_.moveRange@k.u1,
		_.canMove@k.u1,
		_.moveSpeed@k.u2,
		_.unk2@k.u2,
		_.battlefield@k.later("string", k.u4)@insn.zstr,
		_.sepith@sepith@later("sepith", k.u4)@_sepith,
		_.setups@setups@k.struct(
			_.enemies@k.iso(lambda a: list(zip(*a)), lambda b: list(zip(*b)))@k.tuple(
				k.list(8)@monsterref,
				later("layout", k.u2)@_layout,
				later("layout", k.u2)@_layout,
			),
			_.bgm@k.u2,
			_.bgm2@k.u2,
			_.atRoll@later("atRoll", k.u4)@_atRoll,
		),
	)

	class insn(k.element):
		npc_battle = k.tuple(
			True,
			(-1@k.i4) >>
			k.u2, # special mode
			k.bytes(3), # Always 20 30 00 if special mode is nonzero
			k.iso(tuple, list)@k.list(4)@monsterref,
			k.iso(tuple, list)@k.list(4)@monsterref,
			bytes(16)@k.bytes(16) >>
			k.u2, k.u2,
		)

		standard_battle = k.tuple(
			False,
			k.lazy(lambda: battle.later("battle", k.u2)@battle.struct),
			0@k.u2 >>
			k.u2, # special mode
			k.bytes(3), # Always 20 30 00 if special mode is nonzero
			k.u2, k.u2
			<< 255@k.u2,
		)

		def read(self, ctx, nil_ok=False, inner=None):
			assert inner is None
			if k.lookahead.read(ctx, False, k.i2) == -1:
				return self.npc_battle.read(ctx)
			else:
				return self.standard_battle.read(ctx)

		def write(self, ctx, v, inner=None):
			assert inner is None
			if v[0]:
				self.npc_battle.write(ctx, v)
			else:
				self.standard_battle.write(ctx, v)

		def __repr__(self):
			return "battle.insn"
	insn = insn()

class CHAR_ANIMATION(k.element):
	def read(self, ctx, nil_ok=False, inner=None):
		length = k.u1.read(ctx)
		if length == 0:
			(0@k.u1).read(ctx, True)
		return list(ctx.read(length))

	def write(self, ctx, v, inner=None):
		assert inner is None
		k.u1.write(ctx, len(v))
		ctx.write(bytes(v) or b"\0")

	def __repr__(self):
		return "CHAR_ANIMATION"
CHAR_ANIMATION = CHAR_ANIMATION()

class extra(k.element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		if ctx.scope["func_start"] == ctx.tell():
			return None
		return inner.read(ctx)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		if v is not None:
			inner.write(ctx, v)

	def __repr__(self):
		return "extra"
extra = extra()

class labels(k.element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		return inner.read(ctx)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		if not v:
			ctx.later(ctx.tell(), k.u2, lambda: 0)
		inner.write(ctx, v)

	def __repr__(self):
		return "labels"
labels = labels()

scenaStruct = k.struct(
	_.name1@k.enc("cp932")@k.fbytes(10),
	_.name2@k.enc("cp932")@k.fbytes(10),

	_.location@k.u2,
	_.bgm@k.u2,
	_.flags@k.u4,
	_.includes@k.list(6)@scenaref,

	k.cursor("name", k.u4),
	_.name3@k.advance("name")@insn.zstr,

	k.cursor("chcp", k.u2),
	k.cursor("npc", k.u2),
	k.cursor("monster", k.u2),
	k.cursor("trigger", k.u2),
	k.cursor("object", k.u2),

	ref.func_start@k.u2,
	ref.func_count@k.div(4)@k.u2,

	ref.anim_start@k.u2,
	# I'll just assume that it's animations all the way from anim_start to
	# func_start. The 12 is the size of the anim struct.
	ref.anim_count@k.div(12)@k.add(k.div(-1)@ref.anim_start)@ref.func_start,

	_.labels@labels@(
		k.cursor("label", k.u2) >>
		k.list(k.u2)@k.advance("label")@k.struct(
			_.pos@k.tuple(k.f4, k.f4, k.f4),
			_.unk@k.bytes(4),
			_.name@k.later("string", k.u4)@insn.ZSTR,
		)
	),

	_.chcp@k.list(k.u1)@k.advance("chcp")@chcp,

	_.npcs@k.list(k.u1)@k.advance("npc")@k.struct(
		_.name@k.advance("name")@insn.ZSTR,
		_.pos@insn.POS,
		_.angle@k.u2,
		_._1@k.bytes(8),
		_.function@insn.FUNCTION,
		_._2@k.bytes(4),
	),

	_.monsters@k.list(k.u1)@k.advance("monster")@k.struct(
		_.pos@insn.POS,
		_.angle@k.u2,
		_.unk1@k.u2,
		_.battle@battle.later("battle", k.u2)@battle.struct,
		_.flag@k.u2,
		_.chcpIdx@k.u2,
		0xFFFF@k.u2,
		_.standAnim@k.u4,
		_.moveAnim@k.u4
	),

	_.triggers@k.list(k.u1)@k.advance("trigger")@k.struct(
		_.pos@k.tuple(k.f4, k.f4, k.f4),
		_.range@k.f4,
		_.transform@k.list(16)@k.f4,
		_._1@k.bytes(3),
		_.function@insn.FUNCTION,
		_._2@k.bytes(11),
	),

	_.objects@k.list(k.u1)@k.advance("object")@k.struct(
		_.pos@insn.POS,
		_.range@k.u4,
		_.bubble_pos@insn.POS,
		_._1@k.bytes(3),
		_.function@insn.FUNCTION,
		_._2@k.bytes(3),
	),

	_.unk13@k.bytes(3),

	_.extra@extra@k.tuple(k.bytes(60), insn.FUNCTION, insn.FUNCTION),

	_.code@k.later("functable", ref.func_start)@k.list(ref.func_count)@k.later("script", k.u4)@insn.script,

	_.anim@k.later("anim", ref.anim_start)@k.list(ref.anim_count)@k.struct(
		_.speed@k.u2,
		_._@k.u1,
		_.count@k.u1,
		_.frames@k.list(8)@k.u1,
	),

	k.nowC("label"),
	k.nowC("trigger"),
	k.nowC("object"),
	k.nowC("chcp"),
	k.nowC("npc"),
	k.nowC("monster"),

	battle.now,

	k.now("anim"),
	k.now("functable"),
	k.now("script"),
	k.nowC("name"),
	k.now("string"),
)

geofront_tweaks = { # For Geofront v1.0.2
	"a0000": {0x0183B: 0x01892},
	"c0110": {0x24D56: 0x2F578},
	"c011b": {0x16924: 0x1C789},
	"c011c": {0x1266A: 0x16349},
	"c1130": {"reorder": True},
	"m1080": {0x0069B: 0x00696},
	"m3033": {0x01361: 0x01449},
	"t1210": {0x00302: 0x002f8},
}
