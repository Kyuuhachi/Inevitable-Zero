import shutil
from pathlib import Path
import argparse

import kouzou
import scena
import insn
import dump
from insn import Insn
from translate import translator

class Context:
	def __init__(self, vitapath, pcpath, is_geofront=None):
		if is_geofront is None:
			is_geofront = "data_en" in pcpath.absolute().parts
		self.vitapath = vitapath
		self.vita_scripts = {}
		self.pcpath = pcpath
		self.pc_scripts = {}
		self.is_geofront = is_geofront

	def get_vita(self, name):
		if name not in self.vita_scripts:
			with (self.vitapath / name).with_suffix(".bin").open("rb") as f:
				params = { "_insns": insn.insn_zero_vita }
				self.vita_scripts[name] = kouzou.read(scena.scenaStruct, f, params)
		return self.vita_scripts[name]

	def get_pc(self, name):
		if name not in self.pc_scripts:
			with (self.pcpath / name).with_suffix(".bin").open("rb") as f:
				params = { "_insns": insn.insn_zero_pc }
				if self.is_geofront and name in scena.geofront_tweaks:
					params["_geofront_tweaks"] = scena.geofront_tweaks[name]
				self.pc_scripts[name] = do_transform(
					kouzou.read(scena.scenaStruct, f, params),
					{ "translate": True },
				)
		return self.pc_scripts[name]

	def get(self, name):
		return self.get_vita(name), self.get_pc(name)

def patch_furniture_minigames(ctx):
	# There are minigames on some room furniture in the Vita version, let's
	# import that. Since the minigames don't exist on PC, it doesn't quite work.
	for file, func in [
			("c0110_1", 33), ("c0110_1", 35), ("c0110_1", 38),
			("c011b", 73), ("c011b", 75), ("c011b", 78),
			("c011c", 58), ("c011c", 60), ("c011c", 63),
	]:
		vita, pc = ctx.get(file)
		vita, pc = vita.code[func], pc.code[func]
		assert vita[10] == pc[10]
		pc[11:11] = vita[11:17]
		assert vita[18] == pc[18]
		assert vita[22] == pc[22]
		assert vita[23].name == "IF"
		pc.insert(23, vita[23])

def patch_quests(ctx):
	for file, func in [
			("c0110", 3),
			("c011c", 8),
	]:
		vita_, pc_ = get(*ctx.get(file), "code", func, "@WHILE", 1, "@SWITCH", 1)
		pc_[0] = vita_[0]

	vita, pc = ctx.get("c0110")
	vita, pc = vita.code[46], pc.code[46]
	assert pc[-6:-4] == vita[-8:-6]
	pc[-4:-4] = vita[-6:-4]

	vita, pc = ctx.get("c0000")
	pc.includes = vita.includes
	vita = transform_funcs(vita, {
		55: copy(pc.code, vita.code[55]),
		60: copy(pc.code, vita.code[60]),
	}, include=0)
	copy_condition(vita, pc, 6, "@IF", [Insn('FLAG', 1055), Insn('END')], 0)
	copy_clause(vita, pc, 6, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	vita, pc = ctx.get("c0100")
	pc.includes = vita.includes

	vita, pc = ctx.get("c0100_1")
	copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	vita, pc = ctx.get("c020c")
	pc.includes = vita.includes
	copy_clause(vita, pc, 9, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", 0, 0)

	vita, pc = ctx.get("c0210")
	pc.includes = vita.includes
	copy_clause(vita, pc, 2, 0)
	copy_clause(vita, pc, 2, -2)
	copy_clause(vita, pc, 5, "@IF:0", 0, 0)
	copy_condition(vita, pc, 5, "@IF:2", 0, 0, 1, "@IF", None, "@WHILE", 1, "@IF:1", 0, -1, 1, 1)
	copy_clause(vita, pc, 9, "@IF", 0, 0)
	copy_clause(vita, pc, 9, "@IF", 0, 1)
	copy_clause(vita, pc, 11, "@IF:1", 0, 0)

	vita, pc = ctx.get("c0400")
	copy_clause(vita, pc, 49, pc.code[49].index(Insn('EXPR_VAR', 3, [Insn('CONST', 0), Insn('SET'), Insn('END')]))+9)
	copy_clause(vita, pc, 49, pc.code[49].index(Insn('EXPR_VAR', 3, [Insn('CONST', 0), Insn('SET'), Insn('END')]))+10)
	copy_clause(vita, pc, 49, pc.code[49].index(Insn('ITEM_REMOVE', 805, 1))+8)
	copy_clause(vita, pc, 49, pc.code[49].index(Insn('ITEM_REMOVE', 805, 1))+9)

	vita, pc = ctx.get("c1100")
	pc.includes = vita.includes
	copy_clause(vita, pc, 5, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
	copy_condition(vita, pc, 5, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)

	vita, pc = ctx.get("c1130")
	pc.includes = vita.includes
	pc.chcp = vita.chcp
	vita = transform_funcs(vita, {
		2: copy(pc.code, vita.code[2]),
		56: copy(pc.code, vita.code[56]),
	}, include=0)
	vita = transform_npcs(vita, {
		11: copy(pc.npcs, vita.npcs[11]),
	})
	copy_clause(vita, pc, 3, 0)
	copy_clause(vita, pc, 2, "@IF:0", [Insn('FLAG', 1055), Insn('END')], -1)
	copy_clause(vita, pc, 2, "@IF:0", [Insn('FLAG', 1040), Insn('END')], -1)
	copy_clause(vita, pc, 14, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 14, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	vita, pc = ctx.get("c1200")
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

	vita, pc = ctx.get("c1410")
	pc.includes = vita.includes
	copy_clause(vita, pc, 6, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 6, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 34, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 34, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	# tXXXX

	vita, pc = ctx.get("t0500")
	pc.includes = vita.includes
	copy_clause(vita, pc, 13, "@IF", 0, 0)

	vita, pc = ctx.get("t0520")
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

	vita, pc = ctx.get("t1000")
	pc.includes = vita.includes
	pc.chcp = vita.chcp
	vita = transform_funcs(vita, {
		17: copy(pc.code, vita.code[17]),
	}, include=0)
	vita = transform_npcs(vita, {
		13: copy(pc.npcs, vita.npcs[13]),
	})
	copy_clause(vita, pc, 1, 1)

	vita, pc = ctx.get("t1010")
	pc.includes = vita.includes
	pc.chcp = vita.chcp
	vita = transform_npcs(vita, {
		2: copy(pc.npcs, vita.npcs[2]),
	})
	pc.code[4][-3:-1] = vita.code[4][-2:-1]

	vita, pc = ctx.get("t1020")
	pc.includes = vita.includes
	vita = transform_funcs(vita, {
		13: copy(pc.code, vita.code[13]),
		3: copy(pc.code, vita.code[3]),
	}, include=0)
	vita = transform_npcs(vita, {
		6: copy(pc.npcs, vita.npcs[6]),
	})
	copy_clause(vita, pc, 3, -2)

	vita, pc = ctx.get("t1030")
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

	vita, pc = ctx.get("t1050") # XXX I'm sure this can be improved
	pc.includes = vita.includes
	vita = transform_funcs(vita, {
		12: copy(pc.code, vita.code[12]),
	}, include=0)
	for flag in 1312, 1317, 1318:
		copy_clause(vita, pc, 10, "@IF", [Insn('FLAG', flag), Insn('END')], 0)
		copy_condition(vita, pc, 10, "@IF", [Insn('FLAG', flag), Insn('END')], 1)

	vita, pc = ctx.get("t105b")
	pc.code[14].insert(-4, vita.code[14][-5])

	vita, pc = ctx.get("t1500")
	pc.includes = vita.includes
	pc.triggers.append(vita.triggers[5]) # Not sure if the function index in here is right...
	vita_, pc_ = get(vita, pc, "code", 4, "@IF:1", [Insn('FLAG', 1040), Insn('END')])
	pc_[1:1] = vita_[1:2]
	pc.code[5].insert(6, vita.code[5][9]) # This is way too fragile
	pc.code[5].insert(12, vita.code[5][15])
	pc.code[5].insert(-5, vita.code[5][-6])
	copy_condition(vita, pc, 6, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)
	copy_clause(vita, pc, 32, "@IF", 0, 0)
	pc.code[64].insert(4, vita.code[64][4])

	vita, pc = ctx.get("t1520")
	pc.includes = vita.includes
	copy_clause(vita, pc, 9, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 12, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	vita, pc = ctx.get("t1530_1")
	pc.includes = vita.includes
	pc.code.append(vita.code[79])
	pc.code.append(vita.code[80])
	pc.code.append(vita.code[81])
	copy_clause(vita, pc, 1, "@IF", None, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 3, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 10, -4, [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_condition(vita, pc, 13, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)
	copy_clause(vita, pc, 17, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	vita, pc = ctx.get("t1530")
	pc.includes = vita.includes
	vita_, pc_ = get(vita, pc, "code", 5, "@IF:1", [Insn('FLAG', 1040), Insn('END')])
	assert vita_[4].args[0][0][1][0] == pc_[4]
	pc_[4] = vita_[4]

	vita, pc = ctx.get("t1540_1")
	pc.includes = vita.includes
	pc.code.append(vita.code[50])
	pc.code.append(vita.code[51])
	pc.code.append(vita.code[52])
	copy_clause(vita, pc, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 5, "@IF", None, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 6, "@IF", 0, 1)
	copy_clause(vita, pc, 7, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
	copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	vita, pc = ctx.get("t1540")
	pc.includes = vita.includes
	pc.npcs.append(vita.npcs[41])
	pc.npcs.append(vita.npcs[42])
	copy_clause(vita, pc, 1, "@IF:-1", 0, 3)

	vita, pc = ctx.get("t1600")
	pc.includes = vita.includes
	copy_clause(vita, pc, 14, "@IF", 0, 1)

	vita, pc = ctx.get("t4010")
	pc.includes = vita.includes
	for func in 21, 22, 24, 28, 29:
		copy_condition(vita, pc, func, -4)
	copy_clause(vita, pc, 25, "@IF:-1", 0, 0)
	copy_clause(vita, pc, 11, "@IF", [Insn('FLAG', 1536), Insn('END')], "@IF", 0, 0)

	vita, pc = ctx.get("r0000")
	copy_clause(vita, pc, 1, 0)
	vita, pc = ctx.get("r1500")
	copy_clause(vita, pc, 1, 0)
	vita, pc = ctx.get("r2000")
	copy_clause(vita, pc, 0, 0)

	vita, pc = ctx.get("e0010")
	vita = transform_funcs(vita, {
		19: copy(pc.code, vita.code[19]),
	}, include=0)
	copy_clause(vita, pc, 0, "@IF", 0, -1)

	vita, pc = ctx.get("e3010")
	copy_clause(vita, pc, 2, pc.code[2].index(Insn('ITEM_REMOVE', 846, 1))+1)
	copy_clause(vita, pc, 2, pc.code[2].index(Insn('ITEM_REMOVE', 846, 1))+2)

	ctx.pc_scripts["c0210_1"] = ctx.get_vita("c0210_1")
	ctx.pc_scripts["t0520_1"] = ctx.get_vita("t0520_1")
	ctx.pc_scripts["t1030_1"] = ctx.get_vita("t1030_1")
	ctx.pc_scripts["t1500_1"] = ctx.get_vita("t1500_1")
	ctx.pc_scripts["t4010_1"] = ctx.get_vita("t4010_1")

# m0000, m0001, m0002, m0010, m0100, m0110, m0111, m0112, m3002, m3099, r2050, r2070, c1400, c140b
# contain minor, probably aesthetic, changes

# e0111 (EFF_LOAD typo) and e3000 (bgm in Lechter's singing)
# are slightly more important

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
		if isinstance(tr.get("translate"), translator):
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
argp.add_argument("vitapath", type=Path)
argp.add_argument("pcpath", type=Path)
argp.add_argument("outpath", type=Path)
def __main__(vitapath, pcpath, outpath):
	if not vitapath.is_dir():
		raise ValueError("vitapath must be a directory")
	if not pcpath.is_dir():
		raise ValueError("pcpath must be a directory")

	if outpath.exists():
		shutil.rmtree(outpath)
	outpath.mkdir(parents=True, exist_ok=True)

	ctx = Context(vitapath, pcpath)

	patch_furniture_minigames(ctx)
	patch_quests(ctx)

	if ctx.is_geofront:
		for name in ctx.pc_scripts:
			ctx.pc_scripts[name] = do_transform(
				ctx.pc_scripts[name],
				{ "translate": translator(name) },
			)

	# for name, script in ctx.pc_scripts.items():
		# with (outpath / name).with_suffix(".bin").open("wb") as f:
		# 	params = { "_insns": insn.insn_zero_pc }
		# 	kouzou.write(scena.scenaStruct, f, script, params)

	for name, script in ctx.vita_scripts.items():
		with (Path("scr/vita") / name).with_suffix(".py").open("wt") as f:
			dump.dump(f, script, "diff")
	for name, script in ctx.pc_scripts.items():
		with (Path("scr/pc") / name).with_suffix(".py").open("wt") as f:
			dump.dump(f, script, "diff")

if __name__ == "__main__":
	__main__(**argp.parse_args().__dict__)
