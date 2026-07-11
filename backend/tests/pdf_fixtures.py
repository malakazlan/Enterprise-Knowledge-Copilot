"""Minimal in-memory PDF builder for parser tests.

Produces a valid PDF (verified against pypdf) with one text line per page —
no external fixture files, fully deterministic.
"""

from __future__ import annotations


def make_pdf(pages: list[str]) -> bytes:
    objects: list[bytes] = []
    n_fixed = 3  # catalog, pages tree, font
    kids = " ".join(f"{n_fixed + 1 + i * 2} 0 R" for i in range(len(pages)))

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for i, text in enumerate(pages):
        page_obj = n_fixed + 1 + i * 2
        stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {page_obj + 1} 0 R "
                f"/Resources << /Font << /F1 3 0 R >> >> >>"
            ).encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
    ).encode()
    return bytes(out)
