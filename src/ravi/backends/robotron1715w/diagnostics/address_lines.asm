; Fill/verify low then high CPU-address byte across the entire selected range.
; Separate passes distinguish every address within a <=64 KiB address space.
 ld hl,TARGET
 ld bc,SIZE
fill_low:
 ld (hl),l
 inc hl
 dec bc
 ld a,b
 or c
 jr nz,fill_low
 ld hl,TARGET
 ld bc,SIZE
verify_low:
 ld d,l
 ld a,(hl)
 cp d
 jp nz,failed
 inc hl
 dec bc
 ld a,b
 or c
 jr nz,verify_low
 ld hl,TARGET
 ld bc,SIZE
fill_high:
 ld (hl),h
 inc hl
 dec bc
 ld a,b
 or c
 jr nz,fill_high
 ld hl,TARGET
 ld bc,SIZE
verify_high:
 ld d,h
 ld a,(hl)
 cp d
 jp nz,failed
 inc hl
 dec bc
 ld a,b
 or c
 jr nz,verify_high
 jp passed
