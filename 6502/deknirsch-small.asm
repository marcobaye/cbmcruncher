;ACME 0.97
; TODO: add "d030 FIXME"s

!zone knirsch {
	.zp_start = 2	; we need 43 bytes, but we inhibit IRQs and we restore them afterward...

; calling code should do:
!if 0 {
		...
		jsr destroy_header
		jsr file_load
		jsr check_for_header
		b.. not_this_packer
		lda runptr_load	; get pointer to end of file
		ldx runptr_load + 1
		jsr knirsch_unpack	; returns with XXAA = end+1 of unpacked data
		; TODO: store A/X to zp as real end address
		; TODO: fix start address of file to correct value
		...
}
.exchange_43_zp_bytes
		ldx #.block_for_zp_end - .block_for_zp_start - 1
--			lda .zp_start, x
			ldy .block_for_zp_start, x
			sta .block_for_zp_start, x
			sty .zp_start, x
			dex
			bpl --
		rts

.block_for_zp_start
!pseudopc .zp_start {
; this table should be placed in zp for speed reasons
; (original depacker used 12 bytes with two values each, we use 24 bytes for speed reasons)
.zp_table	!by 3, 1, 1, 1, 1, 0, 1, 1	; table for sequence length 2, max offset is 1143
		!by 4, 1, 1, 1, 1, 1, 2, 2	; table for sequence length 3, max offset is 11247
		!by 4, 1, 1, 1, 1, 2, 2, 2	; table for sequence lengths >= 4, max offset is 21999
; this routine should run in zp for speed reasons:
.get_packed_byte_keepsXY
		lda+1 .packed_end
		bne ++
			dec+1 .packed_end + 1
++		dec+1 .packed_end
	.packed_end = * + 1
		lda $ffff	; selfmod, must be initialised from compressed data!
		rts
; vars, should be in zp for speed reasons:
.zp_start_of_3_init
; these must be initialised from compressed data:
.zp_writeptr	!wo 0
.zp_shiftreg	!by 0
; these do not need init:
.zp_index	!by 0	; 0..23 select table entry
.zp_lit_len_hi	!by 0	; sequence length (high byte only for literals,
.zp_rep_len_lo = .zp_lit_len_hi	; low byte only for repetitions!)
.zp_readptr	!wo 0	; where current repetition comes from (points to uncompressed data!)
}
.block_for_zp_end

; the depacker needs this information:
;	end of compressed data (must be passed explicitly, if in doubt use LOAD's run ptr in zp!)
;	end of *uncompressed* data (writeptr!) and initial state of shift register:
;		-> these are just appended to compressed data!
;	caller must make sure that start of compressed data is not in area of uncompressed data.
;	if lower, it must be *at least* 16 bytes lower (TODO - check how much is really needed!)
knirsch_unpack ; enter with XXAA = end+1 of packed data
		; store end pointer in our routine so we can read bytes off the end
		sta &.packed_end
		stx &.packed_end + 1
		php
		sei
		; setup zp
		jsr .exchange_43_zp_bytes
			; now copy values from end of packed data to zp
			ldx #2	; copy three bytes (shift reg, write ptr for unpacked)
--				tay	; remember value of previous iteration for later (see below)
				jsr .get_packed_byte_keepsXY
				sta .zp_start_of_3_init, x
				dex
				bpl --
			; prepare return value (new endoffile+1)
	!if .zp_writeptr != .zp_start_of_3_init { !error "someone broke an optimization" }
			;lda .zp_writeptr
			;ldy .zp_writeptr + 1
			sta .returnvalue_low
			sty .returnvalue_high
			; actually unpack
			ldy #0
			jsr @depacker_mainloop
		; restore zp
		jsr .exchange_43_zp_bytes
		plp
		; return pointer to end+1 of unpacked data
	.returnvalue_low = * + 1
		lda #$ff	; selfmod!
	.returnvalue_high = * + 1
		ldx #$ff	; selfmod!
		rts

; main depacker code
;-----------------------
----			; more table accesses:
			inc .zp_readptr
			bne ++
				inc .zp_readptr + 1
++			dec .zp_index
@calc_offset		; use index to read bit count from table, then fetch bits
			; and calculate offset to copy sequence from:
			ldx .zp_index
			lda .zp_table, x	; read bit count
			tax
			; fetch that many bits into read pointer:
			beq ++
--				jsr .get_bit_keepsAX
				rol .zp_readptr
				rol .zp_readptr + 1
				dex
				bne --
++			; are we at index 0/8/16? (i.e. done with table?)
			lda .zp_index
			and #7
			bne ----
; adjust write pointer by subtracting sequence length:
		sec
		lda .zp_writeptr
		sbc .zp_rep_len_lo
		sta .zp_writeptr
		bcs ++
			dec .zp_writeptr + 1
++
; read pointer only contains offset, so add write pointer
; to it so we can read from the part we have already created:
		clc
		lda .zp_readptr
		adc .zp_writeptr
		sta .zp_readptr
		lda .zp_readptr + 1
		adc .zp_writeptr + 1
		sta .zp_readptr + 1
; now repeat sequence (length is in 2..255 range):
		ldy .zp_rep_len_lo
		; copy up to 255 bytes:
--			lda (.zp_readptr), y
			dey
			sta (.zp_writeptr), y
			bne --
@depacker_mainloop ; call with Y=0!
; is there a literal to copy?
		sty .zp_lit_len_hi
		tya;lda #0	; A holds lit_len_lo!
		; get length of sequence:
		; get first bit:
		jsr .get_bit_keepsAX
		rol
		beq @part2_A_is_zero	; if first bit is zero, stop reading (no need to waste bit for end marker)
		rol .zp_lit_len_hi
		jsr .get_bit_keepsAX	; read another length bit?
		bcc ++
----			; get more length bits:
			jsr .get_bit_keepsAX
			rol
			rol .zp_lit_len_hi
			jsr .get_bit_keepsAX	; read another length bit?
			bcs ----
++		; we have length (up to 16 bits)
; copy literal sequence:
		tay;ldy .zp_lit_len_lo	; check low byte, partial page is done first
		beq ++++
		; copy partial page
		sta @lengthbuf	; FIXME - check if we can do a reverse subtraction here!
		sec
		lda .zp_writeptr
	@lengthbuf = * + 1
		sbc #$ff	; selfmod!
		sta .zp_writeptr
		bcs ++
----			dec .zp_writeptr + 1
++
--			jsr .get_packed_byte_keepsXY
			dey
			sta (.zp_writeptr), y
			bne --
		; now Y is zero
++++		; now do full pages (if any)
		dec .zp_lit_len_hi
		bpl ----
; is there a repetition to copy?
		tya;lda #0
@part2_A_is_zero
		sta .zp_index	; index 0 means "use table for 2-byte sequences"
		sta .zp_readptr
		sta .zp_readptr + 1
		; get length of sequence (minus two because lengths 0 and 1 make no sense):
----			jsr .get_bit_keepsAX
			rol
			beq @zero	; if first bit is zero, stop reading (no need to waste bit for end marker)
			bmi @check_for_eof	; 8 bit length -> stop reading bits (save marker bit)
			jsr .get_bit_keepsAX	; read another length bit?
			bcs ----
@long		; we have length
		inc .zp_index	; nonzero length -> index = 1 -> "use table for 3-byte sequences"
@zero		;clc
		adc #2	; adjust length to correct value (8 bits only!)
		sta .zp_rep_len_lo
		; if length is 4 or more -> index = 2 -> "use table for 4+ sequences"
		and #$fc
		beq ++
			inc .zp_index
++		; index is now 0, 1 or 2 (meaning sequence length is 2, 3 or >3)
		ldx #3	; fetch three bits into index:
----			jsr .get_bit_keepsAX
			rol .zp_index
			dex
			bne ----
		; index is now in 0..23 range:
		; sequence length 2: index 0..7
		; sequence length 3: index 8..15
		; sequence length 4 or more: index 16..23
		jmp @calc_offset
;-----------------------
@check_for_eof ; check for "end of data" marker:
		cmp #$fe	; $fd is largest valid value, $ff is "end of data" marker
		; by comparing to $fe we make sure we can return with C clear
		bcc @long	; go on
		rts	; we are done!
;=======================
.get_bit_keepsAX ; return new bit from shift register in C
		lsr .zp_shiftreg
		beq @empty	; inverting the branch would lose speed...
			rts	; 7/8
@empty		; 1/8
		tay
		jsr .get_packed_byte_keepsXY
		sec
		ror
		sta .zp_shiftreg
		tya
		rts	; return C
}
