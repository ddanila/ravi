; MIT. Stackless RAVI W4 ROM, firmware 4.0.0 (legacy R supported). Generated instruction sequences
; are explicit to allow a normal z80asm build without a macro preprocessor.
; W4: SP high=state (0 scanning,1 locked,2 pending), low=rate index.
; IY=handshake token until locked; I=response status.
; Main BC=op/id, DE=bank/count, HL=address. Alternate BC=CRC16.
; IX=leaf return; alternate DE/HL are serial temporaries; I=response status.
; No CALL/RET/PUSH/POP or main RAM workspace. NMI must remain inactive.
 org 0
 jp cold
 jp returned
cold:
 di
 ld sp,0
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
 ld a,h
 or l
 jr z,checksum_good
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
 ; Optional numeric display: firmware 4.0.0, state, last status.
 xor a
 ld hl,02000h
 ld de,02001h
 ld bc,00fffh
 ld (hl),a
 ldir
 ld hl,font
 ld de,02000h
 ld b,18
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
 ld hl,03000h
 ld de,03001h
 ld bc,00fffh
 xor a
 ld (hl),a
 ldir
 out (019h),a
 ld a,79
 out (018h),a
 ld a,23
 out (018h),a
 ld a,06bh
 out (018h),a
 ld a,060h
 out (018h),a
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
 ld bc,5
 ldir
 jp announce
returned:
 ; Cooperative ABI: C=request id, A=result, ROM mapping restored.
 ; Restore a defined 62400 link; no dependency on the program's stack.
 di
 ld i,a
 ld sp,0
 ld ix,return_ready
 jp configure
return_ready:
 ld a,i
 ld e,a
 ld d,0
 ld hl,0
 ld b,'Z'
 ld a,2
 jp response
configure:
 xor a
 out (024h),a
 ld a,47h
 out (009h),a
 out (00ah),a
 ld hl,0
 add hl,sp
 ld a,l
 ld hl,divisors
 ld e,a
 ld d,0
 add hl,de
 ld a,(hl)
 out (009h),a
 out (00ah),a
 ld a,018h
 out (00fh),a
 ld a,4
 out (00fh),a
 ld a,044h
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
scan_next:
 ld hl,0
 add hl,sp
 inc l
 ld a,l
 cp 3
 jr c,scan_set
 ld l,0
scan_set:
 ld h,0
 ld sp,hl
 ld ix,announce
 jp configure
announce:
 ld hl,0
 add hl,sp
 ld d,l
 ld hl,0400h
 ld bc,0
 ld e,4
 ld a,13
 jp response
idle:
 ld hl,0
 add hl,sp
 ld a,h
 inc a
 ld (03010h),a
 ld a,l
 inc a
 ld (03012h),a
 ; 32768 polls ~0.5s; pending handshake gets twice the budget.
 ld de,32768
 ld a,h
 cp 2
 jr nz,idle_poll
 ld de,0
idle_poll:
 dec de
 ld a,d
 or e
 jr nz,idle_check
 ld hl,0
 add hl,sp
 ld a,h
 cp 1
 jp nz,scan_next
 ld de,32768
idle_check:
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
 ld a,b
 cp 'N'
 jp z,information
 cp 'H'
 jp z,hello
 cp 'C'
 jp z,confirm
 exx
 ld hl,0
 add hl,sp
 ld a,h
 exx
 cp 1
 jp nz,not_connected
 ld a,b
 cp 'X'
 jp z,release
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
 ld i,a
write_match:
 inc hl
 dec e
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
 ld a,i
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
 ld d,127 ; stage markers, build ID, ROM CRC, captured faults, block reads
 ld hl,0800h
 ld e,4
 xor a
 jp response
information:
 ; Static descriptor; bank supplies live rate, address locates ROM bytes.
 exx
 ld hl,0
 add hl,sp
 ld a,l
 exx
 ld d,a
 ld hl,descriptor
 ld e,12
 ld a,12
 jp response
hello:
 ; A new hello may reconnect a locked monitor. It disables mutation until C.
 ld a,h
 or l
 jp z,bad_range
 ld a,h
 db 0fdh,067h
 ld a,l
 db 0fdh,06fh
 exx
 ld hl,0
 add hl,sp
 ld h,2
 ld sp,hl
 exx
 ld b,0
 xor a
 jp response
confirm:
 exx
 ld hl,0
 add hl,sp
 ld a,h
 exx
 cp 2
 jp nz,not_connected
 db 0fdh,07ch
 cp h
 jp nz,not_connected
 db 0fdh,07dh
 cp l
 jp nz,not_connected
 exx
 ld hl,0
 add hl,sp
 ld h,1
 ld sp,hl
 exx
 ld b,0
 xor a
 jp response
release:
 xor a
 jp response
not_connected:
 ld a,14
 jp failure
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
 ld i,a
 exx
 ld hl,0
 add hl,sp
 ld a,h
 exx
 cp 1
 ld b,0
 jr z,failure_status
 ld b,'Y'
failure_status:
 ld a,i
response:
 ld i,a
 ld a,b
 cp 080h
 jr z,response_wire
 ld a,i
 ; Numeric status update is once per response, never per data byte.
 inc a
 ld (03014h),a
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
 ld a,i
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
 ld a,i
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
 ld i,a
 exx
 ld a,b
 exx
 ld ix,cont19
 jp tx
cont19:
 ld a,i
 ld ix,cont20
 jp tx
cont20:
 ld a,b
 cp 'Z'
 jp z,announce
 cp 080h
 jp z,boot_continue
 cp 042h
 jr z,block_payload
 cp 056h
 jr z,block_payload
 cp 04eh
 jr z,block_payload
 cp 058h
 jr z,release_drain
 cp 059h
 jr z,release_drain
 cp 047h
 jr nz,not_go
release_drain:
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
 ld a,b
 cp 'G'
 jp nz,scan_next
 jp (hl)
not_go:
 cp 052h
 jp nz,after_command
 inc hl
 dec e
 jp z,idle
 ld a,9
 jp response
after_command:
 jp idle
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
 ld de,4096
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
 exx
 ld e,a
 exx
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
 ; x = input XOR high; x ^= x >> 4.
 ld e,a
 xor b
 ld d,a
 rrca
 rrca
 rrca
 rrca
 and 15
 xor d
 ld d,a
 ; high = old low XOR (x << 4) XOR (x >> 3).
 and 15
 rlca
 rlca
 rlca
 rlca
 xor c
 ld b,a
 ld a,d
 rrca
 rrca
 rrca
 and 31
 xor b
 ld b,a
 ; low = x XOR (x << 5).
 ld a,d
 rrca
 rrca
 rrca
 and 0e0h
 xor d
 ld c,a
 ld a,e
 exx
 jp (ix)

title: db 5,17,1,17,1
divisors: db 2,3,13
; descriptor schema 1, firmware 4.0.0, machine 1=W/M, protocol4,
; capability mask, speed mask, framing=8N1, multiplier16, block64, reserved.
descriptor: db 1,4,0,0,1,4,127,7,0,16,64,0
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
 db 0,0,0,0,0,24,24,0
build_id: defs 8,0
image_end:
 defs 2046-$,0ffh
rom_crc: dw 0
