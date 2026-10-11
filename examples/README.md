# Example files

All names, dates and numbers here are made up. Never add real patient data to this folder.

| File | Expected `/scan-file` decision |
|---|---|
| `eob_with_phi.pdf` | `block` (page 2 is a rotated landscape page) |
| `clean_benefits.pdf` | `allow` (provider name, NPI, CDT codes and amounts are not PHI) |
| `scanned_page.pdf` | `cannot_verify` (image only; text inside images cannot be checked) |
| `claims_export.csv` | `block` |
| `claim_837d.edi` | `block` (X12 837D) |
