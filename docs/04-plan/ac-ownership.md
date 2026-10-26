# AC Ownership — each acceptance criterion is owned by exactly one milestone

Generated; CI regenerates it and fails on missing, duplicate or unknown ACs, **and on any AC whose owner milestone is earlier than a milestone listed in its `requires`** (NB-1). Later milestones run earlier ACs as regression.
Split ACs (tagged separately in tests): AC-G6-1a (13 catalog automations, M5) / AC-G6-1b (automation 5 with real T7, M7); AC-C17-6a (table, filter, WS, widget — M4b) / AC-C17-6b (export — M9).

| Milestone | # | Owned ACs |
|---|---|---|
| M1 | 23 | AC-K7-2, AC-K7-3, AC-K1-1, AC-K1-2, AC-K2-1, AC-K2-2, AC-K3-2, AC-K3-3, AC-K3-4, AC-A1-1, AC-A1-2, AC-A1-3, AC-A2-1, AC-A2-2, AC-A2-3, AC-A4-1, AC-A4-2, AC-A16-1, AC-F1-1, AC-F1-2, AC-B2-1, AC-B3-1, AC-F7-5 |
| M2 | 57 | AC-B1-1, AC-B1-2, AC-B1-3, AC-B5-1, AC-B5-2, AC-B5-3, AC-B6-1, AC-B6-2, AC-B6-3, AC-B6-4, AC-B6-5, AC-B6-6, AC-B6-7, AC-B6-8, AC-B7-1, AC-B7-2, AC-B7-3, AC-B7-4, AC-B9-1, AC-B9-2, AC-B11-1, AC-B11-2, AC-B12-1, AC-B12-2, AC-C1-1, AC-C2-1, AC-C3-1, AC-C4-1, AC-C4-2, AC-C5-1, AC-C6-1, AC-C7-1, AC-C8-1, AC-C8-3, AC-C9-1, AC-C10-1, AC-C11-1, AC-C12-1, AC-C13-1, AC-C24-1, AC-C25-1, AC-C26-1, AC-C37-1, AC-C40-1, AC-C40-2, AC-C40-3, AC-D1-1, AC-D1-2, AC-D2-1, AC-D2-2, AC-D2-3, AC-D3-1, AC-D3-2, AC-D3-3, AC-K3-1, AC-M1-1, AC-M1-2 |
| M3 | 23 | AC-F7-1, AC-F7-2, AC-F7-3, AC-F7-4, AC-E1-1, AC-E1-2, AC-E1-3, AC-E2-1, AC-E3-1, AC-E3-2, AC-E3-3, AC-E3-4, AC-E4-1, AC-A9-1, AC-A9-2, AC-A9-3, AC-A9-4, AC-A15-1, AC-A15-2, AC-F4-1, AC-A7-1, AC-A7-2, AC-A7-3 |
| M3.5 | 4 | AC-C21-1, AC-C21-2, AC-A13-1, AC-A13-2 |
| M4a | 6 | AC-C18-1, AC-C18-2, AC-C18-3, AC-C17-1, AC-C17-2, AC-C17-3 |
| M4b | 6 | AC-C17-4, AC-C17-5, AC-C17-6a, AC-C19-1, AC-C19-2, AC-F7-6 |
| M5 | 19 | AC-G1-1, AC-G1-2, AC-G1-3, AC-G1-4, AC-G1-5, AC-G1-6, AC-G1-7, AC-G1-8, AC-G1-9, AC-G1-11, AC-G3-1, AC-G5-1, AC-G6-1a, AC-G7-1, AC-C8-2, AC-C22-1, AC-B9-3, AC-F1-3, AC-A13-3 |
| M6 | 11 | AC-I1-1, AC-I1-2, AC-I2-1, AC-I3-1, AC-I3-2, AC-I7-1, AC-I7-2, AC-D5-1, AC-D5-2, AC-D5-3, AC-G1-10 |
| M7 | 21 | AC-L1-2, AC-L1-3, AC-L2-1, AC-L4-1, AC-L4-2, AC-L4-3, AC-L5-1, AC-L6-1, AC-L8-1, AC-L9-1, AC-L10-1, AC-L10-2, AC-L10-3, AC-L10-4, AC-L10-5, AC-L10-6, AC-L14-1, AC-L15-1, AC-L18-1, AC-C38-1, AC-G6-1b |
| M8 | 13 | AC-H1-1, AC-H1-2, AC-H2-1, AC-H3-1, AC-H3-2, AC-H3-3, AC-H4-1, AC-H4-2, AC-H5-1, AC-H7-1, AC-K6-1, AC-L24-1, AC-L1-1 |
| M9 | 13 | AC-K7-1, AC-A11-1, AC-A11-2, AC-A11-3, AC-A11-4, AC-A11-5, AC-A14-1, AC-A14-2, AC-O1-1, AC-O5-1, AC-M1-3, AC-K3-5, AC-C17-6b |
| **Total** | **196** | 194 requirement ACs; G6-1 and C17-6 each counted as two tagged parts → 196 tagged ACs |

## Cross-milestone requirements
| AC | requires |
|---|---|
| AC-L1-1 | M8 (Sales Dashboard) |
| AC-K3-5 | M8 widgets, M9 export |
| AC-C17-6b | M9 export |
| AC-A13-3 | M5 automations |
| AC-G6-1b | M7 real T7 |
| AC-L24-1 | M7 template |
| AC-I1-1 | M5 automation 3 |
| AC-B9-3 | M5 automations |
| AC-F1-3 | M5 automations |
