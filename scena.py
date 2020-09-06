import kouzou as k
from kouzou import _, ref
from util import if_
import insn

###

chcp_types = {
	7: "chr",
	8: "apl",
	9: "monster",
}
def tochcp(n):
	if n == 0:
		return None
	a, b = n >> 20, n & 0xFFFFFF
	return f"{chcp_types[a]}/ch{b:05x}"

# TODO
chcp = k.iso(tochcp, ...)@k.u4

###

class code(k.element):
	def __init__(self, funcs, insns):
		self._funcs = funcs
		self._insns = insns

	def read(self, ctx, nil_ok=False, inner=None):
		assert inner is None
		ctx.scope["insn_type"] = self._insns

		funcs = []
		for a in self._funcs.read(ctx):
			ctx.seek(a)
			funcs.append(insn.script.read(ctx))
		return funcs

	write = ...

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
	ref.funcs@k.at(ref.func_start)@k.list(ref.func_count)@insn.ADDR,

	ref.anim_start@k.u2,
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
		_.pos@k.tuple(k.i4, k.i4, k.i4),
		_.angle@k.u2,
		_._@k.bytes(2*7), # A function or two in here
	),

	_.monsters@k.at(ref.monster_start)@k.list(ref.monster_count)@k.struct(
		_.pos@k.tuple(k.i4, k.i4, k.i4),
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
		_._@k.numpy((4, 4), "f4"),
		_._2@k.bytes(16), # Must be a function in here, at least
	),

	_.objects@k.at(ref.object_start)@k.list(ref.object_count)@k.struct(
		_.pos@k.tuple(k.i4, k.i4, k.i4),
		_.range@k.u4,
		_.pos2@k.tuple(k.i4, k.i4, k.i4),
		_.flags@k.u4,
		_.function@k.u4,
	),

	_.extra@if_(84@ref.func_start, False)@k.bytes(64),

	_.anim@k.at(ref.anim_start)@k.list(ref.anim_count)@k.struct(
		_.speed@k.u2,
		_._@k.u1,
		_.count@k.u1,
		_.frames@k.list(8)@k.u1,
	),

	_.code@code(ref.funcs, insn.insn_zero_pc),
)

def __main__():
	import pathlib
	JP = pathlib.Path(...)
	EN = pathlib.Path(...)
	VITA = pathlib.Path(...)

	for game, file in [("en", EN), ("jp", JP)]:
		print(file)
		for fn in sorted(file.glob("*.bin")):
			with fn.open("rb") as f:
				c = k.ReadContext(f)
				c.scope["_game"] = game
				c.scope["_filename"] = fn.stem
				scenaStruct.read(c)

if __name__ == "__main__":
	__main__()
