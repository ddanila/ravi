; RAVI PC1715 CRT 1.3. Z80, 2716 boot ROM, overlay remains enabled.
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
 ld (iy+0),@FIRST@
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
 ld (iy+1),0 ; title phase; work-page byte is observed only by test runner
 push ix
 pop hl
 ld (hl),080h ; standard glyph bank, invisible field attribute
 inc hl
 ld (hl),32
 push hl
 pop de
 inc de
 ld bc,1919
 ldir
 ld hl,names
 ld b,(iy+0)
 inc b
name_next:
 ld e,(hl)
 inc hl
 dec b
 jr z,name_found
 ld d,0
 add hl,de
 jr name_next
name_found:
 ld c,e
 push hl
 ld a,80
 sub c
 srl a
 ld e,a
 ld d,0
 push ix
 pop hl
 add hl,de
 ld de,881 ; row 11, plus initial field attribute
 add hl,de
 ex de,hl
 pop hl
 ld b,0
 ldir
 call start
 ld d,2
 call delay
 call stop
 ld (iy+1),1 ; clean pattern phase
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
 call start
hold:
 ld d,20
 call delay
 ld a,(iy+0)
 @ADVANCE@
selected:
 push af
 call stop
 pop af
 ld (iy+0),a
 jp show
stop:
 ld a,040h
 out (019h),a
 ret
start:
 ld a,023h
 out (019h),a
 ret
; No CRT status reads. Two iterations ~1 s; twenty ~10 s at 2.458 MHz.
; Instruction execution preserves refresh-driven display fetching.
delay:
 ld bc,47268
delay_inner:
 dec bc
 ld a,b
 or c
 jr nz,delay_inner
 dec d
 jr nz,delay
 ret
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
 ld hl,@SCREEN_ADDR@
 add hl,de
 db 0ddh,07ch ; LD A,IXH
 call hexbyte
 xor a
 call hexbyte
 push ix
 pop de
 ld hl,@WORK_ADDR@
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
 db 79,057h,06bh,00dh
