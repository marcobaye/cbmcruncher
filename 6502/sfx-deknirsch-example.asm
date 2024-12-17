;ACME 0.97

ENTRYPOINT = $0c00

	*=$0801
	!wo line2, 2024
	!pet $9e, "2061", 0
line2	!wo 0
	*=2061
		sei
		lda #0	; all RAM
		sta $01
		lda #<end_of_compressed
		ldx #>end_of_compressed
		jsr knirsch_unpack	; returns XXAA = end+1 of unpacked data, but we do not care
		dec $01;lda #std;sta $01
		cli
		jmp ENTRYPOINT

	!src "deknirsch-fast.asm"

	!if * > ENTRYPOINT - 16 {
		!error "start address of packed data is too high - is the depacker too long?"
	}

	!bin "packed",, 2
end_of_compressed
