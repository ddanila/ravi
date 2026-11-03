; Walking ones and zeros at TARGET. Sixteen write/read comparisons, no stack.
 ld hl,TARGET
 ld d,1
 ld e,8
walk:
 ld (hl),d
 ld a,(hl)
 cp d
 jp nz,failed
 ld a,d
 cpl
 ld d,a
 ld (hl),d
 ld a,(hl)
 cp d
 jp nz,failed
 ld a,d
 cpl
 rlca
 ld d,a
 dec e
 jr nz,walk
 jp passed
