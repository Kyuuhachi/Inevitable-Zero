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

def dump(f, data, compact):
	f.write("if 0: from . import Insn\n")
	f.write("data = ")
	pprint(f, {**data, "code": CustomRepr(f"[None]*{len(data['code'])}")})
	f.write("\n")
	# Printhing functions like this makes it easier to see the indices
	# of functions, both while reading the code and in diff context lines.
	for i, func in enumerate(data["code"]):
		f.write(f"\ndata[{'code'!r}][{i!r}] = ")
		pprint(f, func, compact)
		f.write("\n")

def pprint(f, data, compact=False, indent=0):
	if isinstance(data, dict):
		f.write("{")
		for k, v in data.items():
			f.write("\n" + "\t"*(indent+1))
			f.write(repr(k))
			f.write(": ")
			pprint(f, v, compact, indent+1)
			f.write(",")
		if data:
			f.write("\n" + "\t"*indent)
		f.write("}")
		return

	if isinstance(data, list):
		f.write("[")
		for v in data:
			f.write("\n" + "\t"*(indent+1))
			pprint(f, v, compact, indent+1)
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
			pprint(f, body, compact, indent+1)
			f.write(")")
			f.write(",")
		f.write("\n" + "\t"*indent + "])")
		return

	if isinstance(data, insn.Insn) and data.name == "WHILE":
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, ")
		pprint(f, data.args[1], compact, indent)
		f.write(")")
		return

	if isinstance(data, insn.Insn) and data.name == "SWITCH":
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, ")
		pprint(f, data.args[1], compact, indent)
		f.write(")")
		return

	if isinstance(data, insn.Insn) and data.name in ["FORK", "FORK_LOOP"]:
		f.write(f"Insn({data.name!r}, {data.args[0]!r}, {data.args[1]!r}, ")
		pprint(f, data.args[2], compact, indent)
		f.write(")")
		return

	if isinstance(data, insn.Insn):
		f.write(f"Insn({data.name!r}")
		prevText = False
		for arg in data.args:
			f.write(",")
			if isinstance(arg, insn.Text) and not compact:
				for line in arg.splitlines(keepends=True):
					f.write("\n" + "\t"*(indent+1))
					f.write(repr(line))
				prevText = True
			else:
				if prevText:
					f.write("\n" + "\t"*(indent+1))
				else:
					f.write(" ")
				f.write(repr(arg))
				prevText = False

		if prevText:
			f.write("\n" + "\t"*indent)
		f.write(")")
		return

	f.write(repr(data))

argp = argparse.ArgumentParser()
argp.add_argument("-c", "--compact", action="store_true")
argp.add_argument("-m", "--mode", choices=["jp", "geofront", "vita"], required=True)
argp.add_argument("inpath", type=Path)
argp.add_argument("outpath", type=Path)
def __main__(compact, mode, inpath, outpath):
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
			dump(f, data, compact)

if __name__ == "__main__":
	__main__(**argp.parse_args().__dict__)
