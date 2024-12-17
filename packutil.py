#!/usr/bin/env python3

import sys

DEBUG = True
DEBUG = False

def word(number):
    """
    helper function to convert number to 16-bit little-endian word
    """
    return number.to_bytes(2, "little")

class progress(object):
    """
    This is a helper class to visually indicate progress.
    """

    def __init__(self, maximum, is_bar = False):
        self.milestone = 0
        self.max = maximum
        self.is_bar = is_bar
        if is_bar:
            print(79 * "/", end="\r")
            self.barlength = 0

    def update(self, new_value):
        """
        check if new milestone has been reached. if so, update display.
        """
        if new_value >= self.milestone:
#            print(self.milestone, new_value, self.max)
            if self.is_bar:
                # display progress as horizontal bar
                chars = 79 * new_value // self.max
                self.milestone = (chars + 1) * self.max / 79
                print((chars - self.barlength) * "-", end="", flush=True)
                self.barlength = chars
                if self.barlength >= 79:
                    print()
            else:
                # display progress as percentage
                percentage = 100 * new_value // self.max
                self.milestone = (percentage + 1) * self.max / 100
                if percentage >= 100:
                    print("\t100%")
                else:
                    print("\t%d%%" % percentage, end="\r", flush=True)


class bbstream(object):
    """
    This is an abstraction of the bitstream-in-a-bytestream concept used by
    packers like betacrush.
    """

class cruncher(object):
    """
    This is the base class for betacrush and knirsch, containing everything but
    those parts where they are different.
    """

    # address bits to read for each length mode:
    TABLE_2 = (3, 1, 1, 1, 1, 0, 1, 1)  # sequence length 2
    TABLE_3 = (4, 1, 1, 1, 1, 1, 2, 2)  # sequence length 3
    TABLE_4 = (4, 1, 1, 1, 1, 2, 2, 2)  # sequence lengths 4 or more
    # maximum offsets for these modes:
    MAXOFFSET2 = 1143
    MAXOFFSET3 = 11247
    MAXOFFSET4 = 21999
    # first length without terminator
    MIN_UNTERMINATED_LENGTH = 128

    def find_rep(self, length, maxresult):
        """
        scan payload from current read index for repetition of given length
        """
        if self.SEPARATE_AREAS:
            start = length  # start looking for source area after target area (betacrush)
        else:
            start = 1   # start looking one byte up (knirsch)
        offset = self.payload.find(self.payload[self.read_idx:self.read_idx + length], self.read_idx + start, self.read_idx + start + maxresult + length)
        if offset == -1:
            return -1   # fail
        else:
            return offset - self.read_idx   # success (return offset relative to current position)

    def find_max_rep(self):
        """
        look for a repetition of data at current read pointer.
        """

        # first try length 4 to see if it makes sense to check for longer lengths:
        offset = self.find_rep(4, self.MAXOFFSET4)
        if offset != -1:
            found_length = 4
            found_offset = offset
            # now double length until test fails:
            while True:
                testlength = found_length << 1
                if testlength == self.FAIL_AT_LENGTH:
                    break
                offset = self.find_rep(testlength, self.MAXOFFSET4)
                if offset != -1:
                    found_length = testlength
                    found_offset = offset
                else:
                    break   # on failure, stop trying
            # "testlength" failed but "found_length" succeeded
            # try longer lengths using successive approximation:
            min_length = found_length   # new start value
            testbit = min_length >> 1   # first bit to check
            while testbit:
                testlength = min_length | testbit
                offset = self.find_rep(testlength, self.MAXOFFSET4)
                if offset != -1:
                    found_length = testlength
                    found_offset = offset
                    min_length = testlength
                testbit >>= 1
            assert found_length >= 4, "found_length should be at least 4, but is " + str(found_length) + "."
            return found_length, found_offset

        # no repetition with length 4 or greater, so check lengths 3 and 2:

        # try length 3
        offset = self.find_rep(3, self.MAXOFFSET3)
        if offset != -1:
            return 3, offset

        # try length 2
        offset = self.find_rep(2, self.MAXOFFSET2)
        if offset != -1:
            return 2, offset

        # fail:
        return 0, 0

    def shift_bit(self, bit):
        """
        shift a single bit into shift register
        """
        self.shiftreg <<= 1
        self.shiftreg |= bit
        if self.shiftreg & 256:
            self.packed.append(self.shiftreg & 255)
            self.shiftreg = 1   # marker bit

    def shift_length(self, length, terminate=True):
        """
        encode length in bitstream - CAUTION, bit order gets flipped!
        zero is encoded using a single zero bit,
        all other lengths are encoded by putting "1" bits between data bits and using a "0" bit as terminator.
        """
        if length == 0:
            self.shift_bit(0)
            return

        if terminate:
            self.shift_bit(0)   # "no more bits" terminator (betacrush and knirsch1 drop this for 8-bit repetition lengths)
        while True:
            self.shift_bit(length & 1)
            length >>= 1
            if length == 0:
                break
            self.shift_bit(1)   # "more bits follow"

    def check_literal(self):
        """
        if we have a literal sequence buffered, process it
        """
        if len(self.literal):
            if DEBUG:
                print(hex(self.loadaddr + self.read_idx - len(self.literal)), len(self.literal), "literal bytes")
            # first add actual literal (lower address)
            self.packed += self.literal
            # then add bits to bitstream (higher address)
            self.shift_length(len(self.literal))
            self.literal = bytearray()
            self.insert0 = False    # no need to add a dummy literal

    def encode_repetition(self, length, offset):
        """
        write info about repetition into bitstream
        """
        # select table according to length:
        if length == 2:
            table = self.TABLE_2
        elif length == 3:
            table = self.TABLE_3
        else:   # length 4 or greater
            table = self.TABLE_4
        # encode offset using table
        index = 0
        while True:
            bitcount = table[index]
            for i in range(bitcount):
                self.shift_bit(offset & 1)
                offset >>= 1
            if offset == 0:
                break
            index += 1
            offset -= 1
        # encode index
        self.shift_bit(index & 1)
        self.shift_bit((index >> 1) & 1)
        self.shift_bit((index >> 2) & 1)
        # encode length
        self.shift_length(length - 2, terminate = length - 2 < self.MIN_UNTERMINATED_LENGTH)

    def get_packed_byte(self):
        """
        internal function to deliver one byte of packed data
        """
        if self.packed_read_idx < 1:
            sys.exit("BUG: read_idx < 1.")
        self.packed_read_idx -= 1
        return self.packed[self.packed_read_idx]

    def get_bit(self):
        """
        return bit from shift register
        """
        if self.shiftreg == 1:
            self.shiftreg = self.get_packed_byte()
            self.shiftreg |= 256
        result = self.shiftreg & 1
        self.shiftreg >>= 1
        return result

    def copy_from_packed(self, length):
        """
        copy new byte sequence (input to output, "literal")
        """
        self.writeptr -= length
        if DEBUG and length:
            print(hex(self.writeptr), length, "literal bytes")
        while length:
            self.unpacked.append(self.get_packed_byte())
            length -= 1

    def copy_from_unpacked(self, length, offset):
        """
        repeat old byte sequence (output to output, "repetition")
        """
        self.writeptr -= length
        if DEBUG:
            print(hex(self.writeptr), length, "bytes from offset", offset)
#        if length > 255:
#            block = self.unpacked[-offset:length-offset]
#            block.reverse()
#            print("block with length", length)
#            print(block.decode())
        while length:
            self.unpacked.append(self.unpacked[-offset])
            length -= 1


SFXHEADER = b'\x10\x08\x95\x07\x9e2064 BETA\x00\xa0\x00x\x84\x01L'

class betacrush_packer(cruncher):
    """
    This is a re-implementation of the betacrush compression algorithm.
    """

    # betacrush/knirsch only allow 8-bit repetition lengths, so this allows us to pretend that testing for a 256-byte sequence fails:
    FAIL_AT_LENGTH = 256
    # in contrast to knirsch, this algo starts looking for repetitions at readptr + length instead of at readptr + 1
    SEPARATE_AREAS = True   # betacrush: start looking for source area after target area

    def pack(self, loadaddr, payload):
        """
        compress data block and return result
        """
        # setup internal state
        self.loadaddr = loadaddr
        self.payload = payload
        self.shiftreg = 1   # marker bit
        self.packed = bytearray()
        self.insert0 = False    # two repetitions without a literal inbetween? then insert a zero bit!
        # progress display:
        self.progress = progress(len(self.payload))
        # do the actual compression
        self.read_idx = 0
        self.literal = bytearray()
        while self.read_idx < len(self.payload):
            # kluge to get around a bug in the depacker (part 1):
            # (just like the original asm version, this is not a full fix. it only works if more data is coming)
            # CAUTION: the original asm version seems to grow the literal at the other side!
            if len(self.literal) and ((len(self.literal) & 511) == 0):
                length = 0  # pretend there is no repetition to make sure length of literal increases
            else:
                length, offset = self.find_max_rep()
            if length:
                # we found a repetition
                # first check for buffered literal
                self.check_literal()
                # add dummy literal?
                if self.insert0:
                    self.shift_bit(0)
                # then process current repetition
                if DEBUG:
                    print(hex(self.loadaddr + self.read_idx), length, "bytes from offset", offset)
                self.encode_repetition(length, offset - length) # the algo counts offset from *after* length, which is suboptimal...
                self.read_idx += length
                self.insert0 = True # if another repetition follows, insert dummy literal
            else:
                # no repetition found, so add one byte to literal and try again
                self.literal.append(self.payload[self.read_idx])
                self.read_idx += 1
            # show progress
            self.progress.update(self.read_idx)
        # part 2 of kluge:
        if len(self.literal) and ((len(self.literal) & 511) == 0):
            sys.exit("Sorry, cannot pack this file as depacking it would trigger a bug in the depacker!")
        self.check_literal()
        return self.packed, self.shiftreg

# FIXME - move into packer class!
def make_sfx(loadaddr, packed, shiftreg, uncompressed_length):
    """
    helper function to generate self-extracting version
    """
    result = bytearray()
    result += SFXHEADER
    result += word(loadaddr + len(SFXHEADER) + 2 + len(packed) + 262)   # add target address for JMP to relocator
    result += packed[0x27:] # add main part of packed data
    result += packed[:0x27] # add first 0x27 bytes of packed data
    # add data for zp (0x1d bytes):
    result.append(shiftreg)
    result += word(len(packed))
    result += word(loadaddr + uncompressed_length)
    result += bytearray.fromhex("a5 61 d0 02 c6 62 c6 61 ad")
    result += word(loadaddr - 16 + len(packed))
    result += bytearray.fromhex("60")   # rts
    result += bytearray.fromhex("19 09 08 09 21 09 09 12 21 09 0a 12")  # tables
    # add depacker:
    result += bytearray.fromhex("""
 98 85 4e 85 50 20 c3 01 2a d0 02 90 0c 26 50 20 c3 01 b0 f1 85 4f 20 88 01 98 85 51 85 52 20 c3
 01 2a f0 09 30 05 20 c3 01 b0 f3 e6 4e 69 02 85 4f 29 fc f0 02 e6 4e a2 03 20 c3 01 26 4e ca d0
 f8 a5 4e 4a aa b5 64 b0 03 4a 4a 4a 29 07 aa f0 0a 20 c3 01 26 51 26 52 ca d0 f6 a5 4e 29 07 f0
 0a e6 51 d0 02 e6 52 c6 4e 10 d6 18 a5 56 65 51 85 51 a5 57 65 52 85 52 a5 51 d0 02 c6 52 c6 51
 e6 4e 20 9b 01 4c 00 01 38 a5 54 e5 4f 85 51 85 54 a5 55 e9 00 85 52 e5 50 85 55 a4 4f f0 19 38
 a5 56 e5 4f 85 56 b0 02 c6 57 b1 51 a6 4e d0 03 20 58 00 88 91 56 d0 f2 c4 50 f0 06 c6 52 c6 50
 10 e6 60 46 53 d0 15 c4 54 d0 06 c4 55 f0 0e c6 55 c6 54 48 20 58 00 38 6a 85 53 68 60 c6 01 58
 20 bf e3 20 59 a6 4c b1 a7
        """)
    # add relocator:
    block2 = loadaddr + len(SFXHEADER) + 2 + len(packed)
    block1 = block2 - 0x27
    block3 = block2 + 0x1d
    result += bytearray.fromhex("c0 27 b0 06 b9")
    result += word(block1)
    result.append(0x99) # sta abs,y
    result += word(loadaddr - 16)
    result += bytearray.fromhex("c0 1d b0 06 b9")
    result += word(block2)
    result += bytearray.fromhex("99 53 00 b9")
    result += word(block3)
    result += bytearray.fromhex("99 00 01 c8 d0 e3 4c 00 01")
    return result

class betacrush_depacker(cruncher):
    """
    This class does what the sfx code in the file did.
    """

    def unpack(self, packed, shiftreg, endplus1):
        """
        do the work and uncompress the data block
        """
        self.packed = packed
        self.packed_read_idx = len(packed)
        self.shiftreg = shiftreg
        self.writeptr = endplus1
        self.unpacked = bytearray()
        while True:
# part 1: start by copying a literal from packed data:
            # get length of sequence
            length = 0
            while True:
                length <<= 1
                length |= self.get_bit()
                if length == 0:
                    break   # if first bit is zero, stop reading (no need to waste bit for end marker)
                # read another length bit?
                if self.get_bit() == 0:
                    break
            # copy bytes
            self.copy_from_packed(length)
            # are we done?
            if self.shiftreg == 1 and self.packed_read_idx == 0:
                # asm code jumps to basic "RUN" in this case...
                break
# part 2: after copying a literal from packed we must copy a repetition from unpacked:
            length = 0
            while True:
                length <<= 1
                length |= self.get_bit()
                if length == 0:
                    break   # if first bit is zero, stop reading (no need to waste bit for end marker)
                if length >= self.MIN_UNTERMINATED_LENGTH:
                    break   # 8 bit length -> stop reading bits (save a bit by not having a terminating zero)
                # read another length bit?
                if self.get_bit() == 0:
                    break
            # fix length to real value
            length += 2
            # choose correct table
            if length == 2:
                table = self.TABLE_2
            elif length == 3:
                table = self.TABLE_3
            else:
                table = self.TABLE_4
            # get three bits to determine table index
            index = self.get_bit() << 2
            index |= self.get_bit() << 1
            index |= self.get_bit()

            # build offset
            offset = 0
            while True:
                bitcount = table[index]
                while bitcount:
                    offset <<= 1
                    offset |= self.get_bit()
                    bitcount -= 1
                if index == 0:
                    break
                offset += 1
                index -= 1
            # copy bytes
            self.copy_from_unpacked(length, offset + length)
        # ...loop exits via break
        # re-order and return uncompressed data:
        self.unpacked.reverse()
        return self.unpacked

# FIXME - move into depacker class!
def un_sfx(loadaddr, body):
    """
    split sfx file into parts and return those
    """
    # part 1 is the BASIC/ASM header JMPing to part 6 (ignored)
    packed2 = body[0x17:-333]   # part 2 is packed data (mostly, first 0x27 bytes are missing)
    parts3456 = body[-333:]  # the last 333 bytes are the rest:
    packed1 = parts3456[:0x27]   # part 3 is the first 0x27 bytes of packed data
    zpblock = parts3456[0x27:0x27 + 0x1d]    # part 4 is a block copied into zeropage
    # part 5 is the depacker code (ignored)
    # part 6 is the relocator code for parts 3, 4 and 5 (ignored)
    packed = packed1 + packed2  # all packed data (supposed to be located at "loadaddr - 16")
    shiftreg = zpblock[0]
    # do some checks:
    compressed_size = int.from_bytes(zpblock[1:3], "little")
    if compressed_size != len(packed):
        sys.exit("Error: Length of compressed part does not match.")
    writeptr = int.from_bytes(zpblock[3:5], "little")
    readptr_packed = int.from_bytes(zpblock[14:16], "little")
    if readptr_packed != loadaddr - 16 + len(packed):
        sys.exit("Error: End address of compressed part does not match.")
    return packed, shiftreg, writeptr

class knirsch(cruncher):
    """
    This is a compression algorithm derived from betacrush, but with a few modifications.
    """

    # betacrush/knirsch only allow 8-bit repetition lengths, so this allows us to pretend that testing for a 256-byte sequence fails:
    FAIL_AT_LENGTH = 256
    # in contrast to betacrush, this algo starts looking for repetitions at readptr + 1 instead of at readptr + length
    SEPARATE_AREAS = False  # knirsch: start looking one byte up
    END_LENGTH = 255    # this repetition length indicates end-of-data...
    HEADER = b"\x7f\xff"    # ...and creates this file header

    def create_end_marker(self):
        self.shift_length(self.END_LENGTH, terminate = True)    # forcing termination gives us a 16-bit "file header" (7f ff)

    def pack(self, loadaddr, payload):
        """
        compress data block and return result
        """
        # setup internal state
        self.loadaddr = loadaddr
        self.payload = payload
        self.shiftreg = 1   # marker bit
        self.packed = bytearray()
        self.insert0 = True # two repetitions without a literal inbetween? then insert a zero bit!
        # (we start with True because file header == end marker == special "repetition"
        # progress display:
        self.progress = progress(len(self.payload))
        # do the actual compression
        self.read_idx = 0
        self.literal = bytearray()
        # create end marker, doubling as file header
        self.create_end_marker()
        while self.read_idx < len(self.payload):
            length, offset = self.find_max_rep()
            if length:
                # we found a repetition
                # first check for buffered literal
                self.check_literal()
                # add dummy literal?
                if self.insert0:
                    self.shift_bit(0)
                # then process current repetition
                if DEBUG:
                    print(hex(self.loadaddr + self.read_idx), length, "bytes from offset", offset)
                self.encode_repetition(length, offset - 1)
                self.read_idx += length
                self.insert0 = True # if another repetition follows, insert dummy literal
            else:
                # no repetition found, so add one byte to literal and try again
                self.literal.append(self.payload[self.read_idx])
                self.read_idx += 1
            # show progress
            self.progress.update(self.read_idx)
        self.check_literal()
        # output format:
        # packed data
        # writeptr (low, high)
        # shiftreg
        self.packed += word(loadaddr + len(payload))
        self.packed.append(self.shiftreg)
        return self.packed

    def unpack(self, payload):
        """
        uncompress data block and return resulting load address and body
        """
        self.packed = payload[:-3]
        endplus1 = int.from_bytes(payload[-3:-1], "little")
        self.writeptr = endplus1
        self.shiftreg = payload[-1]
        self.packed_read_idx = len(self.packed)
        self.unpacked = bytearray()
        while True:
# part 1: start by copying a literal from packed data:
            # get length of sequence
            length = 0
            while True:
                length <<= 1
                length |= self.get_bit()
                if length == 0:
                    break   # if first bit is zero, stop reading (no need to waste bit for end marker)
                # read another length bit?
                if self.get_bit() == 0:
                    break
            # copy bytes
            self.copy_from_packed(length)
# part 2: after copying a literal from packed we must copy a repetition from unpacked:
            length = 0
            while True:
                length <<= 1
                length |= self.get_bit()
                if length == 0:
                    break   # if first bit is zero, stop reading (no need to waste bit for end marker)
                if length >= self.MIN_UNTERMINATED_LENGTH:
                    break   # stop reading bits (save a bit by not having a terminating zero)
                # read another length bit?
                if self.get_bit() == 0:
                    break
            # are we done? (length 255 indicates end of data)
            if length >= self.END_LENGTH:
                break
            # fix length to real value
            length += 2
            # choose correct table
            if length == 2:
                table = self.TABLE_2
            elif length == 3:
                table = self.TABLE_3
            else:
                table = self.TABLE_4
            # get three bits to determine table index
            index = self.get_bit() << 2
            index |= self.get_bit() << 1
            index |= self.get_bit()

            # build offset
            offset = 0
            while True:
                bitcount = table[index]
                while bitcount:
                    offset <<= 1
                    offset |= self.get_bit()
                    bitcount -= 1
                if index == 0:
                    break
                offset += 1
                index -= 1
            # copy bytes
            self.copy_from_unpacked(length, offset + 1)
        # ...loop exits via break
        # re-order and return uncompressed data:
        self.unpacked.reverse()
        loadaddr = endplus1 - len(self.unpacked)
        return loadaddr, self.unpacked

class knirsch2(knirsch):
    """
    This is like knirsch, but can handle repetitions of more than 255 bytes.
    """

    # repetition lengths can use 16 bits:
    FAIL_AT_LENGTH = 65536
    # first length without terminator
    MIN_UNTERMINATED_LENGTH = 32768
    END_LENGTH = 65535  # this repetition length indicates end-of-data...
    HEADER = b"\xff\xff\xff"    # ...and creates this file header

    def create_end_marker(self):
        # create 24-bit header (bf ff ff)
        self.shift_length(self.END_LENGTH, terminate = False)   # termination would result in same header as knirsch1!
        # alternative: 33-bit header (bf ff ff ff ...)
        #self.shift_bit(1)
        #self.shift_length(self.END_LENGTH, terminate = True)

if __name__ == "__main__":
    sys.exit("This file is a library, it cannot be run.")
