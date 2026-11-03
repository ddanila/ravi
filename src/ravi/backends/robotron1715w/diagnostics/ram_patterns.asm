; Four complete fill/verify passes. Uniform patterns test storage/data paths.
 ld ix,patterns
 ld e,4
phase:
 ld d,(ix+0)
 ld hl,TARGET
 ld bc,SIZE
fill:
 ld (hl),d
 inc hl
 dec bc
 ld a,b
 or c
 jr nz,fill
 ld hl,TARGET
 ld bc,SIZE
verify:
 ld a,(hl)
 cp d
 jp nz,failed
 inc hl
 dec bc
 ld a,b
 or c
 jr nz,verify
 inc ix
 dec e
 jr nz,phase
 jp passed
patterns: db 0,255,055h,0aah
