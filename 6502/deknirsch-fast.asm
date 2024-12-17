;ACME 0.97
; TODO: add "d030 FIXME"s

!zone knirsch {
knirsch_start
	.zp_start = 2	; we need 33 bytes, but we inhibit IRQs and we restore them afterward...

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
.exchange_zp_bytes
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
; vars, should be in zp for speed reasons:
; this must be initialised from data given by caller:
.zp_packed_end	!wo 0
; these are then initialised from compressed data:
.zp_writeptr	!wo 0
.zp_shiftreg	!by 0
; these do not need init:
.zp_type	!by 0	; 0/1/2 to choose table row
.zp_length	!by 0	; sequence length
.zp_lit_len_hi = .zp_length	; (high byte only for literals,
.zp_rep_len_lo = .zp_length	; low byte only for repetitions!)
.zp_offset	!wo 0	; where current repetition comes from (in uncompressed data)
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
		php
		sei
		sec	; fix end pointer because the last three bytes are special
		sbc #3
		sta &.zp_packed_end
		bcs +
			dex
+		stx &.zp_packed_end + 1
; FIXME - set bit 0 of $d030
		; setup zp
		jsr .exchange_zp_bytes
			; now copy values from end of packed data to zp
			ldy #2
			lda (.zp_packed_end), y
			sta .zp_shiftreg
			dey;ldy#1
			lda (.zp_packed_end), y
			sta .zp_writeptr + 1
			sta .returnvalue_high	; prepare return value (new endoffile+1)
			dey;ldy#0
			lda (.zp_packed_end), y
			sta .zp_writeptr
			sta .returnvalue_low	; prepare return value (new endoffile+1)
			; actually unpack
			jsr @depacker_mainloop
		; restore zp
		jsr .exchange_zp_bytes
; FIXME - restore bit 0 of $d030
		; return pointer to end+1 of unpacked data
	.returnvalue_low = * + 1
		lda #$ff	; selfmod!
	.returnvalue_high = * + 1
		ldx #$ff	; selfmod!
		plp
		rts

; main depacker code
;-----------------------
--			inc .zp_offset + 1
			jmp ++

---- ; entered with C set
			; more table accesses:
			adc #0;inc .zp_offset	C is set!
			beq --
++			dey
			; use index to read bit count from table, then fetch bits
			; and calculate offset to copy sequence from:
@calc_offset ; enter with index in Y and zero in A
			ldx .zp_table, y	; read bit count
			; fetch that many bits into read pointer:
			beq ++
--				lsr .zp_shiftreg
				bne +
					sta @buf_a	; save
					sty @buf_y	; save
					jsr refill_shiftreg_keepsX
	@buf_a = * + 1	:		lda #$ff	; restore (selfmod)
	@buf_y = * + 1	:		ldy #$ff	; restore (selfmod)
+				rol	;.zp_offset
				rol .zp_offset + 1
				dex
				bne --
++			; are we at index 0/8/16? (i.e. done with table?)
	@final_index = * + 1
			cpy #$ff	; selfmod
			bne ----	; if taken, C is set
		;sta .zp_offset
; convert offset to actual read pointer by adding write pointer
; to it so we can read from the part we have already created:
		clc
		;lda .zp_offset
		adc .zp_writeptr
		sta .zp_offset
		lda .zp_offset + 1
		adc .zp_writeptr + 1
		sta .zp_offset + 1
; now repeat sequence (length is in 2..255 range):
		ldy .zp_rep_len_lo
		; copy 2 to 255 bytes:
		lda (.zp_offset), y	; first iteration is "unrolled" to save one branch (better overall than using selfmod+LDAABSY)
		dey
		sta (.zp_writeptr), y
--			lda (.zp_offset), y
			dey
			sta (.zp_writeptr), y
			bne --
@depacker_mainloop
		; get length of literal to copy
		; get first bit:
		lsr .zp_shiftreg
		bne +
			jsr refill_shiftreg_keepsX
+		lda #0
		bcc @part2_A_is_zero	; if first bit is zero, stop reading (no need to waste bit for end marker)
		; at this point we first need to clear lit_len
		; and then rotate C into it:
		;rol	; A holds lit_len_lo
		;rol .zp_lit_len_hi
		; but we know C is set so we'll get $0001
		sta .zp_lit_len_hi
		; get marker bit
		lsr .zp_shiftreg	; read another length bit?
		bne +
			jsr refill_shiftreg_keepsX
+		lda #1	; "restore" value we should have in A
		bcc ++
----			; get more length bits:
			lsr .zp_shiftreg
			bne +
				jsr tax_refill_shiftreg
				txa
+			rol
			rol .zp_lit_len_hi
			lsr .zp_shiftreg	; read another length bit?
			bne +
				jsr tax_refill_shiftreg
				txa
+			bcs ----
++		; we have length (up to 16 bits)
		; C is clear!
; copy literal sequence:
		tay;ldy .zp_lit_len_lo	; check low byte and setup Y as index (partial page is done first)
		beq @full_pages
		; prepare to copy partial page by fixing pointers
		sta @lengthbuf
		; read_pointer -= lowbyte(length):
		; CAUTION, reverse subtraction!
		;clc
		sbc .zp_packed_end
		eor #$ff	; fix result
		sta .zp_packed_end
		bcc ++
			dec .zp_packed_end + 1
++
		; write_pointer -= lowbyte(length):
		sec
		lda .zp_writeptr
	@lengthbuf = * + 1
		sbc #$ff	; selfmod!
		sta .zp_writeptr
		bcs @entry
		dec .zp_writeptr + 1
		jmp @entry

----			dec .zp_packed_end + 1
			dec .zp_writeptr + 1
			dey;ldy#$ff
--				lda (.zp_packed_end), y
				sta (.zp_writeptr), y
@entry				dey
				bne --
			lda (.zp_packed_end), y
			sta (.zp_writeptr), y
			; now Y is zero
@full_pages		; now do full pages (if any)
			dec .zp_lit_len_hi
			bpl ----
; is there a repetition to copy?
		tya;lda #0
@part2_A_is_zero
		sta .zp_type	; 0 means "use table for 2-byte sequences"
		; get length of sequence (minus two because lengths 0 and 1 make no sense):
----			lsr .zp_shiftreg
			bne +
				jsr tax_refill_shiftreg
				txa
+			rol
			beq @zero	; if first bit is zero, stop reading (no need to waste bit for end marker)
			bmi @check_for_eof	; 8 bit length -> stop reading bits (save marker bit)
			lsr .zp_shiftreg	; read another length bit?
			bne +
				jsr tax_refill_shiftreg
				txa
+			bcs ----
@long		; we have length
		inc .zp_type	; nonzero length -> type 1 -> "use table for 3-byte sequences"
@zero		;clc
		adc #2	; adjust length to correct value (8 bits only!)
		sta .zp_rep_len_lo
		; if length is 4 or more -> type 2 -> "use table for 4+ sequences"
		and #$fc
		beq ++
			inc .zp_type
++
; adjust write pointer by subtracting sequence length:
		sec
		lda .zp_writeptr
		sbc .zp_rep_len_lo
		sta .zp_writeptr
		bcs ++
			dec .zp_writeptr + 1
++
		; type is now 0, 1 or 2 (meaning sequence length is 2, 3 or >3)
		; fetch three bits to make index:
		lda .zp_type
		lsr .zp_shiftreg	; try to get first bit
		beq @fail_1
		rol	; put first bit
		lsr .zp_shiftreg	; try to get second bit
		beq @fail_2
		rol	; put second bit
		lsr .zp_shiftreg	; try to get third bit
		beq @fail_3
@put3rd		rol	; put third bit
		tay
		; index is now in 0..23 range:
		; sequence length 2: index 0..7
		; sequence length 3: index 8..15
		; sequence length 4 or more: index 16..23
		and #$f8
		sta @final_index
		lda #0
		sta .zp_offset + 1
		jmp @calc_offset	; needs index in Y and zero in A
;-----------------------
@fail_3		jsr tax_refill_shiftreg	; get third bit
		txa
		jmp @put3rd
;-----------------------
@fail_2		jsr tax_refill_shiftreg	; get second bit
		txa
		rol	; put second bit
		lsr .zp_shiftreg	; get third bit (cannot fail)
		jmp @put3rd
;-----------------------
@fail_1		jsr tax_refill_shiftreg	; get first bit
		txa
		rol	; put first bit
		lsr .zp_shiftreg	; get second bit (cannot fail)
		rol	; put second bit
		lsr .zp_shiftreg	; get third bit (cannot fail)
		jmp @put3rd	; put third bit
;-----------------------
@check_for_eof ; check for "end of data" marker:
		cmp #$fe	; $fd is largest valid value, $ff is "end of data" marker
		; by comparing to $fe we make sure we can return with C clear
		bcc @long	; go on
		rts	; we are done!
;=======================
tax_refill_shiftreg ; return new bit from shift register in C
		tax
refill_shiftreg_keepsX ; return new bit from shift register in C
		lda .zp_packed_end
		beq +
-		dec .zp_packed_end
		ldy #0
		lda (.zp_packed_end), y
		sec
		ror
		sta .zp_shiftreg
		rts	; return C

+		dec .zp_packed_end + 1
		jmp -
!warn "depacker code takes up ", * - knirsch_start, " bytes."
}
