import shutil
from pathlib import Path
import argparse
from contextlib import contextmanager

import kouzou
import scena
import quest
import insn
import dump
from insn import Insn
import translate

class Context:
	def __init__(self, vitapath, pcpath, outpath, is_geofront=None):
		if is_geofront is None:
			is_geofront = pcpath.name == "data_en"
		self.is_geofront = is_geofront

		self.vitapath = vitapath
		self.vita_scripts = {}
		with (vitapath/"text/t_quest._dt").open("rb") as f:
			self.vita_quests = kouzou.read(quest.questStruct, f)

		self.pcpath = pcpath
		self.pc_scripts = {}
		with (pcpath/"text/t_quest._dt").open("rb") as f:
			self.pc_quests = kouzou.read(quest.questStruct, f)

		self.outpath = outpath

	def save(self):
		with (self.outpath/"text/t_quest._dt").open("wb") as f:
			kouzou.write(quest.questStruct, f, self.pc_quests)

		for name, script in self.pc_scripts.items():
			with (self.outpath/"scena"/name).with_suffix(".bin").open("wb") as f:
				params = { "_insns": insn.insn_zero_pc }
				kouzou.write(scena.scenaStruct, f, script, params)

	def _get_vita(self, name):
		if name not in self.vita_scripts:
			with (self.vitapath/"scena"/name).with_suffix(".bin").open("rb") as f:
				params = { "_insns": insn.insn_zero_vita }
				self.vita_scripts[name] = kouzou.read(scena.scenaStruct, f, params)
		return self.vita_scripts[name]

	def _get_pc(self, name):
		if name not in self.pc_scripts:
			with (self.pcpath/"scena"/name).with_suffix(".bin").open("rb") as f:
				params = { "_insns": insn.insn_zero_pc }
				if self.is_geofront and name in scena.geofront_tweaks:
					params["_geofront_tweaks"] = scena.geofront_tweaks[name]
				self.pc_scripts[name] = do_transform(
					kouzou.read(scena.scenaStruct, f, params),
					{ "translate": True },
				)
		return self.pc_scripts[name]

	def copy(self, name, translation=None):
		assert not (self.pcpath/name).with_suffix(".bin").exists()
		self.pc_scripts[name] = self._get_vita(name)
		self._do_translate(name, translation)

	@contextmanager
	def get(self, name, translation=None):
		yield self._get_vita(name), self._get_pc(name)
		self._do_translate(name, translation)

	def _do_translate(self, name, translation):
		if translation is None:
			translation = translate.null_translator()
		if self.is_geofront:
			self.pc_scripts[name] = do_transform(
				self.pc_scripts[name],
				{ "translate": translation },
			)

	def copy_quest(self, n, translation):
		self.pc_quests[n] = {
			**self.vita_quests[n],
			"name": translation.translate(self.vita_quests[n]["name"]),
			"client": translation.translate(self.vita_quests[n]["client"]),
			"description": translation.translate(self.vita_quests[n]["description"]),
			"steps": [
				translation.translate(vs) if vs != ps else ps
				for vs, ps in zip(self.vita_quests[n]["steps"], self.pc_quests[n]["steps"])
			],
		}


def patch_furniture_minigames(ctx):
	# There are minigames on some room furniture in the Vita version, let's
	# import that. Since the minigames don't exist on PC, it doesn't quite work.
	tr = translate.translator("furniture_minigames")
	for file, funcs in [
			("c0110_1", (33, 35, 38)),
			("c011b", (73, 75, 78)),
			("c011c", (58, 60, 63)),
	]:
		tr.pos = 0
		with ctx.get(file, tr) as (vita, pc):
			for func in funcs:
				vita_, pc_ = vita.code[func], pc.code[func]
				assert vita_[10] == pc_[10]
				pc_[11:11] = vita_[11:17]
				assert vita_[18] == pc_[18]
				assert vita_[22] == pc_[22]
				assert vita_[23].name == "IF"
				pc_.insert(23, vita_[23])

def patch_quests(ctx):
	for file, func in [
			("c0110", 3),
			("c011c", 8),
	]:
		with ctx.get(file) as (vita, pc):
			vita_, pc_ = get(vita, pc, "code", func, "@WHILE", 1, "@SWITCH", 1)
			pc_[0] = vita_[0]
	
	# 54, 57
	with ctx.get("c0110") as (vita, pc):
		vita_, pc_ = vita.code[46], pc.code[46]
		assert pc_[-6:-4] == vita_[-8:-6]
		pc_[-4:-4] = vita_[-6:-4]

	# 56, 58
	with ctx.get("c0400") as (vita, pc):
		copy_clause(vita, pc, 49, pc.code[49].index(Insn('EXPR_VAR', 3, [Insn('CONST', 0), Insn('SET'), Insn('END')]))+9)
		copy_clause(vita, pc, 49, pc.code[49].index(Insn('EXPR_VAR', 3, [Insn('CONST', 0), Insn('SET'), Insn('END')]))+10)
		copy_clause(vita, pc, 49, pc.code[49].index(Insn('ITEM_REMOVE', 805, 1))+8)
		copy_clause(vita, pc, 49, pc.code[49].index(Insn('ITEM_REMOVE', 805, 1))+9)

	quest54(ctx)
	quest55(ctx)
	quest56(ctx)
	quest57(ctx)
	quest58(ctx)

def quest54(ctx):
	tr = translate.translator("quest54")
	ctx.copy_quest(54, tr)

	with ctx.get("t0500") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 13, "@IF", 0, 0)

	with ctx.get("t0520") as (vita, pc):
		pc.includes = vita.includes
		path1 = [
			"@IF", None,
			"@WHILE", 1,
			"@IF:1", [Insn('VAR', 0), Insn('CONST', 0), Insn('EQ'), Insn('END')],
		]
		vita = transform_funcs(vita, {
			6:  extract_func(pc, 5, *path1, "@IF", [Insn('FLAG', 1536), Insn('END')]),
			7:  extract_func(pc, 5, *path1, "@IF", [Insn('FLAG', 1544), Insn('END')]),
			8:  extract_func(pc, 5, *path1, "@IF", [Insn('FLAG', 1547), Insn('END')]),
			10: extract_func(pc, 6, "@IF", [Insn('FLAG', 1536), Insn('END')]),
			11: extract_func(pc, 6, "@IF", [Insn('FLAG', 1544), Insn('END')]),
			12: extract_func(pc, 6, "@IF", [Insn('FLAG', 1547), Insn('END')]),
		}, include=0)
		copy_clause(vita, pc, 5, *path1, "@IF", 0, 0)
		copy_clause(vita, pc, 6, "@IF", 0, 0)

	ctx.copy("t0520_1", tr)

def quest55(ctx):
	tr = translate.translator("quest55")
	ctx.copy_quest(55, tr)

	with ctx.get("t1000") as (vita, pc):
		pc.includes = vita.includes
		pc.chcp = vita.chcp
		vita = transform_funcs(vita, {
			17: copy(pc.code, vita.code[17]),
		}, include=0)
		vita = transform_npcs(vita, {
			13: copy(pc.npcs, vita.npcs[13]),
		})
		copy_clause(vita, pc, 1, 1)

	with ctx.get("t1010") as (vita, pc):
		pc.includes = vita.includes
		pc.chcp = vita.chcp
		vita = transform_npcs(vita, {
			2: copy(pc.npcs, vita.npcs[2]),
		})
		# XXX Cabilan and Lughman don't have flag 0x0080 in Vita
		pc.code[4][-3:-1] = vita.code[4][-2:-1]

	with ctx.get("t1020") as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			13: copy(pc.code, vita.code[13]),
			3: copy(pc.code, vita.code[3]),
		}, include=0)
		vita = transform_npcs(vita, {
			6: copy(pc.npcs, vita.npcs[6]),
		})
		copy_clause(vita, pc, 3, -2)

	with ctx.get("t1030") as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			4: extract_func(pc, 3, "@IF", [Insn('FLAG', 1312), Insn('END')]),
			5: extract_func(pc, 3, "@IF", [Insn('FLAG', 1318), Insn('END')]),
		}, include=0)
		copy_clause(vita, pc, 1, "@IF:0", [Insn('FLAG', 1318), Insn('END')], 0)
		copy_condition(vita, pc, 1, "@IF:0", [Insn('FLAG', 1312), Insn('END')], 2)
		copy_clause(vita, pc, 1, -2)
		copy_clause(vita, pc, 3, "@IF", 0, 0)
		copy_clause(vita, pc, 5, "@IF", 0, 0)

	ctx.copy("t1030_1", tr)

	with ctx.get("t1050") as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			12: copy(pc.code, vita.code[12]),
		}, include=0)
		for flag in 1312, 1317, 1318:
			copy_clause(vita, pc, 10, "@IF", [Insn('FLAG', flag), Insn('END')], 0)
			copy_condition(vita, pc, 10, "@IF", [Insn('FLAG', flag), Insn('END')], 1)

	with ctx.get("t105b") as (vita, pc):
		pc.code[14].insert(-4, vita.code[14][-5])

def quest56(ctx):
	tr = translate.translator("quest56")
	ctx.copy_quest(56, tr)

	with ctx.get("c0000") as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			55: copy(pc.code, vita.code[55]),
			60: copy(pc.code, vita.code[60]),
		}, include=0)
		copy_condition(vita, pc, 6, "@IF", [Insn('FLAG', 1055), Insn('END')], 0)
		copy_clause(vita, pc, 6, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	with ctx.get("c0100") as (vita, pc):
		pc.includes = vita.includes

	with ctx.get("c0100_1") as (vita, pc):
		copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	with ctx.get("c1100") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 5, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_condition(vita, pc, 5, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)

	with ctx.get("c1130") as (vita, pc): # This script is very different in the Geofront version, due to realphabetization
		pc.includes = vita.includes
		pc.chcp = vita.chcp
		vita = transform_funcs(vita, {
			2: copy(pc.code, vita.code[2]),
			56: copy(pc.code, vita.code[56]),
		}, include=0)
		vita = transform_npcs(vita, {
			11: copy(pc.npcs, vita.npcs[11]),
		})
		copy_clause(vita, pc, 2, "@IF:0", [Insn('FLAG', 1055), Insn('END')], -1)
		copy_clause(vita, pc, 2, "@IF:0", [Insn('FLAG', 1040), Insn('END')], -1)
		copy_clause(vita, pc, 3, 0)
		copy_clause(vita, pc, 14, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 14, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	with ctx.get("c1200") as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			59: copy(pc.code, vita.code[59]),
			60: copy(pc.code, vita.code[60]),
		}, include=0)
		copy_clause(vita, pc, 12, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 12, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 13, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 13, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_condition(vita, pc, 16, "@IF:0", [Insn('FLAG', 1055), Insn('END')], 0)
		copy_condition(vita, pc, 16, "@IF:0", [Insn('FLAG', 1040), Insn('END')], 0)

	with ctx.get("c1410") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 6, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 6, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 34, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 34, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	with ctx.get("t1500") as (vita, pc):
		pc.includes = vita.includes
		pc.triggers.append(vita.triggers[5]) # Not sure if the function index in here is right...
		vita_, pc_ = get(vita, pc, "code", 4, "@IF:1", [Insn('FLAG', 1040), Insn('END')])
		pc_[1:1] = vita_[1:2]
		pc.code[5].insert(6, vita.code[5][9]) # This is way too fragile
		pc.code[5].insert(12, vita.code[5][15])
		pc.code[5].insert(-5, vita.code[5][-6])
		copy_condition(vita, pc, 6, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)
		copy_clause(vita, pc, 32, "@IF", 0, 0)
		get_(pc.code[32], "@IF", 0, 0, 1, "@IF", None, "@MENU").args[4] = \
			get_(pc.code[32], "@IF", 0, 2, 1, "@MENU").args[4]
		pc.code[64].insert(4, vita.code[64][4])

	ctx.copy("t1500_1", tr)

	with ctx.get("t1520") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 9, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 12, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	with ctx.get("t1530") as (vita, pc):
		pc.includes = vita.includes
		vita_, pc_ = get(vita, pc, "code", 5, "@IF:1", [Insn('FLAG', 1040), Insn('END')])
		assert vita_[4].args[0][0][1][0] == pc_[4]
		pc_[4] = vita_[4]

	with ctx.get("t1530_1", tr) as (vita, pc):
		pc.includes = vita.includes
		pc.code.append(vita.code[79])
		pc.code.append(vita.code[80])
		pc.code.append(vita.code[81])
		copy_clause(vita, pc, 1, "@IF", None, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 3, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 10, -4, [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_condition(vita, pc, 13, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)
		copy_clause(vita, pc, 17, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	with ctx.get("t1540") as (vita, pc):
		pc.includes = vita.includes
		pc.npcs.append(vita.npcs[41])
		pc.npcs.append(vita.npcs[42])
		copy_clause(vita, pc, 1, "@IF:-1", 0, 3)
		with ctx.get("t1520") as (vita2, pc2):
			for npc in pc.npcs:
				if not getattr(npc.name, "translated", False):
					npc.name = [npc2.name for npc1, npc2 in zip(vita2.npcs, pc2.npcs) if npc1.name == npc.name]

	with ctx.get("t1540_1", tr) as (vita, pc):
		pc.includes = vita.includes
		pc.code.append(vita.code[50])
		pc.code.append(vita.code[51])
		pc.code.append(vita.code[52])
		copy_clause(vita, pc, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 5, "@IF", None, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 6, "@IF", 0, 1)
		copy_clause(vita, pc, 7, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	with ctx.get("t1600") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 14, "@IF", 0, 1)

	with ctx.get("e0010") as (vita, pc):
		vita = transform_funcs(vita, {
			19: copy(pc.code, vita.code[19]),
		}, include=0)
		copy_clause(vita, pc, 0, "@IF", 0, -1)

def quest57(ctx):
	tr = translate.translator("quest57")
	ctx.copy_quest(57, tr)

	with ctx.get("t4010") as (vita, pc):
		pc.includes = vita.includes
		for func in 21, 22, 24, 28, 29:
			copy_condition(vita, pc, func, -4)
		copy_clause(vita, pc, 25, "@IF:-1", 0, 0)
		copy_clause(vita, pc, 11, "@IF", [Insn('FLAG', 1536), Insn('END')], "@IF", 0, 0)

	ctx.copy("t4010_1", tr)

def quest58(ctx):
	tr = translate.translator("quest58")
	ctx.copy_quest(58, tr)

	with ctx.get("c020c") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 9, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", 0, 0)

	with ctx.get("c0210") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 2, 0)
		copy_clause(vita, pc, 2, -2)
		copy_clause(vita, pc, 5, "@IF:0", 0, 0)
		copy_condition(vita, pc, 5, "@IF:2", 0, 0, 1, "@IF", None, "@WHILE", 1, "@IF:1", 0, -1, 1, 1)
		copy_clause(vita, pc, 9, "@IF", 0, 0)
		copy_clause(vita, pc, 9, "@IF", 0, 1)
		copy_clause(vita, pc, 11, "@IF:1", 0, 0)

	ctx.copy("c0210_1", tr)

	with ctx.get("e3010") as (vita, pc):
		copy_clause(vita, pc, 2, pc.code[2].index(Insn('ITEM_REMOVE', 846, 1))+1)
		copy_clause(vita, pc, 2, pc.code[2].index(Insn('ITEM_REMOVE', 846, 1))+2)

	with ctx.get("r0000") as (vita, pc):
		copy_clause(vita, pc, 1, 0)
	with ctx.get("r1000") as (vita, pc):
		copy_clause(vita, pc, 0, 0)
	with ctx.get("r1500") as (vita, pc):
		copy_clause(vita, pc, 1, 0)
	with ctx.get("r2000") as (vita, pc):
		copy_clause(vita, pc, 0, 0)

	if ctx.is_geofront:
		# This is an ugly way to do it, but it's much easier than doing it "properly"
		frm = "Luscious Orange\0".encode("cp932")
		to = "Zesty Orange\0".encode("cp932")
		assert len(frm) >= len(to)
		data = (ctx.pcpath/"text/t_ittxt._dt").read_bytes()
		data2 = data.replace(frm, to.ljust(len(frm), b"\0"))
		if data != data2:
			(ctx.outpath/"text/t_ittxt._dt").write_bytes(data2)


# m0000, m0001, m0002, m0010, m0100, m0110, m0111, m0112, m3002, m3099, r2050, r2070, c1400, c140b
# contain minor, probably aesthetic, changes

# e0111 (EFF_LOAD typo) and e3000 (bgm in Lechter's singing)
# are slightly more important

def patch_misc(ctx):
	def split(insn, at, *, formatA=lambda a: a, formatB=lambda b: b, names=None):
		if names is None:
			names = (insn.name, insn.name)
		text = insn.args[-1]
		a, b = text.split(at, 1)
		a, b = type(text)(formatA(a)), type(text)(formatB(b))
		a.__dict__ = b.__dict__ = insn.args[-1].__dict__
		return (
			Insn(names[0], *insn.args[:-1], a),
			Insn(names[1], *insn.args[:-1], b),
		)

	miscTranslator = translate.translator("misc")

	# A rather important line in which the Gang learns how to spell
	with ctx.get("c011b", miscTranslator) as (vita, pc):
		v, p = vita.code[35], pc.code[35]
		start = next(i-2 for i, (a, b) in enumerate(zip(v, p)) if a.name != b.name)
		end = next(-i+1 for i, (a, b) in enumerate(zip(v[::-1], p[::-1])) if a.name != b.name)
		assert v[start].name == p[start].name == 'TEXT_TALK'
		assert v[end].name == p[end].name == 'TEXT_WAIT'
		line1, line2 = split(p[start], "{page}")
		p[start:end] = [line1, *v[start+1:end-1], line2]

	# Fran saying "Ah, Lloyd!"
	pos = miscTranslator.pos
	for script, func in ("c011c", 39), ("c011c", 40), ("r2050", 17):
		miscTranslator.pos = pos
		with ctx.get(script, miscTranslator) as (vita, pc):
			startP = next(i+1 for i, a in enumerate(pc.code[func]) if a.name == "TEXT_SET_NAME")
			startV = next(i+1 for i, a in enumerate(vita.code[func]) if a.name == "TEXT_SET_NAME")
			pc.code[func][startP:startP] = vita.code[func][startV:startV+2]

	# Some lines were split in two for some reason
	with ctx.get("c1310") as (vita, pc):
		pc_ = get_(pc.code[11], "@IF:1", [Insn('FLAG', 801), Insn('END')], "@IF", None)
		line1, line2 = split(pc_[0], "\n", formatA=lambda a:"{0x06}%s{wait}"%a)
		pc_[0:2] = [line1, pc_[1], line2, pc_[1]]

	with ctx.get("c110b") as (vita, pc):
		idx1 = next(i for i, a in enumerate(vita.code[6]) if a.name == "TEXT_SET_POS")
		idx2 = next(i for i, a in enumerate(vita.code[6]) if a.name == "TEXT_TALK")
		pc.code[6][idx1:idx1] = vita.code[6][idx1:idx1+6]
		pc.code[6][idx1+1], pc.code[6][idx2] = split(pc.code[6][idx2], "{page}", names=("TEXT_MESSAGE", "TEXT_TALK"))

	with ctx.get("c110c") as (vita, pc):
		idx = next(i for i, a in enumerate(pc.code[41]) if a.name == "FORK_FUNC")
		pc.code[41][idx:idx] = vita.code[41][idx:idx+5]
		pc.code[41][idx+1], pc.code[41][idx+7] = split(pc.code[41][idx+7], "#600W",
			formatA=lambda a:a.rstrip()+"{wait}",
			formatB=lambda b:"{color 0}"+b.replace("#20W", "#20W#3300058V"),
		)
		if ctx.is_geofront:
			# This voice line is misplaced
			idx = next(~i for i, a in enumerate(pc.code[41][::-1]) if a.name == "TEXT_TALK")
			pc.code[41][idx].args[1] = pc.code[41][idx].args[1].replace("#3300058V", "#3300107V")

def get(vita, pc, *path):
	return (get_(vita, *path), get_(pc, *path))

def get_(who, *path):
	for c in path:
		if isinstance(c, str) and c.startswith("@"):
			if ":" in c:
				c, idx = c[1:].split(":")
				idx = int(idx)
				who = [op for op in who if op.name == c][idx]
			else:
				[who] = [op for op in who if op.name == c[1:]]
		elif isinstance(who, Insn):
			if isinstance(c, int):
				who = who.args[c]
			elif who.name == "IF":
				for c2, b in who.args[0]:
					if c2 == c:
						who = b
						break
				else:
					raise ValueError(who, c)
			else:
				raise ValueError(who, c)
		else:
			who = who[c]
	return who

def copy_clause(vita, pc, *path):
	*path, pos = path
	vita, pc = get(vita, pc, "code", *path)
	vitapos = pcpos = pos
	if vitapos < 0: vitapos += len(vita)
	if pcpos < 0: pcpos += len(pc)+1
	pc[pcpos:pcpos] = vita[vitapos:vitapos+1]

def copy_condition(vita, pc, *path):
	*path, pos = path
	if pos < 0: pos += len(vita)
	vita, pc = get(vita, pc, "code", *path)
	assert vita[pos].name == "IF"
	end = pos+len(vita[pos].args[0][-1][1])
	pc[pos:end] = [
		Insn("IF", [
			*vita[pos].args[0][:-1],
			(vita[pos].args[0][-1][0], pc[pos:end])
		])
	]

def extract_func(pc, *path, include=0):
	n = len(pc.code)
	wh = get_(pc, "code", *path)
	pc.code.append(wh + [Insn('RETURN')])
	wh[:] = [Insn('CALL', (include, n))]
	return n

def copy(objects, obj):
	n = len(objects)
	objects.append(obj)
	return n

def transform_funcs(script, tr, include=0):
	script = do_transform(script, { "func": {
		(include, k): (include, v)
		for k, v in to_permutation(tr).items()
	} })
	permute(tr, script.code)
	return script

def transform_npcs(script, tr):
	script = do_transform(script, {"npc": {
		k+8: v+8
		for k, v in to_permutation(tr).items()
	}})
	permute(tr, script.npcs)
	return script

def to_permutation(tr):
	i = list(range(max([0, *tr.keys(), *tr.values()]) + 1))
	o = permute(tr, i[:])
	return {k: v for k, v in zip(o, i) if k != v}

def permute(tr, xs):
	vals = {}
	for i, o in sorted(tr.items(), key=lambda a: -a[0]):
		vals[i] = xs.pop(i)
	for i, o in sorted(tr.items(), key=lambda a: a[1]):
		xs.insert(o, vals[i])
	return xs

def do_transform(obj, tr):
	if isinstance(obj, insn.Translate) and not getattr(obj, "translated", False):
		if isinstance(tr.get("translate"), translate.BaseTranslator):
			obj = type(obj)(tr["translate"].translate(obj))
		obj.translated = True
		return obj

	if isinstance(obj, Insn):
		obj.args = do_transform(obj.args, tr)
		return obj
	if isinstance(obj, insn.Function):
		return type(obj)(tr.get("func", {}).get(obj, obj))
	if isinstance(obj, insn.Char):
		return type(obj)(tr.get("npc", {}).get(obj, obj))

	if isinstance(obj, list):
		obj[:] = (do_transform(a, tr) for a in obj)
		return obj
	if isinstance(obj, tuple):
		return type(obj)(do_transform(a, tr) for a in obj)
	if isinstance(obj, dict):
		xs = {do_transform(k, tr): do_transform(v, tr) for k, v in obj.items()}
		obj.clear()
		obj.update(xs)
		return obj
	return obj

argp = argparse.ArgumentParser()
argp.add_argument("vitapath", type=Path, help="Path to the Vita data. This should likely be named \"data\"")
argp.add_argument("pcpath", type=Path, help="Path to the PC data. This should likely be named either \"data\" or \"data_en\"")
argp.add_argument("outpath", type=Path, help="Directory to place the patched files into. This should be merged into the data directory.")
argp.add_argument("--minigame", action="store_true", help="Patches in dialogue for certain furniture in the headquarters. The minigames are not implemented, so it is simply a fade to black.")
argp.add_argument("--no-misc", action="store_false", help="Include only the quests, and not the miscellaneous minor patches")
def __main__(vitapath, pcpath, outpath, minigame, no_misc):
	if not vitapath.is_dir():
		raise ValueError("vitapath must be a directory")
	if not pcpath.is_dir():
		raise ValueError("pcpath must be a directory")

	if outpath.exists():
		shutil.rmtree(outpath)
	outpath.mkdir(parents=True, exist_ok=True)
	(outpath/"scena").mkdir()
	(outpath/"text").mkdir()

	ctx = Context(vitapath, pcpath, outpath)

	if minigame:
		patch_furniture_minigames(ctx)
	patch_quests(ctx)
	if not no_misc:
		patch_misc(ctx)

	ctx.save()

if __name__ == "__main__":
	__main__(**argp.parse_args().__dict__)
