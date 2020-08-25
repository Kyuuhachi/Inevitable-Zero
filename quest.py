import kouzou as k
from kouzou import _

zstr = k.iso(
	lambda a: a.replace("\1", "\n"),
	lambda b: b.replace("\n", "\1"),
)@k.enc("cp932")@k.zbytes()

questStruct = k.list(80)@k.struct(
	_.n@k.u1,

	k.iso( # I should add a bitstring handler
		lambda a: {"unk": bool(a&0x20), "side": bool(a&0x10), "chapter": a&0xF},
		lambda b: b["unk"]<<5 | b["side"]<<4 | b["chapter"],
	)@k.u1,

	_.mira@k.u2,
	_.bp@k.u1,
	_.unk2@k.u1,
	0@k.u2,
	_.flags@k.tuple(k.u2, k.u2),
	_.name@k.at(k.u4)@zstr,
	_.client@k.at(k.u4)@zstr,
	_.description@k.at(k.u4)@zstr,
	_.steps@k.at(k.u4)@k.list(32)@k.at(k.u4)@zstr,
)
