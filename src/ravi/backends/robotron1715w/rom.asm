; MIT. Stackless RAVI W ROM, protocol W2 (legacy R supported). Generated instruction sequences
; are explicit to allow a normal z80asm build without a macro preprocessor.
; Main BC=op/id, DE=bank/count, HL=address. Alternate BC=CRC16.
; IX=leaf return; alternate DE/HL and I are serial temporaries.
; No CALL/RET/PUSH/POP or main RAM workspace. NMI must remain inactive.
 org 0
 jp cold
 jp returned
cold:
 di
 ld ix,boot_serial
 jp configure
boot_serial:
 ld bc,08000h
 ld de,1
 ld hl,0
 ld a,10
 jp response
boot_continue:
 ld a,e
 cp 1
 jp z,checksum
 cp 2
 jr z,boot_display_marker
 jp display_init
boot_display_marker:
 ld de,3
 ld hl,0
 ld a,10
 jp response
; Every ROM byte including padding and the appended CRC participates.
checksum:
 ld hl,0
 ld de,0800h
 exx
 ld bc,0ffffh
 exx
checksum_loop:
 ld a,(hl)
 ld ix,checksum_next
 exx
 jp crc_byte
checksum_next:
 inc hl
 dec de
 ld a,d
 or e
 jr nz,checksum_loop
 exx
 ld a,b
 exx
 ld h,a
 exx
 ld a,c
 exx
 ld l,a
 ld sp,0
 ld a,h
 or l
 jr z,checksum_good
 ld sp,1
checksum_good:
 ld a,b
 cp 080h
 jr z,checksum_boot
 ld de,0
 ld a,h
 or l
 ld a,0
 jp z,response
 ld a,11
 jp failure
checksum_boot:
 ld de,2
 ld a,h
 or l
 jr z,checksum_boot_send
 inc d
checksum_boot_send:
 ld a,10
 jp response

display_init:
 xor a
 ; Clear glyph SRAM; every character is initialized by firmware.
 ld hl,02000h
 ld de,02001h
 ld bc,00fffh
 ld (hl),a
 ldir
 ; Copy compact glyph columns into the board's scanline-major font SRAM.
 ld hl,font
 ld de,02000h
 ld b,43
font_char:
 ld c,8
font_row:
 ld a,(hl)
 ld (de),a
 inc hl
 ld a,e
 add a,080h
 ld e,a
 jr nc,font_no_carry
 inc d
font_no_carry:
 dec c
 jr nz,font_row
 ld a,e
 inc a
 ld e,a
 ld d,020h
 djnz font_char
 ; Clear the video SRAM with glyph 0 (space).
 ld hl,03000h
 ld de,03001h
 ld bc,00fffh
 xor a
 ld (hl),a
 ldir
 ; 8275 reset, explicit 80x24, 12 scanlines, reference retrace geometry.
 xor a
 out (019h),a
 ld a,79
 out (018h),a
 ld a,23
 out (018h),a
 ld a,06bh
 out (018h),a
 ld a,060h
 out (018h),a
 ; Cursor outside visible geometry; do not inherit emulator defaults.
 ld a,080h
 out (019h),a
 ld a,0ffh
 out (018h),a
 out (018h),a
 ld a,020h
 out (019h),a
 ld a,0c0h
 out (019h),a
 ld hl,title
 ld de,03000h
 ld bc,12
 ldir
 ld hl,rx_text
 ld de,03140h
 ld bc,10
 ldir
 ld bc,0
 ld de,0
 ld hl,0
 add hl,sp
 ld a,l
 or a
 ld a,2
 jp z,response
 ld a,11
 jp response
returned:
 ; Cooperative ABI: C=request id, A=result; caller restored ROM read bank.
 di
 ld e,a
 ld b,0
 ld d,0
 ld hl,0
 ld ix,return_ready
configure:
 xor a
 out (024h),a
 ; Both candidate V24 clock routes: 3993600 / 16 / 26 = 9600, SIO x1.
 ld a,7
 out (009h),a
 out (00ah),a
 ld a,26
 out (009h),a
 out (00ah),a
 ld a,018h
 out (00fh),a
 ld a,4
 out (00fh),a
 ld a,4
 out (00fh),a
 ld a,3
 out (00fh),a
 ld a,0c1h
 out (00fh),a
 ld a,5
 out (00fh),a
 ld a,0eah
 out (00fh),a
 ld a,1
 out (00fh),a
 xor a
 out (00fh),a
 jp (ix)
return_ready:
 ; Cooperative return, not a boot identity.
 ld a,2
 jp response
idle:
 ; Display is output only. Protocol state never lives in video SRAM.
 exx
 ld hl,wait_text
 ld de,03050h
 ld bc,16
 ldir
 exx
idle_poll:
 xor a
 out (00fh),a
 in a,(00fh)
 bit 0,a
 jr z,idle_poll
 in a,(00dh)
 ex af,af'
 ld a,030h
 out (00fh),a
 ex af,af'
 cp 0a5h
 jr nz,idle_poll
 ld bc,0
 ld de,0
 ld hl,0

 exx
 ld bc,0ffffh
 exx
 ld ix,cont1
 jp rx
cont1:
 ld b,a
 ld ix,cont2
 jp rx
cont2:
 ld c,a
 ld ix,cont3
 jp rx
cont3:
 ld d,a
 ld ix,cont4
 jp rx
cont4:
 ld l,a
 ld ix,cont5
 jp rx
cont5:
 ld h,a
 ld ix,cont6
 jp rx
cont6:
 ld e,a
 ld ix,cont7
 jp rx
cont7:
 ld ix,cont8
 jp rx
cont8:
 exx
 ld a,b
 or c
 exx
 jp nz,bad_crc
 ld a,b
 cp 049h
 jp z,identify
 cp 056h
 jp z,version
 cp 04bh
 jp z,checksum
 ld a,d
 cp 1
 jp nz,bad_range
 ld a,h
 cp 040h
 jp c,bad_range
 ld a,b
 cp 047h
 jp z,execute
 cp 046h
 jp z,fill
 cp 052h
 jp z,read
 cp 042h
 jp z,read
 cp 057h
 jp nz,bad_op
 ld a,e
 or a
 jp z,bad_range
 cp 65
 jp nc,bad_range
 ld a,l
 add a,e
 jr nc,write_range_ok
 ld a,h
 cp 0ffh
 jr nz,write_range_ok
 ld a,l
 add a,e
 jp nz,bad_range
write_range_ok:
 exx
 ld hl,load_text
 ld de,03050h
 ld bc,16
 ldir
 exx
 ld d,e
 ld iy,0

 exx
 ld bc,0ffffh
 exx
write_loop:
 ld ix,cont9
 jp rx
cont9:
 ld (hl),a
 ; IX is disposable between RX calls. Sample RAM exactly once.
 db 0ddh,06fh ; LD IXL,A (expected)
 ld a,(hl)
 db 0ddh,0bdh ; CP IXL
 jr z,write_match
 ld b,a ; W opcode no longer needed; RX preserves this observed byte.
 ; Retain a failing address, but drain the full payload and CRC before reply.
 ld a,h
 db 0fdh,067h ; LD IYH,A
 ld a,l
 db 0fdh,06fh ; LD IYL,A
write_match:
 inc hl
 dec e
 ld a,d
 sub e
 ex af,af'
 ld a,d
 sub e
 rrca
 rrca
 rrca
 rrca
 and 15
 inc a
 ld (03144h),a
 ex af,af'
 and 15
 inc a
 ld (03145h),a
 ld a,d
 rrca
 rrca
 rrca
 rrca
 and 15
 inc a
 ld (03147h),a
 ld a,d
 and 15
 inc a
 ld (03148h),a
 ld a,e
 or a
 jr nz,write_loop
 ld d,1

 ld ix,cont10
 jp rx
cont10:
 ld ix,cont11
 jp rx
cont11:
 exx
 ld a,b
 or c
 exx
 jp nz,bad_crc
 db 0fdh,07ch ; LD A,IYH
 db 0fdh,0b5h ; OR IYL
 jr z,write_ok
 db 0fdh,07ch ; LD A,IYH
 ld h,a
 db 0fdh,07dh ; LD A,IYL
 ld l,a
 ld e,b
 ld a,7
 jp failure
write_ok:
 ld b,0
 xor a
 jp response
read:
 ld a,e
 or a
 jp z,bad_range
 cp 65
 jp nc,bad_range
 ld a,l
 add a,e
 jr nc,read_range_ok
 ld a,h
 cp 0ffh
 jr nz,read_range_ok
 ld a,l
 add a,e
 jp nz,bad_range
read_range_ok:
 ld a,b
 cp 042h
 ld a,12
 jp z,response
 ; Legacy R keeps per-byte fixed frames for W1 hosts.
 ld a,9
 jp response
fill:
 ; One page; header address must be page-aligned, E=pattern.
 ld a,l
 or a
 jp nz,bad_range
fill_loop:
 ld (hl),e
 inc l
 jr nz,fill_loop
fill_check:
 ld a,(hl)
 cp e
 jr nz,fill_bad
 inc l
 jr nz,fill_check
 xor a
 jp response
fill_bad:
 ld e,a
 ld a,7
 jp failure
version:
 ld d,0
 ld hl,build_id
 ld e,8
 ld a,12
 jp response
identify:
 ld d,31 ; stage markers, build ID, ROM CRC, captured faults, block reads
 ld hl,0800h
 ld e,2
 xor a
 jp response
execute:
 ld a,1
 jp response
bad_range:
 ld a,4
 jr failure
bad_crc:
 ld a,3
 jr failure
bad_op:
 ld a,8
failure:
 ld b,0
response:
 ; Save status in IY low; IY otherwise disposable after command processing.
 db 0fdh,06fh ; LD IYL,A
 ld a,b
 cp 080h
 jr z,response_wire
 ; Status text uses only the alternate scratch set; CRC resets below.
 db 0fdh,07dh ; LD A,IYL
 exx
 add a,a
 add a,a
 add a,a
 add a,a
 ld e,a
 ld d,0
 ld hl,status_text
 add hl,de
 ld de,030a0h
 ld bc,16
 ldir
 exx
 ld a,h
 rrca
 rrca
 rrca
 rrca
 and 15
 inc a
 ld (12532),a
 ld a,h
 and 15
 inc a
 ld (12533),a
 ld a,l
 rrca
 rrca
 rrca
 rrca
 and 15
 inc a
 ld (12534),a
 ld a,l
 and 15
 inc a
 ld (12535),a
 ld a,e
 rrca
 rrca
 rrca
 rrca
 and 15
 inc a
 ld (12537),a
 ld a,e
 and 15
 inc a
 ld (12538),a
response_wire:
 exx
 ld bc,0ffffh
 exx
 ld a,05ah
 ld ix,cont12
 jp tx
cont12:
 exx
 ld bc,0ffffh
 exx
 db 0fdh,07dh ; LD A,IYL
 ld ix,cont13
 jp tx
cont13:
 ld a,c
 ld ix,cont14
 jp tx
cont14:
 ld a,d
 ld ix,cont15
 jp tx
cont15:
 ld a,l
 ld ix,cont16
 jp tx
cont16:
 ld a,h
 ld ix,cont17
 jp tx
cont17:
 db 0fdh,07dh ; LD A,IYL
 cp 9
 ld a,e
 jr nz,response_value
 ld a,(hl)
response_value:
 ld ix,cont18
 jp tx
cont18:
 exx
 ld a,c
 exx
 db 0fdh,067h ; LD IYH,A
 exx
 ld a,b
 exx
 ld ix,cont19
 jp tx
cont19:
 db 0fdh,07ch ; LD A,IYH
 ld ix,cont20
 jp tx
cont20:
 ld a,b
 cp 080h
 jp z,boot_continue
 cp 042h
 jr z,block_payload
 cp 056h
 jr z,block_payload
 cp 047h
 jr nz,not_go
 ; Wait for the entire STARTED frame to leave the shift register before
 ; guest code can reset SIO. Preserve all primary registers.
 exx
 ld de,0ffffh
go_drain:
 ld a,1
 out (00fh),a
 in a,(00fh)
 bit 0,a
 jr nz,go_ready
 dec de
 ld a,d
 or e
 jr nz,go_drain
 exx
 jp idle
go_ready:
 exx
 jp (hl)
not_go:
 cp 052h
 jp nz,idle
 inc hl
 dec e
 jp z,idle
 ld a,9
 jp response
block_payload:
 exx
 ld bc,0ffffh
 exx
block_loop:
 ld a,(hl)
 ld ix,block_next
 jp tx
block_next:
 inc hl
 dec e
 jr nz,block_loop
 ld b,0
 jp cont18 ; payload CRC, then idle (no automatic replay)
; Serial leaf routines preserve all primary registers. Timeout abandons frame.
rx:
 exx
 ld de,0ffffh
rx_wait:
 xor a
 out (00fh),a
 in a,(00fh)
 bit 0,a
 jr nz,rx_ready
 dec de
 ld a,d
 or e
 jr nz,rx_wait
 exx
 ld a,5
 jp failure
rx_ready:
 ld a,1
 out (00fh),a
 in a,(00fh)
 and 070h
 jr nz,rx_error
 in a,(00dh)
 jp crc_byte
rx_error:
 in a,(00dh)
 ld a,030h
 out (00fh),a
 exx
 ld a,6
 jp failure
tx:
 exx
 ld l,a
 ld de,0ffffh
tx_wait:
 xor a
 out (00fh),a
 in a,(00fh)
 bit 2,a
 jr nz,tx_ready
 dec de
 ld a,d
 or e
 jr nz,tx_wait
 ; A dead transmitter must not prevent the rest of cold startup.
 exx
 ld a,b
 cp 080h
 jp z,boot_continue
 jp idle
tx_ready:
 ld a,l
 out (00dh),a
crc_byte:
 ld i,a
 xor b
 ld b,a
 ld d,8
crc_bit:
 sla c
 rl b
 jr nc,crc_next
 ld a,b
 xor 010h
 ld b,a
 ld a,c
 xor 021h
 ld c,a
crc_next:
 dec d
 jr nz,crc_bit
 ld a,i
 exx
 jp (ix)

title: db 28,11,32,19,0,2,8,2,6,33,0,0
wait_text: db 33,11,19,30,0,18,25,29,30,0,0,0,0,0,0,0
load_text: db 22,25,11,14,0,0,0,0,0,0,0,0,0,0,0,0
rx_text: db 28,34,0,0,1,1,40,1,1,0
status_text:
status0: db 32,15,28,19,16,19,15,14,0,0,0,0,0,0,0,0
status1: db 28,31,24,0,0,0,0,0,0,0,0,0,0,0,0,0
status2: db 28,15,11,14,35,0,0,0,0,0,0,0,0,0,0,0
status3: db 13,28,13,0,15,28,28,25,28,0,0,0,0,0,0,0
status4: db 28,11,24,17,15,0,15,28,28,25,28,0,0,0,0,0
status5: db 28,34,0,30,19,23,15,25,31,30,0,0,0,0,0,0
status6: db 31,11,28,30,0,15,28,28,25,28,0,0,0,0,0,0
status7: db 28,11,23,0,15,28,28,25,28,0,0,0,0,0,0,0
status8: db 12,11,14,0,13,25,23,23,11,24,14,0,0,0,0,0
status9: db 28,15,11,14,0,0,0,0,0,0,0,0,0,0,0,0
status10: defs 16,0
status11: db 28,25,23,0,15,28,28,25,28,0,0,0,0,0,0,0
status12: db 28,15,11,14,0,12,22,25,13,21,0,0,0,0,0,0
font:
 db 0,0,0,0,0,0,0,0
 db 56,76,84,84,100,68,56,0
 db 16,48,16,16,16,16,56,0
 db 56,68,4,8,16,32,124,0
 db 120,4,4,56,4,4,120,0
 db 8,24,40,72,124,8,8,0
 db 124,64,64,120,4,4,120,0
 db 56,64,64,120,68,68,56,0
 db 124,4,8,16,32,32,32,0
 db 56,68,68,56,68,68,56,0
 db 56,68,68,60,4,4,56,0
 db 56,68,68,124,68,68,68,0
 db 120,68,68,120,68,68,120,0
 db 60,64,64,64,64,64,60,0
 db 120,68,68,68,68,68,120,0
 db 124,64,64,120,64,64,124,0
 db 124,64,64,120,64,64,64,0
 db 60,64,64,92,68,68,60,0
 db 68,68,68,124,68,68,68,0
 db 124,16,16,16,16,16,124,0
 db 28,8,8,8,72,72,48,0
 db 68,72,80,96,80,72,68,0
 db 64,64,64,64,64,64,124,0
 db 68,108,84,84,68,68,68,0
 db 68,100,100,84,76,76,68,0
 db 56,68,68,68,68,68,56,0
 db 120,68,68,120,64,64,64,0
 db 56,68,68,68,84,72,52,0
 db 120,68,68,120,80,72,68,0
 db 60,64,64,56,4,4,120,0
 db 124,16,16,16,16,16,16,0
 db 68,68,68,68,68,68,56,0
 db 68,68,68,68,68,40,16,0
 db 68,68,68,84,84,108,68,0
 db 68,68,40,16,40,68,68,0
 db 68,68,40,16,16,16,16,0
 db 124,4,8,16,32,64,124,0
 db 56,68,4,8,16,0,16,0
 db 0,0,124,0,124,0,0,0
 db 0,0,0,124,0,0,0,0
 db 4,4,8,16,32,64,64,0
 db 0,16,16,0,16,16,0,0
 db 0,0,0,0,0,24,24,0
build_id: defs 8,0 ; builder patches canonical SHA-256 prefix
image_end:
 defs 2046-$,0ffh
rom_crc: dw 0 ; builder appends CRC-16/CCITT-FALSE, high byte first
