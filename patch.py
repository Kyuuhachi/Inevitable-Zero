#!/usr/bin/env python3
import shutil
from pathlib import Path
import argparse
from contextlib import contextmanager
from copy import deepcopy

import kouzou
import scena
import quest
import insn
import dump
from insn import Insn, Char
import translate

class Context: # {{{1
	def __init__(self, vitapath, pcpath, outpath, en: bool, portraits: Path|None = None):
		self.en = en
		self.portraits = portraits

		self.vitapath = vitapath
		self.vita_scripts = {}
		with (vitapath/"text/t_quest._dt").open("rb") as f:
			self.vita_quests = kouzou.read(quest.questStruct, f)

		self.pcpath = pcpath
		self.pc_scripts = {}
		with (pcpath/("text_us" if self.en else "text")/"t_quest._dt").open("rb") as f:
			self.pc_quests = kouzou.read(quest.questStruct, f)

		self.outpath = outpath

	def save(self):
		with (self.outpath/("text_us" if self.en else "text")/"t_quest._dt").open("wb") as f:
			kouzou.write(quest.questStruct, f, self.pc_quests)

		for name, script in self.pc_scripts.items():
			with (self.outpath/("scena_us" if self.en else "scena")/name).with_suffix(".bin").open("wb") as f:
				params = { "_insns": insn.insn_zero_22 }
				kouzou.write(scena.scenaStruct, f, script, params)

	def _load(self, name, params, *, vita, transform):
		path = self.vitapath if vita else self.pcpath
		# }}}
		if self.en and not vita:
			path = (path/"scena_us"/name).with_suffix(".bin")
		else:
			path = (path/"scena"/name).with_suffix(".bin")

		with path.open("rb") as f:
			sc = kouzou.read(scena.scenaStruct, f, params)
			if not vita and self.portraits is not None:
				path2 = (self.portraits/("scena_us" if self.en else "scena")/name).with_suffix(".bin")
				if path2.exists():
					with path2.open("rb") as f:
						from copy import deepcopy
						sc = kouzou.read(scena.scenaStruct, f, {**params, "_eddec_original": deepcopy(sc.code)})
			sc = do_transform(sc, transform)
			return sc

	def _get_vita(self, name):
		if name not in self.vita_scripts:
			params = { "_insns": insn.insn_zero_vita }
			self.vita_scripts[name] = self._load(name, params, vita=True, transform=None)
		return self.vita_scripts[name]

	def _get_pc(self, name):
		if name not in self.pc_scripts:
			params = { "_insns": insn.insn_zero_22 }
			self.pc_scripts[name] = self._load(name, params, vita=False, transform={ "translate": True })
		return self.pc_scripts[name]

	def copy(self, name, translation=None):
		assert not (self.pcpath/name).with_suffix(".bin").exists()
		assert name not in self.pc_scripts
		self.pc_scripts[name] = self._get_vita(name)
		self._do_translate(name, translation)
		return self.pc_scripts[name]

	@contextmanager
	def get(self, name, translation=None):
		yield self._get_vita(name), self._get_pc(name)
		self._do_translate(name, translation)

	def _do_translate(self, name, translation):
		if translation is None:
			translation = translate.null_translator()
		if self.en:
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

def patch_furniture_minigames(ctx): # {{{1
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

def patch_timing(ctx): # {{{1 Main infrastructure: starting and failing the quests
	# Add to quest lists
	for file, func in [
		("c0110", 3),
		("c011c", 8),
	]:
		with ctx.get(file) as (vita, pc):
			vita_, pc_ = get(vita, pc, "code", func, "@WHILE", 1, "@SWITCH", 1)
			pc_[0] = vita_[0]

	# Failure (I think)

	# 54, 57
	with ctx.get("c0110") as (vita, pc):
		vita_, pc_ = vita.code[46], pc.code[46]
		assert pc_[-6:-4] == vita_[-8:-6]
		pc_[-4:-4] = vita_[-6:-4]

	# 56, 58
	with ctx.get("c0400") as (vita, pc):
		pc_index   =   pc.code[49].index(Insn('EXPR_VAR', 3, [Insn('CONST', 0), Insn('SET'), Insn('END')]))
		vita_index = vita.code[49].index(Insn('EXPR_VAR', 3, [Insn('CONST', 0), Insn('SET'), Insn('END')]))
		pc.code[49][pc_index+9:pc_index+9] = vita.code[49][vita_index+9:vita_index+11]
		pc_index   =   pc.code[49].index(Insn('ITEM_REMOVE', 805, 1))
		vita_index = vita.code[49].index(Insn('ITEM_REMOVE', 805, 1))
		pc.code[49][pc_index+8:pc_index+8] = vita.code[49][vita_index+8:vita_index+10]

	# 55
	with ctx.get("t105b") as (vita, pc):
		pc.code[14].insert(-4, vita.code[14][-5])

def quest54(ctx): # {{{1 Clerk’s Customer Service Guidance
	tr = translate.translator("quest54")
	ctx.copy_quest(54, tr)

	# Mainz Mining Village, talking to Carlos
	with ctx.get("t0500") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 13, "@IF", 0, 0)

	# Der Ziegel Inn
	with ctx.get("t0520") as (vita, pc):
		pc.includes = vita.includes

		p1 = [ 5,
			"@IF", None,
			"@WHILE", 1,
			"@IF:1", [Insn('VAR', 0), Insn('CONST', 0), Insn('EQ'), Insn('END')],
		]
		p2 = [6]
		vita = transform_funcs(vita, {
			6:  extract_func(pc, *p1, "@IF", [Insn('FLAG', 1536), Insn('END')]),
			7:  extract_func(pc, *p1, "@IF", [Insn('FLAG', 1544), Insn('END')]),
			8:  extract_func(pc, *p1, "@IF", [Insn('FLAG', 1547), Insn('END')]),
			10: extract_func(pc, *p2, "@IF", [Insn('FLAG', 1536), Insn('END')]),
			11: extract_func(pc, *p2, "@IF", [Insn('FLAG', 1544), Insn('END')]),
			12: extract_func(pc, *p2, "@IF", [Insn('FLAG', 1547), Insn('END')]),
		})

		copy_clause(vita, pc, *p1, "@IF", 0, 0) # Noma
		copy_clause(vita, pc, *p2, "@IF", 0, 0) # Luka

	ctx.copy("t0520_1", tr)

def quest55(ctx): # {{{1 Search for a Certain Person
	tr = translate.translator("quest55")
	ctx.copy_quest(55, tr)

	# Mishelam, docks
	with ctx.get("t1000", tr) as (vita, pc):
		pc.includes = vita.includes
		pc.chcp = vita.chcp
		vita = transform_funcs(vita, {
			17: copy(pc.code, vita.code[17]),
		}, include=0)
		vita = transform_npcs(vita, {
			13: copy(pc.npcs, vita.npcs[13]),
		})

		copy_clause(vita, pc, 1, 1) # Add Tourist

	# Mishelam, residental district
	with ctx.get("t1010", tr) as (vita, pc):
		pc.includes = vita.includes
		pc.chcp = vita.chcp
		vita = transform_npcs(vita, t1010_map := {
			2: copy(pc.npcs, vita.npcs[2]),
		})

		# XXX Cabilan and Lughman don't have flag 0x0080 in Vita
		pc.code[4][-3:-1] = vita.code[4][-2:-1] # Add Mishy

	# Mishelam, mall
	with ctx.get("t1020", tr) as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			13: copy(pc.code, vita.code[13]),
			3: copy(pc.code, vita.code[3]),
		})
		vita = transform_npcs(vita, {
			6: copy(pc.npcs, vita.npcs[6]),
		})

		copy_clause(vita, pc, 3, -2) # Add Girl

	# Mishelam, Wonderland entrance
	with ctx.get("t1030") as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			4: extract_func(pc, 3, "@IF", [Insn('FLAG', 1312), Insn('END')]),
			5: extract_func(pc, 3, "@IF", [Insn('FLAG', 1318), Insn('END')]),
		}, include=0)

		copy_clause(vita, pc, 1, "@IF:0", [Insn('FLAG', 1318), Insn('END')], 0) # Add Sunita
		copy_condition(vita, pc, 1, "@IF:0", [Insn('FLAG', 1312), Insn('END')], 2) # -''-
		copy_clause(vita, pc, 1, -2) # Entering after finding Mishy
		copy_clause(vita, pc, 3, "@IF", 0, 0) # Talking to Clerk
		copy_clause(vita, pc, 5, "@IF", 0, 0) # Talking to Mishy

	# Mishelam, hotel
	with ctx.get("t1050") as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			12: copy(pc.code, vita.code[12]),
		}, include=0)
		# Talking to Citrus
		for flag in 1312, 1317, 1318:
			copy_clause(vita, pc, 10, "@IF", [Insn('FLAG', flag), Insn('END')], 0)
			copy_condition(vita, pc, 10, "@IF", [Insn('FLAG', flag), Insn('END')], 1)

	pc = ctx.copy("t1030_1", tr)
	pc.code[18] = do_transform(pc.code[18], { "func": {
		(1, k): (1, v)
		for k, v in to_permutation({
			# Function 16 uses character 10 in both t1010 and t1030, but here they
			# are different. So let's add a copy.
			16: copy(pc.code, deepcopy(pc.code[16])),
		}).items()
	} })
	for fn in 11, 14, 15, 16, 17:
		pc.code[fn] = do_transform(pc.code[fn], {"npc": { k+8: v+8 for k, v in to_permutation(t1010_map).items() }})

def quest56(ctx): # {{{1 Search for the Oversleeping Doctor
	tr = translate.translator("quest56")
	ctx.copy_quest(56, tr)

	# St. Ursula Medical College
	with ctx.get("t1500") as (vita, pc):
		pc.includes = vita.includes
		pc.triggers.append(vita.triggers[5])

		# Entering
		vita_, pc_ = get(vita, pc, "code", 4, "@IF:1", [Insn('FLAG', 1040), Insn('END')])
		pc_[1:1] = vita_[1:2]

		# Trying to leave
		pc.code[5].insert(6, vita.code[5][9]) # This is way too fragile
		pc.code[5].insert(12, vita.code[5][15])
		pc.code[5].insert(-5, vita.code[5][-6])

		# Talking to Tony
		copy_condition(vita, pc, 6, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)

		# Bus stop
		copy_clause(vita, pc, 32, "@IF", 0, 0)
		get_(pc.code[32], "@IF", 0, 0, 1, "@IF", None, "@MENU").args[4] = \
			get_(pc.code[32], "@IF", 0, 2, 1, "@MENU").args[4]

		# Trying to leave (called from 5)
		pc.code[64].insert(4, vita.code[64][4])

	ctx.copy("t1500_1", tr)

	# Hospital Dorms
	with ctx.get("t1520") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 9, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Talking to Marone
		copy_clause(vita, pc, 12, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Talking to Gwen

	# Waiting room
	with ctx.get("t1530") as (vita, pc):
		pc.includes = vita.includes
		# Loading; something with an outpatient?
		vita_, pc_ = get(vita, pc, "code", 5, "@IF:1", [Insn('FLAG', 1040), Insn('END')])
		assert vita_[4].args[0][0][1][0] == pc_[4]
		pc_[4] = vita_[4]

	# -''-
	with ctx.get("t1530_1", tr) as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			79: copy(pc.code, vita.code[79]),
			80: copy(pc.code, vita.code[80]),
			81: copy(pc.code, vita.code[81]),
		})
		copy_clause(vita, pc, 1, "@IF", None, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Talking to Philia
		copy_clause(vita, pc, 3, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Talking to Clark
		copy_clause(vita, pc, 10, -4, [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Talking to Gailey
		copy_condition(vita, pc, 13, "@IF", [Insn('FLAG', 1040), Insn('END')], 0) # Talking to Chaleur
		copy_clause(vita, pc, 17, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Talking to Ursuline

	# Nurse station
	with ctx.get("t1540", tr) as (vita, pc):
		pc.includes = vita.includes
		vita = transform_npcs(vita, {
			41: copy(pc.npcs, vita.npcs[41]),
			42: copy(pc.npcs, vita.npcs[42]),
		})
		copy_clause(vita, pc, 1, "@IF:-1", 0, 3)

	# -''-
	with ctx.get("t1540_1", tr) as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			50: copy(pc.code, vita.code[50]),
			51: copy(pc.code, vita.code[51]),
			52: copy(pc.code, vita.code[52]),
		})
		copy_clause(vita, pc, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 5, "@IF", None, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Philia
		copy_clause(vita, pc, 6, "@IF", 0, 1) # Martha
		copy_clause(vita, pc, 7, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Meifa
		copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0) # Cecile

		# Fix bug when playing as Tio
		pc.code[51].insert(-2, Insn("CHAR_SET_POS", Char(0), (101750, 0, -1250), 0))

	# Hospital roof
	with ctx.get("t1600") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 14, "@IF", 0, 1) # Outside Research Ward

	# Bus
	with ctx.get("e0010", tr) as (vita, pc):
		vita = transform_funcs(vita, {
			19: copy(pc.code, vita.code[19]),
		}, include=0)
		copy_clause(vita, pc, 0, "@IF", 0, -1)

	# Station Street
	with ctx.get("c0000", tr) as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			55: copy(pc.code, vita.code[55]),
			60: copy(pc.code, vita.code[60]),
		}, include=0)
		# Talking to Lyd
		copy_condition(vita, pc, 6, "@IF", [Insn('FLAG', 1055), Insn('END')], 0)
		copy_clause(vita, pc, 6, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	# Central Square
	with ctx.get("c0100") as (vita, pc):
		pc.includes = vita.includes
	with ctx.get("c0100_1") as (vita, pc):
		# Talking to Kate
		copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 8, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	# Administrative District
	with ctx.get("c1100") as (vita, pc):
		pc.includes = vita.includes
		# Talking to Chroma
		copy_clause(vita, pc, 5, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_condition(vita, pc, 5, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], 0)

	# Library
	with ctx.get("c1130", tr) as (vita, pc):
		# This script is very different in the Geofront version, due to realphabetization
		pc.includes = vita.includes
		pc.chcp = vita.chcp
		vita = transform_funcs(vita, {
			2: copy(pc.code, vita.code[2]),
			56: copy(pc.code, vita.code[56]),
		}, include=0)
		# Add Ursuline
		vita = transform_npcs(vita, {
			11: copy(pc.npcs, vita.npcs[11]),
		})
		copy_clause(vita, pc, 2, "@IF:0", [Insn('FLAG', 1055), Insn('END')], -1)
		copy_clause(vita, pc, 2, "@IF:0", [Insn('FLAG', 1040), Insn('END')], -1)
		copy_clause(vita, pc, 3, 0)
		# Talking to Miles
		copy_clause(vita, pc, 14, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 14, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

	# Harbor District
	with ctx.get("c1200", tr) as (vita, pc):
		pc.includes = vita.includes
		vita = transform_funcs(vita, {
			59: copy(pc.code, vita.code[59]),
			60: copy(pc.code, vita.code[60]),
		}, include=0)
		# Talking to Cunha
		copy_clause(vita, pc, 12, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 12, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		# Talking to Ozelle
		copy_clause(vita, pc, 13, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 13, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		# Talking to Quine
		copy_condition(vita, pc, 16, "@IF:0", [Insn('FLAG', 1055), Insn('END')], 0)
		copy_condition(vita, pc, 16, "@IF:0", [Insn('FLAG', 1040), Insn('END')], 0)

	# Trinity
	with ctx.get("c1410") as (vita, pc):
		pc.includes = vita.includes
		# Talk to Wazy
		copy_clause(vita, pc, 6, "@IF:1", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 6, "@IF:1", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)
		# Talk to Azel
		copy_clause(vita, pc, 34, "@IF", [Insn('FLAG', 1055), Insn('END')], "@IF", 0, 0)
		copy_clause(vita, pc, 34, "@IF", [Insn('FLAG', 1040), Insn('END')], "@IF", 0, 0)

def quest57(ctx): # {{{1 Guest Lecturer for Sunday School (Continued)
	tr = translate.translator("quest57")
	ctx.copy_quest(57, tr)

	# Inside Cathedral
	with ctx.get("t4010") as (vita, pc):
		pc.includes = vita.includes
		vita.chcp = pc.chcp

		vita.npcs += [None, None]
		vita = transform_npcs(vita, vita_npcs := {
			len(vita.npcs)-1: 19,
			len(vita.npcs)-2: 20,
		})

		vita.code += [None, None, None]
		vita = transform_funcs(vita, vita_funcs := {
			len(vita.code)-1: 24,
			len(vita.code)-2: 25,
			len(vita.code)-3: 26,
		}, include=0)

		# Couta, Eugot, Boy, Boy, Girl
		for func in 21, 22, 27, 31, 32:
			copy_condition(vita, pc, func, -4)
		copy_clause(vita, pc, 28, "@IF:-1", 0, 0) # Girl
		copy_clause(vita, pc, 11, "@IF", [Insn('FLAG', 1536), Insn('END')], "@IF", 0, 0) # Marble

		names = [n.name for n in pc.npcs]

	vita = ctx._get_vita("t4010_1")
	vita = transform_npcs(vita, vita_npcs, own=False)
	vita = transform_funcs(vita, vita_funcs, include=0, own=False)
	ctx.pc_scripts["t4010_1"] = patch_t4010_1(names, vita)
	ctx._do_translate("t4010_1", tr)

patched_script = None
def patch_t4010_1(npc_names, raw):
	global patched_script
	if patched_script is not None:
		return deepcopy(patched_script)

	names = {}

	names["C_Self"] = insn.Char(254)
	names["C_None"] = insn.Char(255)
	names["C_Lloyd"] = insn.Char(257)
	names["C_Elie"] = insn.Char(258)
	names["C_Tio"] = insn.Char(259)
	names["C_Randy"] = insn.Char(260)

	nboy = 0
	ngirl = 0
	for i, n in enumerate(npc_names, 8):
		name = n.split()[-1]
		if name == "Boy": nboy += 1; name += str(nboy)
		if name == "Girl": ngirl += 1; name += str(ngirl)
		names["C_" + name] = insn.Char(i)

	# dump.dump(open("t4010_1.py", "wt"), raw, "verbose", names)

	import tempfile
	import subprocess
	with tempfile.NamedTemporaryFile(mode="w+t", prefix="t4010_1-", suffix=".py") as f:
		dump.dump(f, raw, "verbose", names)
		f.flush()
		subprocess.check_call(["patch", "-u", f.name, "text/t4010_1.patch"])
		patched_script = undump(Path(f.name).read_text())

	return patched_script

def quest58(ctx): # {{{1 Ultimate Bread Showdown!
	tr = translate.translator("quest58")
	ctx.copy_quest(58, tr)

	# West Street during festival?
	with ctx.get("c020c") as (vita, pc):
		pc.includes = vita.includes
		vita.code[0:0] = [None, None, None]
		copy_clause(vita, pc, 12, "@WHILE", 1, "@IF:1", 0, -1, 1, "@IF", 0, 0) # Bennet
		del vita.code[0:3]

	# Bakery interior
	with ctx.get("c0210") as (vita, pc):
		pc.includes = vita.includes
		copy_clause(vita, pc, 2, 0)
		copy_clause(vita, pc, 2, -2)
		copy_clause(vita, pc, 5, "@IF:0", 0, 0) # Oscar
		copy_condition(vita, pc, 5, "@IF:2", 0, 0, 1, "@IF", None, "@WHILE", 1, "@IF:1", 0, -1, 1, 1) # -''-
		copy_clause(vita, pc, 9, "@IF", 0, 0) # Morges, when not shopping
		copy_clause(vita, pc, 9, "@IF", 0, 1) # -''-
		copy_clause(vita, pc, 11, "@IF:1", 0, 0) # Bennet

	def traverse(insns):
		nfunc = []
		import re
		rx = re.compile(r"\{(#\d+F)\}")
		for x, i in enumerate(insns):
			if i.name == "TEXT_TALK" and rx.search(i.args[1]):
				if ctx.portraits:
					while x < len(insns)-2 \
							and insns[x+1].name == "TEXT_WAIT" \
							and insns[x+2].name == "TEXT_TALK" \
							and insns[x+2].args[0] == i.args[0]:
						i.args[1] += "{page}" + insns[x+2].args[1]
						del insns[x+1]
						del insns[x+1]
					i.args[1] = insn.Text(rx.sub(r"\1", i.args[1]))
				else:
					i.args[1] = insn.Text(rx.sub(r"", i.args[1]))

			if i.name == "IF":
				for _, b in i.args[0]:
					traverse(b)
			if i.name == "WHILE":
				traverse(i.args[1])
			if i.name == "SWITCH":
				for b in i.args[1].values():
					traverse(b)
			nfunc.append(i)
		insns[:] = nfunc

	pc = ctx.copy("c0210_1", tr)
	for func in pc.code:
		traverse(func)

	# Set flag 1107. Not sure what that does
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

	# Rename Luscious Orange → Zesty Orange. I don't really want to do that, but can't get any good translation otherwise.
	if ctx.en:
		# This is an ugly way to do it, but it's much easier than doing it "properly"
		frm = "Luscious Orange\0".encode("cp932")
		to = "Zesty Orange\0".encode("cp932")
		assert len(frm) >= len(to)
		data = (ctx.pcpath/"text_us/t_ittxt._dt").read_bytes()
		data2 = data.replace(frm, to.ljust(len(frm), b"\0"))
		if data != data2:
			(ctx.outpath/"text_us/t_ittxt._dt").write_bytes(data2)

# }}}1

# m0000, m0001, m0002, m0010, m0100, m0110, m0111, m0112, m3002, m3099, r2050, r2070, c1400, c140b
# contain minor, probably aesthetic, changes

# e0111 (EFF_LOAD typo) and e3000 (bgm in Lechter's singing)
# are slightly more important

def patch_misc(ctx): # {{{1
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

	# Fran saying "Oh! Hello, Lloyd!" when calling; asking the gang to find Colin,
	# and after exploring the Moon Temple.
	pos = miscTranslator.pos
	for script, func in ("c011c", 39), ("c011c", 40), ("r2050", 17):
		miscTranslator.pos = pos
		with ctx.get(script, miscTranslator) as (vita, pc):
			startP = next(i for i, a in enumerate(pc.code[func]) if a.name == "TEXT_SET_NAME") + 1
			startV = next(i for i, a in enumerate(vita.code[func]) if a.name == "TEXT_SET_NAME") + 1
			# In Geofront all three copies were absent, but in 2022 one of them was added — but without voice.
			# I'll just remove it and add my own.
			if pc.code[func][startP] in [
				Insn("TEXT_MESSAGE", 255, "{color 5}#18AOh! Hello, Lloyd!{wait}"),
				Insn("TEXT_MESSAGE", 255, "{color 5}#18Aあ、ロイドさん。{wait}"),
			]:
				del pc.code[func][startP:startP+2]

			pc.code[func][startP:startP] = vita.code[func][startV:startV+2]

# {{{1 Utils
def undump(src):
	import insn
	loc = {"data": None}
	exec(src, dict(insn.__dict__), loc)
	return loc["data"]

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
					import pprint
					for c2, b in who.args[0]:
						print(c2)
					raise ValueError("couldn't find case " + str(c))
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
	"""
	Sometimes Vita adds new branches that lead to the same dialogue as existing
	ones, in which case this dialogue is usually extracted to a function.

	When used together with transform_funcs, this function handles that case.
	"""
	n = len(pc.code)
	wh = get_(pc, "code", *path)
	pc.code.append(wh + [Insn('RETURN')])
	wh[:] = [Insn('CALL', (include, n))]
	return n

def copy(objects, obj):
	n = len(objects)
	objects.append(obj)
	return n

def transform_funcs(script, tr, include=0, own=True):
	"""
	In some cases functions are added, and not necessarily at the end. This
	means that function indices are sometimes different between PC and Vita.

	This function moves the relevant functions to the end of the Vita script and
	remaps indices to match, so that the scripts can be copied from Vita into PC.

	The reason the Vita scripts are remapped instead of the PC ones is to
	minimize diffs in the PC version.
	"""
	script = do_transform(script, { "func": {
		(include, k): (include, v)
		for k, v in to_permutation(tr).items()
	} })
	if own:
		permute(tr, script.code)
	return script

def transform_npcs(script, tr, own=True):
	"""
	Similar to transform_funcs, but concerning NPCs.
	"""
	script = do_transform(script, {"npc": {
		k+8: v+8
		for k, v in to_permutation(tr).items()
	}})
	if own:
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
	if not tr: return obj
	if isinstance(obj, insn.Translate):
		if getattr(obj, "translated", False):
			return obj
		tl = tr.get("translate")
		if tl is None:
			return obj
		elif tl is True:
			obj.translated = True
			return obj
		elif isinstance(tl, translate.BaseTranslator):
			obj = type(obj)(tl.translate(obj))
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
# }}}1

argp = argparse.ArgumentParser()
argp.add_argument("vitapath", type=Path, help="Path to the Vita data. This should likely be named \"data\"")
argp.add_argument("pcpath", type=Path, help="Path to the PC data. This should likely be named \"data\"")
argp.add_argument("-p", "--portraitpath", type=Path, help="Path to the More Portraits data. This should likely be named \"data\"")
argp.add_argument("outpath", type=Path, help="Directory to place the patched files into. This should be merged into the data directory.")
argp.add_argument("--minigame", action="store_true", help="Patches in dialogue for certain furniture in the headquarters. The minigames are not implemented, so it is simply a fade to black.")
argp.add_argument("--no-misc", dest="misc", action="store_false", help="Include only the quests, and not the miscellaneous minor patches")
argp.add_argument("-d", "--dump", dest="dumpdir", type=Path, help="Directory to place scenario dumps in, for all scenarios affected by the patch. Will be emptied.")
def __main__(vitapath, pcpath, portraitpath, outpath, minigame, misc, dumpdir):
	if not vitapath.is_dir():
		raise ValueError("vitapath must be a directory")
	if not pcpath.is_dir():
		raise ValueError("pcpath must be a directory")

	if outpath.exists():
		shutil.rmtree(outpath)

	outpath.mkdir(parents=True)
	(outpath/"scena").mkdir()
	(outpath/"text").mkdir()
	(outpath/"scena_us").mkdir()
	(outpath/"text_us").mkdir()

	for en in [True, False]:
		ctx = Context(vitapath, pcpath, outpath, en, portraits=portraitpath)

		if minigame:
			print("furniture_minigames")
			patch_furniture_minigames(ctx)

		print("timing")
		patch_timing(ctx)
		print("quest54")
		quest54(ctx)
		print("quest55")
		quest55(ctx)
		print("quest56")
		quest56(ctx)
		print("quest57")
		quest57(ctx)
		print("quest58")
		quest58(ctx)

		if misc:
			print("misc")
			patch_misc(ctx)

		print("save")
		ctx.save()

		if en and dumpdir is not None:
			print("dump")
			if dumpdir.exists():
				shutil.rmtree(dumpdir)
			dumpdir.mkdir(parents=True)

			for name, script in ctx.pc_scripts.items():
				with (dumpdir/name).with_suffix(".py").open("wt", encoding="utf-8") as f:
					dump.dump(f, script, "verbose")

	# Copy dizzy Mishy sprite for quest55
	name = "apl/ch50393.itc"
	(outpath/name).parent.mkdir(parents=True, exist_ok=True)
	(outpath/name).write_bytes((vitapath/name).read_bytes())

	# Copy cat-Tio image for quest57
	name = "visual/bu06900.itp"
	(outpath/name).parent.mkdir(parents=True, exist_ok=True)
	(outpath/name).write_bytes(Path("text/bu06900.itp").read_bytes())

if __name__ == "__main__":
	__main__(**argp.parse_args().__dict__)
