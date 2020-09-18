import kouzou as k
from kouzou import _, ref
from collections import defaultdict

zstr = k.iso(
	lambda a: a.replace("\1", "\n"),
	lambda b: b.replace("\n", "\1"),
)@k.enc("cp932")@k.zbytes()

questStruct = k.while_(lambda x: x["n"] != 0xFF)@k.struct(
	ref.n@k.u1,
	_.n@ref.n,

	k.iso( # I should add a bitstring handler
		lambda a: {"unk": bool(a&0x20), "side": bool(a&0x10), "chapter": a&0xF},
		lambda b: b["unk"]<<5 | b["side"]<<4 | b["chapter"],
	)@k.u1,

	_.mira@k.u2,
	_.bp@k.u1,
	_.unk2@k.u1,
	0@k.u2,
	_.flags@k.tuple(k.u2, k.u2),
	_.name@k.later("name", k.u4)@zstr,
	_.client@k.later("name", k.u4)@zstr,
	_.description@k.later("name", k.u4)@zstr,
	_.steps@k.later("steps", k.u4)@k.list(k.switch(ref.n,
		defaultdict(lambda: 32, { 0: 2, 0xFF: 1})
	))@k.later("step", k.u4)@zstr,
) << k.now("steps") << k.now("name") << k.now("step")
