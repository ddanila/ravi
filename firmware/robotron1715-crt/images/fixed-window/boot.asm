; RAVI PC1715 CRT 1.2. Z80, 2716 boot ROM, overlay remains enabled.
; Destructive minimum-RAM search. No CALL/PUSH/interrupts until a work page
; and a distinct non-aliasing screen block have both passed two fill/read passes.
 org 0
 di
retry:
 ld a,040h
 out (019h),a
 ld d,0f8h
screen_search:
 ld c,8
 ld iy,screen_result
 jp probe
screen_result:
 jr nc,screen_found
 ld a,d
 sub 8
 ld d,a
 jr nz,screen_search
 jr retry
screen_found:
 ld h,d
 ld l,0
 ld ix,0
 ; Transfer HL to IX without using RAM or stack.
 db 0ddh,062h ; LD IXH,D
 ld d,0ffh
work_search:
 ld a,d
 and 0f8h
 db 0ddh,0bch ; CP IXH
 jr z,work_next
 ; Restore screen signature before trying another possibly aliased page.
 db 0ddh,07ch ; LD A,IXH
 ld h,a
 ld l,0
 ld b,8
signature:
 ld a,h
 xor l
 cpl
 ld (hl),a
 inc l
 jr nz,signature
 inc h
 djnz signature
 ld c,1
 ld iy,work_result
 jp probe
work_result:
 jr c,work_next
 db 0ddh,07ch ; LD A,IXH
 ld h,a
 ld l,0
 ld b,8
alias_check:
 ld a,h
 xor l
 cpl
 cp (hl)
 jr nz,work_next
 inc l
 jr nz,alias_check
 inc h
 djnz alias_check
 ld h,d
 ld l,0
 ld iy,0
 db 0fdh,062h ; LD IYH,D
 inc h
 ld sp,hl
 ld (iy+0),9
 jp initialise
work_next:
 dec d
 ld a,d
 cp 8
 jr nc,work_search
 jp retry
; D=start high byte, C=page count. E=pass mask. Returns carry on mismatch.
probe:
 ld e,0
probe_pass:
 ld h,d
 ld l,0
 ld b,c
fill:
 ld a,h
 xor l
 xor e
 ld (hl),a
 inc l
 jr nz,fill
 inc h
 djnz fill
 ld h,d
 ld l,0
 ld b,c
verify:
 ld a,h
 xor l
 xor e
 cp (hl)
 jr nz,bad
 inc l
 jr nz,verify
 inc h
 djnz verify
 ld a,e
 cpl
 ld e,a
 or a
 jr nz,probe_pass
 jp (iy)
bad:
 scf
 jp (iy)
initialise:
 xor a
 out (019h),a
 ld hl,parameters
 ld b,4
init_loop:
 ld a,(hl)
 inc hl
 out (018h),a
 djnz init_loop
 ; Cursor outside the active area.
 ld a,080h
 out (019h),a
 ld a,0ffh
 out (018h),a
 out (018h),a
 db 0ddh,07ch ; LD A,IXH
 ; A23.2 D1..D5 -> AB11..AB15 (X12 selects counter AB10).
 rrca
 rrca
 and 03eh
 out (034h),a
show:
 ld a,040h
 out (019h),a
 ld a,(iy+0)
 add a,a
 ld l,a
 ld h,0
 ld de,patterns
 add hl,de
 ld e,(hl)
 inc hl
 ld d,(hl)
 ex de,hl
 push ix
 pop de
 call unpack
 ld a,(iy+0)
 or a
 call z,addresses
 ld a,023h
 out (019h),a
 ; A23.1 is a one-way latch: CPU cannot read 8275 status on this board.
 ; 24,579,698 T states = 9.999877 s at nominal 2.458 MHz.
 ; Execute instructions continuously to preserve refresh-driven video fetches.
delay:
 ld d,16
delay_outer:
 ld bc,59085
delay_inner:
 dec bc
 ld a,b
 or c
 jr nz,delay_inner
 dec d
 jr nz,delay_outer
 ld a,(iy+0)
 jp delay
selected:
 ld (iy+0),a
 jp show
; LZ decoder: zero=end, low control=literal count;
; high control=match length minus three, then little-endian backward distance.
unpack:
 ld a,(hl)
 inc hl
 or a
 ret z
 bit 7,a
 jr nz,match
 ld c,a
 ld b,0
 ldir
 jr unpack
match:
 and 127
 add a,3
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 push hl
 ld h,d
 ld l,e
 or a
 sbc hl,bc
 ld c,a
 ld b,0
 ldir
 pop hl
 jr unpack
addresses:
 push ix
 pop de
 ld hl,768
 add hl,de
 db 0ddh,07ch ; LD A,IXH
 call hexbyte
 xor a
 call hexbyte
 push ix
 pop de
 ld hl,780
 add hl,de
 db 0fdh,07ch ; LD A,IYH
 call hexbyte
 xor a
 jp hexbyte
hexbyte:
 push af
 rrca
 rrca
 rrca
 rrca
 call digit
 pop af
digit:
 and 15
 add a,48
 cp 58
 jr c,digit_store
 add a,7
digit_store:
 ld (hl),a
 inc hl
 ret
; 80 columns, 24+2 rows, 12 scanlines, invisible attributes, 28 H blank.
parameters:
 db 79,057h,0bbh,00dh

patterns:
 dw p0,p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11
p0:
 db 2,128,32,204,1,0,255,81,0,188,162,0,19,82,65,86,73,32,80,67,49,55,49,53
 db 32,67,82,84,32,49,46,50,255,243,0,218,149,1,14,56,48,32,88,32,50,52,32,32
 db 45,32,32,54,52,130,13,0,2,56,56,255,230,1,214,136,2,22,82,65,77,32,83,67
 db 82,69,69,78,58,32,48,48,48,48,32,32,87,79,82,75,133,12,0,255,217,2,209,123
 db 3,11,49,50,32,80,65,84,84,69,82,78,83,130,232,1,10,49,48,32,83,69,67,79
 db 78,68,83,255,204,3,211,110,4,28,78,79,32,75,69,89,66,79,65,82,68,32,79,82
 db 32,68,73,83,75,32,82,69,81,85,73,82,69,68,255,191,4,216,97,5,8,82,69,83
 db 69,84,32,84,79,129,9,0,4,84,65,82,84,255,178,5,255,84,6,255,165,6,172,104
 db 7,0
p1:
 db 3,132,6,7,133,1,0,154,10,0,1,8,165,40,0,3,132,9,0,133,1,0,154,10
 db 0,1,10,165,40,0,255,81,0,158,162,0,255,68,1,255,68,1,255,68,1,255,136,2
 db 172,217,2,2,11,12,133,1,0,154,10,0,1,13,165,40,0,255,204,3,255,204,3,255
 db 204,3,255,16,5,255,16,5,255,84,6,255,204,3,187,204,3,0
p2:
 db 3,132,6,7,133,1,0,154,10,0,1,8,165,40,0,3,132,9,0,133,1,0,146,10
 db 0,18,14,15,16,17,18,19,20,21,22,23,24,20,25,26,27,28,29,30,147,40,0,133
 db 70,0,1,10,152,81,0,7,31,32,33,34,35,36,4,132,41,0,132,121,0,7,37,38
 db 39,40,41,42,43,174,81,0,5,14,44,45,46,47,138,122,0,138,202,0,5,48,49,50
 db 51,30,148,162,0,145,68,1,3,52,53,54,159,68,1,3,55,56,57,164,68,1,3,58
 db 59,60,144,28,1,144,108,1,3,61,62,63,160,68,1,3,64,65,66,146,109,1,146,189
 db 1,3,67,68,69,157,149,1,2,70,71,148,190,1,148,14,2,2,72,73,155,68,1,2
 db 74,75,173,136,2,2,76,77,154,136,2,1,78,150,96,2,150,176,2,1,79,153,136,2
 db 2,80,81,175,81,0,2,82,83,139,217,2,2,11,12,133,1,0,4,11,12,12,84,134
 db 10,0,135,20,0,131,32,0,1,13,144,20,0,132,40,0,1,85,138,40,0,139,204,3
 db 1,86,177,204,3,1,87,152,204,3,2,88,89,175,68,1,2,90,91,153,204,3,1,92
 db 175,149,1,1,93,154,29,4,2,94,95,173,230,1,2,96,97,155,204,3,2,98,99,171
 db 16,5,2,100,101,157,16,5,3,102,103,104,167,123,3,3,105,106,107,160,16,5,3,108
 db 109,110,163,29,4,3,111,112,113,164,97,5,4,114,115,116,30,157,110,4,4,14,117,118
 db 119,166,16,5,7,6,7,7,120,121,122,123,151,84,6,4,124,125,126,127,175,84,6,8
 db 128,0,1,2,3,4,132,29,132,173,0,133,5,6,9,14,15,128,5,6,7,8,9,132
 db 178,88,6,130,189,6,15,37,38,128,10,11,12,13,14,15,132,22,23,128,16,14,129,181
 db 6,3,132,36,4,157,173,6,151,172,3,165,212,3,139,252,3,0
p3:
 db 2,132,2,204,1,0,255,81,0,255,162,0,255,68,1,255,149,1,255,55,2,255,217,2
 db 255,42,3,255,204,3,255,29,4,255,191,4,255,97,5,255,178,5,255,84,6,255,165,6
 db 168,108,7,0
p4:
 db 2,132,3,204,1,0,255,81,0,255,162,0,255,68,1,255,149,1,255,55,2,255,217,2
 db 255,42,3,255,204,3,255,29,4,255,191,4,255,97,5,255,178,5,255,84,6,255,165,6
 db 168,108,7,0
p5:
 db 2,132,4,204,1,0,255,81,0,255,162,0,255,68,1,255,149,1,255,55,2,255,217,2
 db 255,42,3,255,204,3,255,29,4,255,191,4,255,97,5,255,178,5,255,84,6,255,165,6
 db 168,108,7,0
p6:
 db 2,132,5,204,1,0,255,81,0,255,162,0,255,68,1,255,149,1,255,55,2,255,217,2
 db 255,42,3,255,204,3,255,29,4,255,191,4,255,97,5,255,178,5,255,84,6,255,165,6
 db 168,108,7,0
p7:
 db 2,132,0,204,1,0,255,81,0,255,162,0,255,68,1,255,149,1,255,55,2,255,217,2
 db 255,42,3,255,204,3,255,29,4,255,191,4,255,97,5,255,178,5,255,84,6,255,165,6
 db 168,108,7,0
p8:
 db 2,132,1,204,1,0,255,81,0,255,162,0,255,68,1,255,149,1,255,55,2,255,217,2
 db 255,42,3,255,204,3,255,29,4,255,191,4,255,97,5,255,178,5,255,84,6,255,165,6
 db 168,108,7,0
p9:
 db 2,132,0,204,1,0,255,81,0,255,162,0,255,68,1,255,149,1,255,55,2,154,218,2
 db 1,1,144,1,0,255,81,0,255,162,0,255,68,1,201,149,1,255,191,4,255,16,5,255
 db 178,5,255,84,6,255,165,6,173,103,7,0
p10:
 db 2,128,32,204,1,0,158,81,0,15,83,84,65,78,68,65,82,68,32,71,76,89,80,72
 db 83,191,81,0,206,162,0,182,243,0,32,0,1,2,3,4,5,6,7,8,9,10,11,12
 db 13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,175,68,1,31,33
 db 34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57
 db 58,59,60,61,62,63,174,149,1,32,64,65,66,67,68,69,70,71,72,73,74,75,76,77
 db 78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,174,230,1,32,96,97
 db 98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121
 db 122,123,124,125,126,127,255,149,1,255,55,2,255,217,2,132,229,3,14,65,76,84,69,82
 db 78,65,84,69,32,84,73,76,69,255,123,3,191,124,4,1,132,205,123,3,134,81,0,197
 db 123,3,134,162,0,197,123,3,134,243,0,255,123,3,255,178,5,255,3,6,212,165,6,0
p11:
 db 2,128,32,204,1,0,156,81,0,20,73,78,84,69,78,83,73,84,89,32,65,78,68,32
 db 68,73,84,72,69,82,186,81,0,206,162,0,255,81,0,164,243,0,6,78,79,82,77,65
 db 76,255,243,0,130,66,2,2,132,1,172,1,0,142,121,2,225,83,0,228,59,2,4,72
 db 73,71,72,255,140,2,131,218,3,1,133,207,153,1,208,83,0,221,212,3,132,105,4,10
 db 53,48,32,80,69,82,67,69,78,84,255,37,4,2,132,5,172,1,0,160,50,3,207,83
 db 0,217,15,6,132,254,5,18,73,83,32,78,79,84,32,65,78,65,76,79,71,32,71,82
 db 69,89,255,15,6,255,96,6,136,152,7,0
