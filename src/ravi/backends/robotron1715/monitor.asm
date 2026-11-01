; RAVI PC1715 recoverable serial diagnostic, MIT.
; Code 4000h..image_end; scratch 4C00h..4EFFh; stack in known boot RAM at 0990h.
; Polls the stock loader's SIO B configuration, interrupts remain disabled.
; Commands are byte-oriented, not a terminal line protocol:
; ? => identity; R lo hi count => hex read (count=0 means 256)
; T page => preserve/test/restore 256 bytes (protect 08..0F and 40..4F)
; W lo hi count data => staged, bounded write within one writable page
; G lo hi => call uploaded code (RET returns here); writable ranges only.
; Every command ends with READY, including RAM failures and parser errors.
        org 04000h
start:
        di
        ld sp,00990h
        ld hl,identity
        call puts
ready:
        ld sp,00990h
        ld hl,ready_text
        call puts
command:
        call rx_wait
        cp '?'
        jp z,start
        cp 'R'
        jp z,read_command
        cp 'T'
        jp z,test_command
        cp 'W'
        jp z,write_command
        cp 'G'
        jp z,go_command
        ld hl,bad_command
        jp error
read_command:
        call header
        ld hl,data_text
        call puts
        ld hl,(address)
        call length_bc
read_loop:
        ld a,(hl)
        call hex_byte
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,read_loop
        jp finish
write_command:
        call header
        ld hl,(address)
        call writable
        ; A write must fit within one page, including the 256-byte case.
        ld a,(length)
        or a
        jr nz,write_short
        ld a,l
        or a
        jp nz,range_error
        jr write_receive
write_short:
        dec a
        add a,l
        jp c,range_error
write_receive:
        ld hl,backup
        call length_bc
write_receive_loop:
        call rx_timed
        ld (hl),a
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,write_receive_loop
        ld hl,backup
        ld de,(address)
        call length_bc
        ldir
        ld hl,wrote_text
        call puts
        ld hl,(address)
        call length_bc
        jr read_loop
 go_command:
        call rx_timed
        ld (address),a
        call rx_timed
        ld (address+1),a
        ld hl,(address)
        call writable
        ld hl,go_text
        call puts
        ld hl,(address)
        call jump_hl
        di
        jp ready
jump_hl:
        jp (hl)
header:
        call rx_timed
        ld (address),a
        call rx_timed
        ld (address+1),a
        call rx_timed
        ld (length),a
        ret
length_bc:
        ld a,(length)
        ld c,a
        ld b,0
        or a
        ret nz
        inc b
        ret
writable:
        ld a,h
        cp 010h
        jp c,range_error
        cp 040h
        ret c
        cp 050h
        jp c,range_error
        ret
range_error:
        ld hl,range_text
        jp error

 test_command:
        call rx_timed
        ld (page),a
        cp 008h
        jr c,test_allowed
        cp 010h
        jp c,range_error
        cp 040h
        jr c,test_allowed
        cp 050h
        jp c,range_error
 test_allowed:
        ld hl,test_text
        call puts
        ld a,(page)
        call hex_byte
        call newline
        call page_hl
        ld de,backup
        ld bc,0100h
        ldir
        ld ix,patterns
        ld a,20
        ld (patterns_left),a
pattern_next:
        ld c,(ix+0)
        ld a,'P'
        ld (phase),a
        call page_hl
pattern_fill:
        ld (hl),c
        inc l
        jr nz,pattern_fill
pattern_verify:
        ld a,(hl)
        cp c
        jp nz,test_failed
        inc l
        jr nz,pattern_verify
        inc ix
        ld a,(patterns_left)
        dec a
        ld (patterns_left),a
        jr nz,pattern_next
        ld a,'A'
        ld (phase),a
address_fill:
        ld (hl),l
        inc l
        jr nz,address_fill
address_verify:
        ld c,l
        ld a,(hl)
        cp c
        jp nz,test_failed
        inc l
        jr nz,address_verify
        call restore_page
        ld hl,pass_text
        call puts
        ld a,(page)
        call hex_byte
        jp finish
 test_failed:
        ld (actual),a
        ld a,c
        ld (expected),a
        ld (failure_address),hl
        ld a,(hl)
        ld (second_read),a
        call restore_page
        ld hl,fail_text
        call puts
        ld a,(phase)
        call tx
        call space
        ld hl,(failure_address)
        ld a,h
        call hex_byte
        ld a,l
        call hex_byte
        call space
        ld a,(expected)
        call hex_byte
        call space
        ld a,(actual)
        call hex_byte
        call space
        ld a,(expected)
        ld c,a
        ld a,(actual)
        xor c
        call hex_byte
        call space
        ld a,(second_read)
        call hex_byte
        jp finish
page_hl:
        ld a,(page)
        ld h,a
        ld l,0
        ret
restore_page:
        call page_hl
        ex de,hl
        ld hl,backup
        ld bc,0100h
        ldir
        ret

; Serial helpers preserve BC, DE and HL. A is return value/clobbered.
rx_wait:
        xor a
        out (00fh),a
        in a,(00fh)
        bit 0,a
        jr z,rx_wait
        in a,(00dh)
        ret
rx_timed:
        push de
        ld de,0ffffh
rx_timed_loop:
        xor a
        out (00fh),a
        in a,(00fh)
        bit 0,a
        jr nz,rx_timed_ready
        dec de
        ld a,d
        or e
        jr nz,rx_timed_loop
        ; Reset stack instead of unwinding nested parser calls on timeout.
        ld hl,timeout_text
        jp error
rx_timed_ready:
        in a,(00dh)
        pop de
        ret
tx:
        push bc
        push de
        ld c,a
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
        ; A dead transmitter must not trap the monitor forever.
        pop de
        pop bc
        ret
 tx_ready:
        ld a,c
        out (00dh),a
        pop de
        pop bc
        ret
puts:
        ld a,(hl)
        or a
        ret z
        call tx
        inc hl
        jr puts
hex_byte:
        push af
        rrca
        rrca
        rrca
        rrca
        call hex_digit
        pop af
hex_digit:
        and 00fh
        add a,'0'
        cp ':'
        jr c,hex_emit
        add a,7
hex_emit:
        jp tx
space:
        ld a,' '
        jp tx
newline:
        ld a,13
        call tx
        ld a,10
        jp tx
finish:
        call newline
        jp ready
error:
        ld sp,00990h
        call puts
        jp ready
identity: db 'R1715 DIAG 1',13,10,0
ready_text: db 'READY',13,10,0
data_text: db 'DATA ',0
wrote_text: db 'WROTE ',0
go_text: db 'GO',13,10,0
test_text: db 'TEST ',0
pass_text: db 'PASS ',0
fail_text: db 'FAIL ',0
bad_command: db 'ERR COMMAND',13,10,0
range_text: db 'ERR RANGE',13,10,0
timeout_text: db 'ERR TIMEOUT',13,10,0
patterns: db 00h,0ffh,055h,0aah,01h,02h,04h,08h,10h,20h,40h,80h
          db 0feh,0fdh,0fbh,0f7h,0efh,0dfh,0bfh,07fh
image_end:
backup: equ 04c00h
address: equ 04e00h
length: equ 04e02h
page: equ 04e03h
patterns_left: equ 04e04h
phase: equ 04e05h
actual: equ 04e06h
expected: equ 04e07h
second_read: equ 04e08h
failure_address: equ 04e09h
