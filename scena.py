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

chcp = "chcp"|k.iso(tochcp, fromchcp)@k.u4

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
	_.includes@k.list(6)@insn.scenaref,

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
			_.name@k.later("string", k.u4)@insn.zstr,
		)
	),

	_.chcp@k.list(k.u1)@k.advance("chcp")@chcp,

	_.npcs@k.list(k.u1)@k.advance("npc")@k.struct(
		_.name@k.advance("name")@insn.zstr,
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
		_.battle@insn.battle.inner,
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
		_.pos2@insn.POS,
		_.flags@k.u4,
		_.function@k.u4,
	),

	_.unk13@k.bytes(3),

	_.extra@extra@k.tuple(k.bytes(60),insn.FUNCTION,insn.FUNCTION),

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

	# This is not the same order as in the original files (those have AT rolls
	# first), but writing that order would complicate things significantly.
	k.now("battle"),
	k.now("sepith"),
	k.now("battleLayout"),
	k.now("atRoll"),

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
import shutil
from pathlib import Path

def dump(inpath, outpath, mode):
	inpath, outpath = Path(inpath), Path(outpath)
	insns = {
		"jp": insn.insn_zero_pc,
		"vita": insn.insn_zero_vita,
		"geofront": insn.insn_zero_pc,
	}[mode]
	if outpath.exists():
		shutil.rmtree(outpath)
	outpath.mkdir(parents=True, exist_ok=True)
	for file in sorted(inpath.glob("*.bin")):
		print(file)
		with file.open("rb") as f:
			params = {
				"_insns": insns,
			}
			if mode == "geofront" and file.stem in geofront_tweaks:
				params["_geofront_tweaks"] = geofront_tweaks[file.stem]
			data = k.read(scenaStruct, f, params)

		with (outpath/file.name).with_suffix(".py").open("wt") as f:
			f.write("if 0: from . import Insn\n")
			f.write("data = ")
			pprint(f, {**data, "code": CustomRepr(f"[None]*{len(data['code'])}")})
			f.write("\n")
			# Printhing functions like this makes it easier to see the indices
			# of functions, both while reading the code and in diff context lines.
			for i, func in enumerate(data["code"]):
				f.write(f"\ndata[{'code'!r}][{i!r}] = ")
				pprint(f, func)
				f.write("\n")


class CustomRepr:
	def __init__(self, repr):
		self.repr = repr
	def __repr__(self): return self.repr

def pprint(f, data, indent=0):
	if isinstance(data, dict):
		f.write("{")
		for k, v in data.items():
			f.write("\n" + "\t"*(indent+1))
			f.write(repr(k))
			f.write(": ")
			pprint(f, v, indent+1)
			f.write(",")
		if data:
			f.write("\n" + "\t"*indent)
		f.write("}")
		return

	if isinstance(data, list):
		f.write("[")
		for v in data:
			f.write("\n" + "\t"*(indent+1))
			pprint(f, v, indent+1)
			f.write(",")
		if data:
			f.write("\n" + "\t"*indent)
		f.write("]")
		return

	if isinstance(data, insn.Insn) and data.name == "IF":
		f.write(f"Insn({data.name!r}, [")
		for cond, body in data.args[0]:
			f.write("\n" + "\t"*(indent+1))
			f.write("(")
			f.write(repr(cond))
			f.write(", ")
			pprint(f, body, indent+1)
			f.write(")")
			f.write(",")
		f.write("\n" + "\t"*indent + "])")
		return

	if isinstance(data, insn.Insn) and data.name == "WHILE":
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, ")
		pprint(f, data.args[1], indent)
		f.write(")")
		return

	if isinstance(data, insn.Insn) and data.name == "SWITCH":
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, ")
		pprint(f, data.args[1], indent)
		f.write(")")
		return

	f.write(repr(data))

def __main__():
	JP = Path(...)
	EN = Path(...)
	VITA = Path(...)

	dump(VITA, Path("dump/vita"), "vita")
	dump(JP, Path("dump/jp"), "jp")
	dump(EN, Path("dump/en"), "geofront")

if __name__ == "__main__":
	__main__()
