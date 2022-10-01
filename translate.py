import re
from pathlib import Path

# I don't want to have things like positioning (#P) and faces (#F) in the
# translation file, so this filters them out
DIALOGUE_RE = re.compile(r"^((?:\{[^}]+\}|#\d+[S])*)((?:#\d+[ABFPVWZ])*)(.*?)(\{wait\})$", re.DOTALL)
PATH = Path("text")

class BaseTranslator:
	def __init__(self):
		self.pos = 0
		self.lines = []
		self.lastExpect = object()

	def translate(self, string):
		if not string.strip():
			return string
		if string.endswith("\n"): # Menu
			return "".join(self._translate(s) + "\n" for s in string.splitlines())
		if string.endswith("{wait}"): # Dialogue
			lines = []
			for line in string.split("{page}"):
				line2, nsub = DIALOGUE_RE.subn(lambda m: m[2]+self._translate(m[1]+m[3])+m[4], line)
				assert nsub == 1
				lines.append(line2)
			return "{page}".join(lines)
		return self._translate(string) # Other such as npc names or MENU_CUSTOM items

	def _translate(self, string):
		a, b = self.lines[self.pos]
		if a == string:
			self.pos += 1
			return b
		else:
			if a is not self.lastExpect:
				print(f"Expected {a!r}")
				self.lastExpect = a
			print(string)
			print("\n".join("\t"+x for x in string.splitlines()))
			print()
			return string

	def __repr__(self):
		return f"{type(self).__name__}({self.pos} out of {len(self.lines)})"


class translator(BaseTranslator):
	def __init__(self, name):
		super().__init__()
		self.lines = self.load((PATH / name).with_suffix(".txt").read_text(encoding="utf-8"))
		self.lines.append((None, None))

	@staticmethod
	def load(text):
		lines = []
		for p in text.splitlines():
			p = p.split("##")[0].rstrip(" ")
			if not p: continue
			if p.startswith("\t"):
				lines[-1][1].append(p[1:])
			else:
				if not lines or lines[-1][1]:
					lines.append(([], []))
				lines[-1][0].append(p)

		return [("\n".join(a), "\n".join(b)) for a, b in lines]

class null_translator(BaseTranslator):
	def __init__(self):
		super().__init__()
		self.lines = [(None, None)]

class dump_translator(BaseTranslator):
	def __init__(self, name):
		super().__init__()
		self.file = (PATH / name).with_suffix(".txt").open("wt", encoding="utf-8")

	def _translate(self, string):
		if self.pos == len(self.lines):
			self.lines.append((string, string))
			for line in string.splitlines():
				assert line != ""
				assert line.replace("\u3000", "  ").replace("\n", " ").isprintable()
				print(line, file=self.file)
			for line in string.splitlines():
				print("\t"+line, file=self.file)
			print(file=self.file)
		return super()._translate(string)

if False:
	translator = dump_translator
