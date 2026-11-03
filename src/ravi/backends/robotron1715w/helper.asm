; MIT. Assemble with ORG supplied by build_helper(). No stack in bank copy path.
; This helper is never run until its entire reserved window passes host tests.
entry:
 di
 ld a,c
 ld (saved_id),a
 ld a,(operation)
 cp 2
 jr z,write_block
 cp 3
 jr z,call_snippet
 ; Read: source bank, base-RAM destination. Executable helper must be common.
 ld a,(bank)
 or 010h
 out (024h),a
 ld hl,(address)
 ld de,buffer
 ld bc,(length)
 ldir
 xor a
 jr finish
write_block:
 ; Read code/data from base RAM, write selected physical bank.
 ld a,(bank)
 rlca
 rlca
 rlca
 rlca
 or 1
 out (024h),a
 ld hl,buffer
 ld de,(address)
 ld bc,(length)
 ldir
 ; Verify through target read mapping, base RAM remains writable.
 ld a,(bank)
 or 010h
 out (024h),a
 ld hl,(address)
 ld de,buffer
 ld bc,(length)
verify:
 ld a,(de)
 cp (hl)
 jr nz,failed
 inc de
 inc hl
 dec bc
 ld a,b
 or c
 jr nz,verify
 xor a
 jr finish
failed:
 ld (failure),hl
 ld a,7
 jr finish
call_snippet:
 ld a,(bank)
 or 010h
 out (024h),a
 ld sp,stack_end
 ld hl,(address)
 call jump_hl
 ; A carries snippet result. All registers may be clobbered; mapping must
 ; still expose this helper and the tested stack on RET.
 jr finish
jump_hl:
 jp (hl)
finish:
 ld b,a
 xor a
 out (024h),a
 ld a,(saved_id)
 ld c,a
 ld a,b
 jp 3
saved_id: db 0
operation: db 0
bank: db 1
address: dw 0
length: dw 0
failure: dw 0
buffer: defs 64,0
stack: defs 128,0
stack_end:
helper_end:
