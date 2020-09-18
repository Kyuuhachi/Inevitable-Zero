import re
DIALOGUE_RE = re.compile(r"^(?:(?:\{[^}]+\})*(?:#\d+[A-Z])+)?(.*?)(?:\{[^}]+\}|#\d+[A-Z])*\r$", re.DOTALL)

class translator:
	def __init__(self, name):
		self.name = name

	def translate(self, string):
		if not string.strip():
			return string
		if string.endswith("\n"): # Menu
			return "".join(self._translate(s) + "\n" for s in string.splitlines())
		if string.endswith("\r"): # Dialogue
			lines = []
			for line in string.split("\f"):
				line2, nsub = DIALOGUE_RE.subn(lambda m: self._translate(m[1]), line)
				assert nsub == 1
				lines.append(line2)
			return "\f".join(lines)
		return self._translate(string) # Other such as npc names or MENU_CUSTOM items

	def _translate(self, string):
		print(self.name, repr(string))
		return string

	def scope(self, name):
		return translator(self.name + "." + name)
