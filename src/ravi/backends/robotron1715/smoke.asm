; Original RAVI diagnostic for the plain PC1715, stock V.24 boot path.
; Load/enter at 4000h. Uses 8000h..80FFh for destructive RAM tests.
; No stack or ROM calls. Interrupts disabled. Keeps ROM's SIO/CTC settings.
; Test each byte with 00, FF, 55, AA, then an address pattern across the page.
; This is a small smoke test, NOT a full RAM/address-bus qualification.
        org 04000h
        di
        ld hl,08000h
byte_test:
        xor a
        ld (hl),a
        cp (hl)
        jp nz,failed
        ld a,0ffh
        ld (hl),a
        cp (hl)
        jp nz,failed
        ld a,055h
        ld (hl),a
        cp (hl)
        jp nz,failed
        ld a,0aah
        ld (hl),a
        cp (hl)
        jp nz,failed
        ld (hl),l
        inc l
        jr nz,byte_test
address_test:
        ld a,l
        cp (hl)
        jp nz,failed
        inc l
        jr nz,address_test
        ld hl,ready_text
        jr print
failed:
        ld hl,fail_text
print:
        ld a,(hl)
        or a
        jr z,printed
        ld c,a
wait_tx:
        xor a
        out (00fh),a
        in a,(00fh)
        bit 2,a
        jr z,wait_tx
        ld a,c
        out (00dh),a
        inc hl
        jr print
printed:
        ; C contains last emitted byte: LF on success, '!' on failure.
        ld a,c
        cp '!'
        jr z,stop
receive:
        xor a
        out (00fh),a
        in a,(00fh)
        bit 0,a
        jr z,receive
        in a,(00dh)
        ld c,a
wait_echo:
        xor a
        out (00fh),a
        in a,(00fh)
        bit 2,a
        jr z,wait_echo
        ld a,c
        out (00dh),a
        jr receive
stop:
        halt
        jr stop
ready_text:
        db 'R1715 RAM OK',13,10,0
fail_text:
        db 'R1715 RAM FAIL!',0
