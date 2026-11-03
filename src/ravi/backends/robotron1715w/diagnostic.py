"""Bounded, stackless destructive diagnostics with verified result records."""

import hashlib
import json
from pathlib import Path

from ravi.execution import OutcomeUnknown

from .banked import BankAddress
from .build import ROOT, assemble

KINDS = {"data-lines": 1, "ram-patterns": 2, "address-lines": 3}


def build_diagnostic(kind, workspace, address, length, bank=1):
    if kind not in KINDS:
        raise ValueError("unknown diagnostic")
    BankAddress(bank, address).validate(length)
    if length > 4096 or (kind == "data-lines" and length != 1):
        raise ValueError(
            "diagnostics cover 1..4096 bytes; data-lines requires one byte"
        )
    if not 0x4000 <= workspace < 0x10000 or (bank != 1 and workspace < 0xC000):
        raise ValueError("workspace requires direct RAM; other banks need common RAM")
    source = f""" ; MIT. Generated relocatable W1 diagnostic, stackless return ABI.
 org {workspace}
TARGET: equ {address}
SIZE: equ {length}
entry:
 di
 ld a,c
 ld (saved_id),a
 ld a,{bank * 17}
 out (024h),a
"""
    source += (ROOT / "diagnostics" / (kind.replace("-", "_") + ".asm")).read_text()
    source += f"""
passed:
 xor a
 jr finish
failed:
 ld (result_address),hl
 ld (result_actual),a
 ld a,d
 ld (result_expected),a
 ld a,1
finish:
 ld (result_status),a
 ld b,a
 ld a,0a5h
 ld (result_done),a
 xor a
 out (024h),a
 ld a,(saved_id)
 ld c,a
 ld a,b
 jp 3
code_end:
saved_id: db 0
result: db "WD1",{KINDS[kind]}
result_status: db 255
result_address: dw 0
result_expected: db 0
result_actual: db 0
result_done: db 0
image_end:
"""
    image, labels = assemble(source)
    end = workspace + len(image)
    page_start, page_end = workspace & ~255, (end + 255) & ~255
    if end > 65536 or address < page_end and address + length > page_start:
        raise ValueError(
            "target overlaps diagnostic workspace/survey pages or image wraps"
        )
    manifest = {
        "kind": kind,
        "bank": bank,
        "address": address,
        "length": length,
        "workspace": workspace,
        "workspace_end": end,
        "survey_start": page_start,
        "survey_length": page_end - page_start,
        "result_address": labels["result"],
        "size": len(image),
        "sha256": hashlib.sha256(image).hexdigest(),
        "labels": labels,
        "maximum_tstates": 20000 + length * 1000,
        "stack_bytes": 0,
        "destructive": True,
    }
    return image, source, manifest


def run_diagnostic(monitor, kind, workspace, address, length, bank=1, artifacts=None):
    image, source, manifest = build_diagnostic(kind, workspace, address, length, bank)
    # Reject overlap with existing helper before ANY destructive preparation.
    monitor._range(manifest["survey_start"], manifest["survey_length"], True)
    if any(
        address < end and address + length > start for start, end in monitor.reserved
    ):
        raise ValueError("target overlaps an active helper")
    if artifacts is not None:
        artifacts = Path(artifacts)
        artifacts.mkdir(parents=True, exist_ok=False)
        (artifacts / "snippet.asm").write_text(source)
        (artifacts / "snippet.bin").write_bytes(image)
        (artifacts / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    report = {"manifest": manifest, "passed": False}
    try:
        survey = monitor.survey(manifest["survey_start"], manifest["survey_length"])
        report["workspace_survey"] = survey
        if not all(page["passed"] for page in survey):
            raise ValueError(
                "diagnostic workspace failed survey; no execution attempted"
            )
        monitor.write_memory(workspace, image)
        result = monitor.execute(workspace, timeout=5)
        report["execution"] = result
        raw = monitor.read_memory(manifest["result_address"], 10)
        code_size = manifest["labels"]["code_end"] - workspace
        if monitor.read_memory(workspace, code_size) != image[:code_size]:
            monitor.usable = False
            raise OutcomeUnknown("diagnostic code changed during execution")
        if (
            raw[:4] != b"WD1" + bytes((KINDS[kind],))
            or raw[9] != 0xA5
            or raw[4] not in (0, 1)
            or result["accumulator"] != raw[4]
        ):
            monitor.usable = False
            raise OutcomeUnknown("missing, corrupt or inconsistent diagnostic result")
        report.update(
            passed=raw[4] == 0,
            status="pass" if raw[4] == 0 else "mismatch",
            failure=None
            if raw[4] == 0
            else {
                "bank": bank,
                "address": int.from_bytes(raw[5:7], "little"),
                "expected": raw[7],
                "actual": raw[8],
            },
        )
        return report
    except Exception as exc:
        report.update(status="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if artifacts is not None:
            (artifacts / "result.json").write_text(json.dumps(report, indent=2) + "\n")
