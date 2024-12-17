#!/usr/bin/env python3

import cbmutil
import packutil
import sys

def compress(infile, outfile, mode):
    """
    compress file to file
    """
    print("%s:" % infile)
    # load
    loadaddr, body = cbmutil.load(infile)
    body_size = len(body)
    print("\tFile occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr, loadaddr + body_size, body_size))
    # pass to depacker
    print("\tCompressing...")
    bc = packutil.betacrush_packer()
    packed, shiftreg = bc.pack(loadaddr, body)
    # CAUTION: the +3 bytes in the next line are for the shift register and the initial write pointer
    print("\tCompressed file occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr - 16, loadaddr - 16 + len(packed) + 3, len(packed) + 3))
    print("\tData change:", len(packed) + 3 - body_size)
    # save result
    if outfile:
        compressed_left = len(packed)
        writeptr = loadaddr + body_size
        if mode == "sfx":
            print("\tMaking SFX file...")
            packed = packutil.make_sfx(loadaddr, packed, shiftreg, len(body))
            print("\tSFX file occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr, loadaddr + len(packed), len(packed)))
            print("\tTotal file change:", len(packed) - len(body))
            if len(packed) >= len(body):
                print("\t\tFile did not shrink, using uncompressed version instead!")
                packed = body
            print("\tSaving to", outfile)
            cbmutil.save(outfile, loadaddr, packed)
        elif mode == "mem":
            print("\tMaking MEM (in-place) file...")
            # format:
            # same load address as input file
            # packed data
            # shiftreg
            # compressed_left (low, high)
            # writeptr (low, high)
            packed.append(shiftreg)
            packed += packutil.word(compressed_left)
            packed += packutil.word(writeptr)
            print("\tSaving to", outfile)
            cbmutil.save(outfile, loadaddr, packed)
        elif mode == "load":
            print("\tMaking LOAD file...")
            # format:
            # no load address!
            # writeptr (high, low)
            # compressed_left (high, low)
            # shiftreg
            # data (reverse, i.e. from high addresses to low addresses)
            # a single zero byte (who knows why)
            packed.append(shiftreg)
            packed += packutil.word(compressed_left)
            packed += packutil.word(writeptr)
            packed.reverse()
            packed.append(0)
            print("\tSaving to", outfile)
            # file has no load address, so write directly instead of using "cbmutil.save":
            with open(outfile, "wb") as fh:
                fh.write(packed)
        else:
            sys.exit("BUG: invalid mode")
    else:
        print("\tNo output file name given, so not saving anything.")

def uncompress(infile, outfile):
    """
    uncompress file to file
    """
    print("%s:" % infile)
    # load file and check
    loadaddr, body = cbmutil.load(infile)
    file_size = len(body)
    print("\tFile occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr, loadaddr + file_size, file_size))
#    if loadaddr != LOADADDR:
#        sys.exit("Error: Load address should be 0x%x." % LOADADDR)
    if body.startswith(packutil.SFXHEADER):
        # get parts of self-extracting file:
        print("\tFile has betacrush self-extract header.")
        packed, shiftreg, unpacked_end = packutil.un_sfx(loadaddr, body)
    else:
        print("\tHeader:", body[:len(packutil.SFXHEADER)])
        sys.exit("Error: Invalid header.")
#    cbmutil.save(outfile, loadaddr - 16, packed)
    uncompressed_size = unpacked_end - loadaddr
#    print("\tShift reg: 0x%x" % shiftreg)
    print("\tUncompressed file occupies 0x%x..0x%x (load address + %d bytes)." % (loadaddr, unpacked_end, unpacked_end - loadaddr))
    # CAUTION: the +3 bytes in the next line are for the shift register and the initial write pointer
    print("\tData change: %d, total file change: %d." % (len(packed) + 3 - uncompressed_size, file_size - uncompressed_size))
    # now pass to depacker
    depack = packutil.betacrush_depacker()
    result = depack.unpack(packed, shiftreg, unpacked_end)
    if loadaddr + len(result) != unpacked_end:
        sys.exit("Error: Uncompressed length does not match.")
    # save result
    if outfile:
        print("\tSaving to", outfile)
        cbmutil.save(outfile, loadaddr, result)
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
        print("This is a re-implementation of the C64 program")
        print("\"Beta Dynamic Level Compressor v2.0\" aka \"betacrush\".")
        print("Syntax: betacrush.py sfx|mem|load|unpack INPUTFILE [OUTPUTFILE]")
        print("\"sfx\" creates a self-extracting executable.")
        print("\"mem\" outputs packed data with the same load address.")
        print("\"load\" creates a data file that must be read byte by byte using a special loader.")
        print("\"unpack\" decompresses an SFX file back to the original data.")
        print()
        sys.exit("Error: Wrong number of arguments.")
    if sys.argv[1] == "sfx":
        compress(infile, outfile, "sfx")
    elif sys.argv[1] == "mem":
        compress(infile, outfile, "mem")
    elif sys.argv[1] == "load":
        compress(infile, outfile, "load")
    elif sys.argv[1] == "unpack":
        uncompress(infile, outfile)
    else:
        sys.exit("Error: Invalid mode given.")

if __name__ == "__main__":
    main()
