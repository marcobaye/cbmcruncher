#!/usr/bin/env python3

import sys

def load(filename):
    """load(str) -> int, bytes

    Read file and return as load address and actual body."""
    with open(filename, "rb") as fh:
        buf = fh.read(2 + 65536 + 1)    # load address + 64K is max
    size = len(buf)
    if size > 2 + 65536:
        raise Exception("File too long")
    if size < 2 + 1:
        raise Exception("File too short")
    load_address = int.from_bytes(buf[0:2], "little")
    return load_address, buf[2:size]

def save(filename, load_address, body):
    """save(str, int, bytes)

    Save file with a cbm-style load address."""
    with open(filename, "wb") as fh:
        fh.write(load_address.to_bytes(2, "little"))
        fh.write(body)

if __name__ == "__main__":
    sys.exit("This file is a library, it cannot be run.")
