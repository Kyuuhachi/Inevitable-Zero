import kaiseki

import main
import argparse
argp = argparse.ArgumentParser()
argp.add_argument("file", type=argparse.FileType("rb"))
@main(argp=argp)
def __main__(source):
	print(source)
