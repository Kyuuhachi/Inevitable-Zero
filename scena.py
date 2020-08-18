import argparse
argp = argparse.ArgumentParser()
argp.add_argument("source", type=argparse.FileType("rb"))

def __main__(source):
	print(source)

if __name__ == "__main__":
	__main__(**argp.parse_args().__dict__)
