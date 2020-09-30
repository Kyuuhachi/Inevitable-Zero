import shutil
from pathlib import Path
import argparse

import kouzou
import scena
import insn

class CustomRepr:
	def __init__(self, repr):
		self.repr = repr
	def __repr__(self): return self.repr

def dump(f, data, mode):
	f.write("if 0: from . import Insn, Expr, Text, Translate, Char, Flag, Function\n")
	f.write("data = ")
	pprint(f, {**data, "code": CustomRepr(f"[None]*{len(data['code'])}")}, mode)
	f.write("\n")
	# Printhing functions like this makes it easier to see the indices
	# of functions, both while reading the code and in diff context lines.
	for i, func in enumerate(data["code"]):
		f.write(f"\ndata[{'code'!r}][{i!r}] = ")
		pprint(f, func, mode)
		f.write("\n")

def commas(f, items, indent):
	if indent is None:
		has = False
		for item in items:
			if has:
				f.write(", ")
			yield item, None
			has = True
	else:
		has = False
		for item in items:
			f.write("\n" + "\t"*(indent+1))
			yield item, indent+1
			f.write(",")
			has = True
		if has:
			f.write("\n" + "\t"*indent)

def pprint(f, data, mode, indent=0):
	if isinstance(data, insn.Translate) and mode == "diff":
		f.write("...")
		return

	if isinstance(data, insn.Expr):
		indent = None

	if isinstance(data, insn.Text) and indent is not None:
		f.write(type(data).__qualname__)
		f.write("(")
		for line in data.replace("{wait}", "\r").replace("{page}", "\f").splitlines(keepends=True):
			f.write("\n" + "\t"*(indent+1))
			f.write(repr(line.replace("\r", "{wait}").replace("\f", "{page}")))
		f.write("\n" + "\t"*indent)
		f.write(")")
		return

	for cls in [kouzou.dotdict, bool, int, float, str, dict, tuple, list]:
		if isinstance(data, cls):
			if type(data) is not cls:
				f.write(type(data).__qualname__)
				f.write("(")
				pprint(f, cls(data), mode, indent)
				f.write(")")
				return
			break

	if isinstance(data, dict):
		f.write("{")
		for (k, v), ind in commas(f, data.items(), indent):
			pprint(f, k, mode, None)
			f.write(": ")
			pprint(f, v, mode, ind)
		f.write("}")
		return

	if isinstance(data, list):
		f.write("[")
		for v, ind in commas(f, data, indent):
			pprint(f, v, mode, ind)
		f.write("]")
		return

	if isinstance(data, tuple):
		f.write("(")
		for v, _ in commas(f, data, None):
			pprint(f, v, mode, indent)
		if len(data) == 1:
			f.write(",")
		f.write(")")
		return

	if isinstance(data, insn.Insn) and data.name == "IF":
		f.write(f"Insn({data.name!r}, [")
		for (cond, body), ind in commas(f, data.args[0], indent):
			f.write("(")
			pprint(f, cond, mode, None)
			f.write(", ")
			pprint(f, body, mode, ind)
			f.write(")")
		f.write("])")
		return

	if isinstance(data, insn.Insn) and data.name == "WHILE":
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, ")
		pprint(f, data.args[1], mode, indent)
		f.write(")")
		return

	if isinstance(data, insn.Insn) and data.name == "SWITCH":
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, ")
		pprint(f, data.args[1], mode, indent)
		f.write(")")
		return

	if isinstance(data, insn.Insn) and data.name in ["FORK", "FORK_LOOP"]:
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, {data.args[1]!r}, ")
		pprint(f, data.args[2], mode, indent)
		f.write(")")
		return

	if isinstance(data, insn.Insn):
		f.write(f"Insn({data.name!r}")
		for arg in data.args:
			f.write(", ")
			pprint(f, arg, mode, indent)

		f.write(")")
		return

	f.write(repr(data))

argp = argparse.ArgumentParser()
argp.add_argument("-d", "--diff", dest="dump_mode", action="store_const", const="diff")
argp.add_argument("-m", "--mode", choices=["jp", "geofront", "vita"], required=True)
argp.add_argument("inpath", type=Path)
argp.add_argument("outpath", type=Path)
def __main__(dump_mode, mode, inpath, outpath):
	if not inpath.is_dir():
		raise ValueError("inpath must be a directory")

	if outpath.exists():
		shutil.rmtree(outpath)
	outpath.mkdir(parents=True, exist_ok=True)

	insns = {
		"jp": insn.insn_zero_pc,
		"vita": insn.insn_zero_vita,
		"geofront": insn.insn_zero_pc,
	}[mode]

	for file in sorted(inpath.glob("*.bin")):
		outfile = (outpath/file.name).with_suffix(".py")
		print(outfile)

		with file.open("rb") as f:
			params = {
				"_insns": insns,
			}
			if mode == "geofront" and file.stem in scena.geofront_tweaks:
				params["_geofront_tweaks"] = scena.geofront_tweaks[file.stem]
			data = kouzou.read(scena.scenaStruct, f, params)

		with outfile.open("wt") as f:
			dump(f, data, dump_mode)

if __name__ == "__main__":
	__main__(**argp.parse_args().__dict__)
