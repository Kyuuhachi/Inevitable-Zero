import re
from pathlib import Path

DIALOGUE_RE = re.compile(r"^(?:(?:\{[^}]+\})*(?:#\d+[A-Z])+)?(.*?)(?:\{[^}]+\}|#\d+[A-Z])*\{wait\}$", re.DOTALL)
PATH = Path("text")

class BaseTranslator:
	def __init__(self):
		self.pos = 0
		self.lines = []

	def translate(self, string):
		if not string.strip():
			return string
		if string.endswith("\n"): # Menu
			return "".join(self._translate(s) + "\n" for s in string.splitlines())
		if string.endswith("{wait}"): # Dialogue
			lines = []
			for line in string.split("{page}"):
				line2, nsub = DIALOGUE_RE.subn(lambda m: self._translate(m[1]), line)
				assert nsub == 1
				lines.append(line2)
			return "\f".join(lines)
		return self._translate(string) # Other such as npc names or MENU_CUSTOM items

	def _translate(self, string):
		a, b = self.lines[self.pos]
		self.pos += 1
		assert a == string, (a, string)
		return b


class translator(BaseTranslator):
	def __init__(self, name):
		super().__init__()
		self.lines = self.load((PATH / name).with_suffix(".txt").read_text())

	@staticmethod
	def load(text):
		lines = []
		for p in text.splitlines():
			if not p: continue
			if p.startswith("\t"):
				lines[-1][1].append(p[1:])
			else:
				if not lines or lines[-1][1]:
					lines.append(([], []))
				lines[-1][0].append(p)

		return [("\n".join(a), "\n".join(b)) for a, b in lines]

class null_translator(BaseTranslator):
	def _translate(self, string):
		raise ValueError("This shouldn't have anything to translate")

class dump_translator(BaseTranslator):
	def __init__(self, name):
		super().__init__()
		self.file = (PATH / name).with_suffix(".txt").open("wt")

	def _translate(self, string):
		if self.pos == len(self.lines):
			self.lines.append((string, string))
			for line in string.splitlines():
				print(line, file=self.file)
			for line in string.splitlines():
				print("\t"+line, file=self.file)
			print(file=self.file)
		return super()._translate(string)

if False:
	translator = dump_translator
