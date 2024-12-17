#!/usr/bin/env python3

import cbmutil
import packutil
import sys

def compress(kn, infile, outfile):
    """
    compress file to file
    """
    print("%s:" % infile)
    # load
    loadaddr, unpacked = cbmutil.load(infile)
    unpacked_size = len(unpacked)
    print("\tFile occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr, loadaddr + unpacked_size, unpacked_size))
    # pass to depacker
    print("\tCompressing...")
    packed = kn.pack(loadaddr, unpacked)
    packed_size = len(packed)
    print("\tCompressed file occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr - 16, loadaddr - 16 + packed_size, packed_size))
    print("\tSize change: %d." % (packed_size - unpacked_size))
    # save result
    if outfile:
        # format:
        # load address = load address of input file minus 16
        # packed data
        # writeptr (low, high)
        # shiftreg
        print("\tSaving to", outfile)
        cbmutil.save(outfile, loadaddr - 16, packed)
    else:
        print("\tNo output file name given, so not saving anything.")

def uncompress(kn, infile, outfile):
    """
    uncompress file to file
    """
    print("%s:" % infile)
    # load file and check
    loadaddr, packed = cbmutil.load(infile)
    packed_size = len(packed)
    print("\tFile occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr, loadaddr + packed_size, packed_size))
    if not packed.startswith(kn.HEADER):
        print("\tHeader:", packed[:2])
        sys.exit("Error: Invalid header.")
    print("\tFile has knirsch header.")
    # pass to depacker
    loadaddr, unpacked = kn.unpack(packed)
    unpacked_size = len(unpacked)
    print("\tUncompressed file occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr, loadaddr + unpacked_size, unpacked_size))
    print("\tSize change: %d." % (unpacked_size - packed_size))
    # save result
    if outfile:
        print("\tSaving to", outfile)
        cbmutil.save(outfile, loadaddr, unpacked)
    else:
        print("\tNo output file name given, so not saving anything.")

def main():
    if len(sys.argv) == 3:
        infile = sys.argv[2]
        outfile = None
    elif len(sys.argv) == 4:
        infile = sys.argv[2]
        outfile = sys.argv[3]
    else:
        print("This is a packer derived from the C64 program")
        print("\"Beta Dynamic Level Compressor v2.0\" aka \"betacrush\",")
        print("with some minor improvements.")
        print("Syntax: knirsch.py pack|unpack INPUTFILE [OUTPUTFILE]")
        print("\"pack\" outputs packed data with a lower load address.")
        print("\"unpack\" decompresses a packed file back to the original data.")
        print()
        sys.exit("Error: Wrong number of arguments.")
    if sys.argv[1] == "pack":
        compress(packutil.knirsch(), infile, outfile)
    elif sys.argv[1] == "pack2":
        compress(packutil.knirsch2(), infile, outfile)
    elif sys.argv[1] == "unpack":
        uncompress(packutil.knirsch(), infile, outfile)
    elif sys.argv[1] == "unpack2":
        uncompress(packutil.knirsch2(), infile, outfile)
    else:
        sys.exit("Error: Invalid mode given.")

if __name__ == "__main__":
    main()
