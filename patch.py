import shutil
from pathlib import Path
import argparse

import kouzou
import scena
import insn
import dump

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
				self.pc_scripts[name] = kouzou.read(scena.scenaStruct, f, params)
		return self.pc_scripts[name]

	def get(self, name):
		return self.get_vita(name), self.get_pc(name)

def patch_furniture_minigames(ctx):
	# Since the minigames don't exist on PC, this doesn't quite work.
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

def patch_quest_lists(ctx):
	for file, func in [
			("c0110", 3),
			("c011c", 8),
	]:
		vita, pc = ctx.get(file)
		vita, pc = vita.code[func], pc.code[func]
		assert len(vita) == len(pc)
		for vita, pc in zip(vita, pc):
			if vita.name == pc.name == "WHILE":
				break
		vita, pc = vita.args[1][1], pc.args[1][1]
		assert vita.name == pc.name == "SWITCH"
		pc.args[1][0] = vita.args[1][0]

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
	patch_quest_lists(ctx)

	for name, script in ctx.pc_scripts.items():
		with (outpath / name).with_suffix(".bin").open("wb") as f:
			params = { "_insns": insn.insn_zero_pc }
			kouzou.write(scena.scenaStruct, f, script, params)
		with (outpath / name).with_suffix(".py").open("wt") as f:
			dump.dump(f, script, False)

if __name__ == "__main__":
	__main__(**argp.parse_args().__dict__)
