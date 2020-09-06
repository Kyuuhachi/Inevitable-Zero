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
	a, b = n >> 20, n & 0xFFFFFF
	return f"{chcp_types[a]}{b:05x}"

def fromchcp(n):
	if n is None:
		return 0
	for i, v in chcp_types.items():
		if n.startswith(v):
			return i << 20 | int(n[len(v):], 16)

class extra(k.element):
	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is not None
		if ctx.scope["func_start"] == ctx.tell():
			return None
		return inner.read(ctx)

	def write(self, ctx, v, inner=None):
		assert inner is not None
		if v is not None:
			pos = ctx.tell()
			inner.write(ctx, v)
			@ctx.later
			def ensure_extra():
				assert ctx.scope["func_start"] != pos
			ensure_extra.__qualname__ = repr(self@inner)

	def __repr__(self):
		return "extra"
extra = extra()

# TODO
chcp = "chcp"|k.iso(tochcp, fromchcp)@k.u4

scenaStruct = k.struct(
	_.name1@k.enc("cp932")@k.fbytes(10),
	_.name2@k.enc("cp932")@k.fbytes(10),

	_.location@k.u2,
	_.bgm@k.u2,
	_.flags@k.u4,

	_.includes@k.list(6)@insn.scenaref,
	_.name3@k.at(k.u4)@insn.zstr,

	ref.chcp_start@k.u2,
	ref.npc_start@k.u2,
	ref.monster_start@k.u2,
	ref.trigger_start@k.u2,
	ref.object_start@k.u2,

	ref.func_start@k.u2,
	ref.func_count@k.div(4)@k.u2,

	ref.anim_start@k.u2,
	# I'll just assume that it's animations all the way from anim_start to
	# func_start. The 12 is the size of the anim struct.
	ref.anim_count@k.div(12)@k.add(k.div(-1)@ref.anim_start)@ref.func_start,

	ref.label_start@k.u2,
	ref.label_count@k.u2,
	_.labels@k.at(ref.label_start)@k.list(ref.label_count)@k.struct(
		_.pos@k.tuple(k.f4, k.f4, k.f4),
		_.unk@k.bytes(4),
		_.name@k.at(k.u4)@insn.zstr,
	),

	ref.chcp_count@k.u1,
	ref.npc_count@k.u1,
	ref.monster_count@k.u1,
	ref.trigger_count@k.u1,
	ref.object_count@k.u1,

	_.unk13@k.bytes(3),

	_.chcp@k.at(ref.chcp_start)@k.list(ref.chcp_count)@chcp,

	_.npcs@k.at(ref.npc_start)@k.list(ref.npc_count)@k.struct(
		_.pos@insn.POS,
		_.angle@k.u2,
		_._@k.bytes(2*7), # A function or two in here
	),

	_.monsters@k.at(ref.monster_start)@k.list(ref.monster_count)@k.struct(
		_.pos@insn.POS,
		_.angle@k.u2,
		_.unk1@k.u2,
		_.battle@insn.battle.inner,
		_.flag@k.u2,
		_.chcpIdx@k.u2,
		0xFFFF@k.u2,
		_.standAnim@k.u4,
		_.moveAnim@k.u4
	),

	_.triggers@k.at(ref.trigger_start)@k.list(ref.trigger_count)@k.struct(
		_.pos@k.tuple(k.f4, k.f4, k.f4),
		_.range@k.f4,
		_._@k.list(4)@k.list(4)@k.f4,
		_._2@k.bytes(16), # Must be a function in here, at least
	),

	_.objects@k.at(ref.object_start)@k.list(ref.object_count)@k.struct(
		_.pos@insn.POS,
		_.range@k.u4,
		_.pos2@insn.POS,
		_.flags@k.u4,
		_.function@k.u4,
	),

	_.extra@extra@k.bytes(64),

	_.code@k.at(ref.func_start)@k.list(ref.func_count)@k.at(k.u4)@insn.script,

	_.anim@k.at(ref.anim_start)@k.list(ref.anim_count)@k.struct(
		_.speed@k.u2,
		_._@k.u1,
		_.count@k.u1,
		_.frames@k.list(8)@k.u1,
	),
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

def __main__():
	import pathlib
	import util
	import io
	JP = pathlib.Path(...)
	EN = pathlib.Path(...)
	VITA = pathlib.Path(...)

	for game, file in [("geofront", EN), ("jp", JP)]:
		print(file)
		for fn in sorted(file.glob("c0250.bin")):
			with fn.open("rb") as f:
				sc = {}
				sc["_insns"] = insn.insn_zero_pc
				if game == "geofront" and fn.stem in geofront_tweaks:
					sc["_geofront_tweaks"] = geofront_tweaks[fn.stem]
				v = k.read(scenaStruct, f, dict(sc))

				try:
					f = io.BytesIO()
					k.write(scenaStruct, f, v, dict(sc))
					f.seek(0)
					v2 = k.read(scenaStruct, f, dict(sc))
					for a, b in util.diff(v.code, v2.code):
						print(repr(a), repr(b))
					print(v == v2)
				except Exception:
					import traceback
					print(fn)
					traceback.print_exc()

if __name__ == "__main__":
	__main__()
