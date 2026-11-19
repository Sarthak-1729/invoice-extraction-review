# Evaluation: test set

| Run | Value |
|---|---|
| Model | gemini / gemini-3.5-flash-lite |
| Prompt | extraction_v4 (`852b70c465cb`) |
| Git commit | `f451523bbb2d` |
| Set hash | `5584672000bc2df17eacdbc4e8c7f442e0f214ce1182f1f47b8fa8e55f005681` |
| Metric definitions | v1.1 |
| Runs | 1 (started 2026-11-18T12:45:36+00:00) |
| Computed | 2026-11-18T12:51:30+00:00 |
| Settings | gemini_thinking_level=None, gemini_max_output_tokens=16384, gemini_timeout_seconds=120.0, gemini_min_interval_seconds=6.0, llm_transient_retries=3, llm_max_backoff_seconds=60.0, max_pages=20 |

## Headline

| Metric | Result |
|---|---|
| Layer 2 decided accuracy | 94.4% (1548/1640), 4 ambiguous excluded |
| Layer 2 strict accuracy | 94.2% (1548/1644) |
| Layer 1 (printed string copied exactly) | 82.1% (1349/1644) |
| Line items F1 | 74.2% (precision 74.2% (265/357), recall 74.2% (265/357)) |
| Flag recall (errors flagged) | 0.0% (0/92) |
| Flag precision | n/a (0/0) |

Coverage: 24 of 24 documents scored.


## Per field (layer 1 and layer 2 side by side)

| Field | Layer 1 | Layer 2 strict | Layer 2 decided | Ambiguous | Errors |
|---|---|---|---|---|---|
| invoice_number | 100.0% (24/24) | 100.0% (24/24) | 100.0% (24/24) | 0 | 0 |
| vendor_name | 100.0% (24/24) | 100.0% (24/24) | 100.0% (24/24) | 0 | 0 |
| bill_to_name | 100.0% (24/24) | 100.0% (24/24) | 100.0% (24/24) | 0 | 0 |
| invoice_date | 100.0% (24/24) | 95.8% (23/24) | 100.0% (23/23) | 1 | 0 |
| due_date | 100.0% (24/24) | 95.8% (23/24) | 100.0% (23/23) | 1 | 0 |
| currency | 100.0% (24/24) | 91.7% (22/24) | 100.0% (22/22) | 2 | 0 |
| subtotal | 70.8% (17/24) | 100.0% (24/24) | 100.0% (24/24) | 0 | 0 |
| tax | 70.8% (17/24) | 100.0% (24/24) | 100.0% (24/24) | 0 | 0 |
| total | 70.8% (17/24) | 100.0% (24/24) | 100.0% (24/24) | 0 | 0 |
| description | 74.2% (265/357) | 74.2% (265/357) | 74.2% (265/357) | 0 | 92 |
| quantity | 100.0% (357/357) | 100.0% (357/357) | 100.0% (357/357) | 0 | 0 |
| unit_price | 74.5% (266/357) | 100.0% (357/357) | 100.0% (357/357) | 0 | 0 |
| amount | 74.5% (266/357) | 100.0% (357/357) | 100.0% (357/357) | 0 | 0 |

## Outcomes and ambiguity

| Outcome | Fields |
|---|---|
| correct | 1537 |
| correct_absent | 11 |
| wrong | 92 |
| missing | 0 |
| hallucinated | 0 |
| ambiguous | 4 |
| ambiguous: document ambiguity (oracle also ambiguous; handled) | 4 |
| ambiguous: induced by the extraction | 0 |

## Documents

| Measure | Result |
|---|---|
| Header correct (all 9 fields, strict) | 87.5% (21/24) |
| Fully correct (header and every line) | 75.0% (18/24) |
| Documents whose only problems are ambiguous fields | 3 |

## Line items

| Measure | Result |
|---|---|
| Truth lines / predicted lines | 357 / 357 |
| Precision (all 4 fields right) | 74.2% (265/357) |
| Recall (all 4 fields right) | 74.2% (265/357) |
| F1 | 74.2% |
| Match rate (description matched) | 100.0% (357/357) |
| description accuracy over matched lines | 74.2% (265/357) |
| quantity accuracy over matched lines | 100.0% (357/357) |
| unit_price accuracy over matched lines | 100.0% (357/357) |
| amount accuracy over matched lines | 100.0% (357/357) |

## Arithmetic

Consistent documents with no arithmetic flag: 100.0% (20/20).

Deliberate arithmetic errors (case studies):

| Document | Expected flag | Fired | Arithmetic flags (fields) |
|---|---|---|---|
| test-03 | TOTAL_MISMATCH | yes | TOTAL_MISMATCH: subtotal, tax, total |
| test-08 | SUBTOTAL_MISMATCH | yes | SUBTOTAL_MISMATCH: subtotal, line_items |
| test-16 | LINE_AMOUNT_MISMATCH | yes | LINE_AMOUNT_MISMATCH: line_items[0].quantity, line_items[0].unit_price, line_items[0].amount |
| test-20 | LINE_AMOUNT_MISMATCH | yes | LINE_AMOUNT_MISMATCH: line_items[41].quantity, line_items[41].unit_price, line_items[41].amount |

## Flagging and review load

|  | Recall | Review items per document (mean / median) | Flagged fields per document (mean / median) |
|---|---|---|---|
| No review | 0.0% (0/92) | 0 | 0 |
| This system | 0.0% (0/92) | 0.62 / 0.0 | 1.08 / 0.0 |
| Review every field | 100.0% (92/92) | n/a | 68.5 / 35.0 |

- Flag precision: n/a (0/0) (false alarms: 0).
- Explained flags on accurate fields (deliberate arithmetic errors, document ambiguity), counted as neither hits nor false alarms: 22.
- Missed errors per document: 3.83 (92 unflagged errors / 24 documents), of which 0 are in documents whose extraction failed (shown to the reviewer as failed).
- Flags on predicted lines that matched no truth line: 0.

## Breakdowns (5 or more documents)

| Group | Documents | Layer 1 | Layer 2 strict | Layer 2 decided | Line recall | Flag recall |
|---|---|---|---|---|---|---|
| Layout: classic_us | 6 | 93.7% (163/174) | 99.4% (173/174) | 100.0% (173/173) | 100.0% (30/30) | n/a (0/0) |
| Layout: european | 6 | 76.4% (139/182) | 100.0% (182/182) | 100.0% (182/182) | 100.0% (32/32) | n/a (0/0) |
| Layout: modern | 6 | 83.5% (172/206) | 99.5% (205/206) | 100.0% (205/205) | 100.0% (38/38) | n/a (0/0) |
| Layout: multipage | 6 | 80.9% (875/1082) | 91.3% (988/1082) | 91.5% (988/1080) | 64.2% (165/257) | 0.0% (0/92) |
| Other currencies | 19 | 85.0% (978/1151) | 92.3% (1062/1151) | 92.6% (1062/1147) | 65.3% (160/245) | 0.0% (0/85) |

## Case studies (groups under 5 documents: counts, no rates)

### Currency JPY (test-14, test-18, test-24)

Group: layer 1 224 of 231 fields, layer 2 224 of 231 fields, 0 ambiguous, lines fully right 44 of 51. Rest of the set (21 documents): layer 1 1125 of 1413, layer 2 1324 of 1413, lines 221 of 306.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-14 | success | 29 of 29 fields | 29 of 29 fields | 0 | 5 of 5 matched, 0 extra | none | none |
| test-18 | success | 41 of 41 fields | 41 of 41 fields | 0 | 8 of 8 matched, 0 extra | none | none |
| test-24 | success | 154 of 161 fields | 154 of 161 fields | 0 | 38 of 38 matched, 0 extra | none | line_items[31].description wrong (raw `B769-75 Label printer tape #2835`, printed `Label printer tape #2835`); line_items[32].description wrong (raw `T135-83 Whiteboard markers (pack of 12) #4778`, printed `Whiteboard markers (pack of 12) #4778`); line_items[33].description wrong (raw `F810-62 USB-C docking station #8606`, printed `USB-C docking station #8606`); line_items[34].description wrong (raw `R814-86 Whiteboard markers (pack of 12) #3229`, printed `Whiteboard markers (pack of 12) #3229`); line_items[35].description wrong (raw `D415-38 USB-C docking station #7042`, printed `USB-C docking station #7042`); line_items[36].description wrong (raw `F607-76 Laser toner cartridge #3316`, printed `Laser toner cartridge #3316`); line_items[37].description wrong (raw `R801-63 A4 copy paper (box of 5 reams) #7345`, printed `A4 copy paper (box of 5 reams) #7345`) |

### Currency CAD (test-04, test-21)

Group: layer 1 147 of 262 fields, layer 2 262 of 262 fields, 0 ambiguous, lines fully right 61 of 61. Rest of the set (22 documents): layer 1 1202 of 1382, layer 2 1286 of 1382, lines 204 of 296.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-04 | success | 29 of 29 fields | 29 of 29 fields | 0 | 5 of 5 matched, 0 extra | none | none |
| test-21 | success | 118 of 233 fields | 233 of 233 fields | 0 | 56 of 56 matched, 0 extra | none | none |

### Plain numbers (no separators) (test-21)

Group: layer 1 118 of 233 fields, layer 2 233 of 233 fields, 0 ambiguous, lines fully right 56 of 56. Rest of the set (23 documents): layer 1 1231 of 1411, layer 2 1315 of 1411, lines 209 of 301.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-21 | success | 118 of 233 fields | 233 of 233 fields | 0 | 56 of 56 matched, 0 extra | none | none |

### Amount column before quantity (test-20, test-23)

Group: layer 1 308 of 350 fields, layer 2 308 of 350 fields, 0 ambiguous, lines fully right 41 of 83. Rest of the set (22 documents): layer 1 1041 of 1294, layer 2 1240 of 1294, lines 224 of 274.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-20 | success | 135 of 177 fields | 135 of 177 fields | 0 | 42 of 42 matched, 0 extra | LINE_AMOUNT_MISMATCH | line_items[0].description wrong (raw `T635-49 Whiteboard markers (pack of 12) #7870`, printed `Whiteboard markers (pack of 12) #7870`); line_items[1].description wrong (raw `D587-59 Network switch, 8-port #3595`, printed `Network switch, 8-port #3595`); line_items[2].description wrong (raw `A558-70 Label printer tape #2501`, printed `Label printer tape #2501`); line_items[3].description wrong (raw `H579-54 Laser toner cartridge #4933`, printed `Laser toner cartridge #4933`); line_items[4].description wrong (raw `M844-88 USB-C docking station #7713`, printed `USB-C docking station #7713`); line_items[5].description wrong (raw `D304-87 Standing desk frame #4363`, printed `Standing desk frame #4363`); line_items[6].description wrong (raw `A802-50 Label printer tape #3439`, printed `Label printer tape #3439`); line_items[7].description wrong (raw `F889-14 Laser toner cartridge #8411`, printed `Laser toner cartridge #8411`); line_items[8].description wrong (raw `B752-88 Ergonomic office chair #3649`, printed `Ergonomic office chair #3649`); line_items[9].description wrong (raw `B719-10 Laser toner cartridge #9805`, printed `Laser toner cartridge #9805`); line_items[10].description wrong (raw `T448-20 Acoustic wall panel #8791`, printed `Acoustic wall panel #8791`); line_items[11].description wrong (raw `T961-98 Cable management kit #1669`, printed `Cable management kit #1669`); line_items[12].description wrong (raw `P706-63 Laser toner cartridge #1808`, printed `Laser toner cartridge #1808`); line_items[13].description wrong (raw `R698-76 Webcam 1080p #6651`, printed `Webcam 1080p #6651`); line_items[14].description wrong (raw `C982-50 Webcam 1080p #4555`, printed `Webcam 1080p #4555`); line_items[15].description wrong (raw `P177-88 Ergonomic office chair #9714`, printed `Ergonomic office chair #9714`); line_items[16].description wrong (raw `P487-67 Acoustic wall panel #2532`, printed `Acoustic wall panel #2532`); line_items[17].description wrong (raw `K757-56 Label printer tape #5308`, printed `Label printer tape #5308`); line_items[18].description wrong (raw `H690-60 Cable management kit #3546`, printed `Cable management kit #3546`); line_items[19].description wrong (raw `C533-71 LED desk lamp #9832`, printed `LED desk lamp #9832`); line_items[20].description wrong (raw `M394-42 A4 copy paper (box of 5 reams) #8600`, printed `A4 copy paper (box of 5 reams) #8600`); line_items[21].description wrong (raw `C461-35 USB-C docking station #6032`, printed `USB-C docking station #6032`); line_items[22].description wrong (raw `T576-20 Network switch, 8-port #8533`, printed `Network switch, 8-port #8533`); line_items[23].description wrong (raw `H601-97 USB-C docking station #9444`, printed `USB-C docking station #9444`); line_items[24].description wrong (raw `A817-79 LED desk lamp #9559`, printed `LED desk lamp #9559`); line_items[25].description wrong (raw `C243-43 Label printer tape #4941`, printed `Label printer tape #4941`); line_items[26].description wrong (raw `T374-40 Acoustic wall panel #5023`, printed `Acoustic wall panel #5023`); line_items[27].description wrong (raw `D816-96 Label printer tape #5821`, printed `Label printer tape #5821`); line_items[28].description wrong (raw `E288-71 A4 copy paper (box of 5 reams) #3099`, printed `A4 copy paper (box of 5 reams) #3099`); line_items[29].description wrong (raw `T464-47 Acoustic wall panel #7929`, printed `Acoustic wall panel #7929`); line_items[30].description wrong (raw `P842-79 Monitor arm #5754`, printed `Monitor arm #5754`); line_items[31].description wrong (raw `B963-32 Wireless keyboard #8361`, printed `Wireless keyboard #8361`); line_items[32].description wrong (raw `P100-28 Webcam 1080p #6722`, printed `Webcam 1080p #6722`); line_items[33].description wrong (raw `F192-47 Standing desk frame #2628`, printed `Standing desk frame #2628`); line_items[34].description wrong (raw `A285-52 Ergonomic office chair #4848`, printed `Ergonomic office chair #4848`); line_items[35].description wrong (raw `F335-74 Label printer tape #4927`, printed `Label printer tape #4927`); line_items[36].description wrong (raw `A638-76 Network switch, 8-port #9876`, printed `Network switch, 8-port #9876`); line_items[37].description wrong (raw `T526-32 Cable management kit #9205`, printed `Cable management kit #9205`); line_items[38].description wrong (raw `D744-40 Standing desk frame #1738`, printed `Standing desk frame #1738`); line_items[39].description wrong (raw `D530-34 Network switch, 8-port #2602`, printed `Network switch, 8-port #2602`); line_items[40].description wrong (raw `M782-52 Wireless keyboard #1948`, printed `Wireless keyboard #1948`); line_items[41].description wrong (raw `E389-94 Whiteboard markers (pack of 12) #4986`, printed `Whiteboard markers (pack of 12) #4986`) |
| test-23 | success | 173 of 173 fields | 173 of 173 fields | 0 | 41 of 41 matched, 0 extra | none | none |

### SKU / item-code column (test-19, test-20, test-22, test-24)

Group: layer 1 584 of 676 fields, layer 2 582 of 676 fields, 2 ambiguous, lines fully right 68 of 160. Rest of the set (20 documents): layer 1 765 of 968, layer 2 966 of 968, lines 197 of 197.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-19 | success | 138 of 181 fields | 138 of 181 fields | 0 | 43 of 43 matched, 0 extra | none | line_items[0].description wrong (raw `A599-19 Standing desk frame #5085`, printed `Standing desk frame #5085`); line_items[1].description wrong (raw `C366-20 Webcam 1080p #6196`, printed `Webcam 1080p #6196`); line_items[2].description wrong (raw `M586-34 Cable management kit #5785`, printed `Cable management kit #5785`); line_items[3].description wrong (raw `F204-30 Monitor arm #4925`, printed `Monitor arm #4925`); line_items[4].description wrong (raw `M941-42 Webcam 1080p #7866`, printed `Webcam 1080p #7866`); line_items[5].description wrong (raw `F729-64 Laser toner cartridge #2170`, printed `Laser toner cartridge #2170`); line_items[6].description wrong (raw `H627-63 Webcam 1080p #6250`, printed `Webcam 1080p #6250`); line_items[7].description wrong (raw `T876-15 Standing desk frame #1514`, printed `Standing desk frame #1514`); line_items[8].description wrong (raw `B142-36 Whiteboard markers (pack of 12) #7118`, printed `Whiteboard markers (pack of 12) #7118`); line_items[9].description wrong (raw `D667-95 Whiteboard markers (pack of 12) #5437`, printed `Whiteboard markers (pack of 12) #5437`); line_items[10].description wrong (raw `E639-18 Webcam 1080p #4332`, printed `Webcam 1080p #4332`); line_items[11].description wrong (raw `P369-12 Acoustic wall panel #8931`, printed `Acoustic wall panel #8931`); line_items[12].description wrong (raw `F821-44 Label printer tape #2742`, printed `Label printer tape #2742`); line_items[13].description wrong (raw `P436-12 Ergonomic office chair #3569`, printed `Ergonomic office chair #3569`); line_items[14].description wrong (raw `E255-20 A4 copy paper (box of 5 reams) #8238`, printed `A4 copy paper (box of 5 reams) #8238`); line_items[15].description wrong (raw `P739-60 Monitor arm #1856`, printed `Monitor arm #1856`); line_items[16].description wrong (raw `A220-10 Wireless keyboard #2928`, printed `Wireless keyboard #2928`); line_items[17].description wrong (raw `T107-75 LED desk lamp #1815`, printed `LED desk lamp #1815`); line_items[18].description wrong (raw `T189-64 Ergonomic office chair #7453`, printed `Ergonomic office chair #7453`); line_items[19].description wrong (raw `H919-47 Whiteboard markers (pack of 12) #8643`, printed `Whiteboard markers (pack of 12) #8643`); line_items[20].description wrong (raw `P832-33 Label printer tape #8160`, printed `Label printer tape #8160`); line_items[21].description wrong (raw `F199-24 A4 copy paper (box of 5 reams) #7561`, printed `A4 copy paper (box of 5 reams) #7561`); line_items[22].description wrong (raw `B635-50 Wireless keyboard #5661`, printed `Wireless keyboard #5661`); line_items[23].description wrong (raw `H593-21 Acoustic wall panel #4484`, printed `Acoustic wall panel #4484`); line_items[24].description wrong (raw `C941-30 Acoustic wall panel #5651`, printed `Acoustic wall panel #5651`); line_items[25].description wrong (raw `C894-95 Cable management kit #2695`, printed `Cable management kit #2695`); line_items[26].description wrong (raw `E729-11 Label printer tape #5998`, printed `Label printer tape #5998`); line_items[27].description wrong (raw `R441-23 Network switch, 8-port #4093`, printed `Network switch, 8-port #4093`); line_items[28].description wrong (raw `A500-76 Whiteboard markers (pack of 12) #1362`, printed `Whiteboard markers (pack of 12) #1362`); line_items[29].description wrong (raw `E426-74 USB-C docking station #5861`, printed `USB-C docking station #5861`); line_items[30].description wrong (raw `D897-54 USB-C docking station #6536`, printed `USB-C docking station #6536`); line_items[31].description wrong (raw `A368-75 LED desk lamp #3749`, printed `LED desk lamp #3749`); line_items[32].description wrong (raw `P913-61 Webcam 1080p #6130`, printed `Webcam 1080p #6130`); line_items[33].description wrong (raw `B755-68 Ergonomic office chair #3241`, printed `Ergonomic office chair #3241`); line_items[34].description wrong (raw `D873-89 Standing desk frame #2406`, printed `Standing desk frame #2406`); line_items[35].description wrong (raw `M637-87 Acoustic wall panel #9294`, printed `Acoustic wall panel #9294`); line_items[36].description wrong (raw `K284-58 Monitor arm #7415`, printed `Monitor arm #7415`); line_items[37].description wrong (raw `E198-13 Cable management kit #3872`, printed `Cable management kit #3872`); line_items[38].description wrong (raw `T427-21 Acoustic wall panel #8559`, printed `Acoustic wall panel #8559`); line_items[39].description wrong (raw `E286-46 Whiteboard markers (pack of 12) #3962`, printed `Whiteboard markers (pack of 12) #3962`); line_items[40].description wrong (raw `F469-16 Monitor arm #9237`, printed `Monitor arm #9237`); line_items[41].description wrong (raw `A385-40 Acoustic wall panel #4945`, printed `Acoustic wall panel #4945`); line_items[42].description wrong (raw `C939-61 Network switch, 8-port #8024`, printed `Network switch, 8-port #8024`) |
| test-20 | success | 135 of 177 fields | 135 of 177 fields | 0 | 42 of 42 matched, 0 extra | LINE_AMOUNT_MISMATCH | line_items[0].description wrong (raw `T635-49 Whiteboard markers (pack of 12) #7870`, printed `Whiteboard markers (pack of 12) #7870`); line_items[1].description wrong (raw `D587-59 Network switch, 8-port #3595`, printed `Network switch, 8-port #3595`); line_items[2].description wrong (raw `A558-70 Label printer tape #2501`, printed `Label printer tape #2501`); line_items[3].description wrong (raw `H579-54 Laser toner cartridge #4933`, printed `Laser toner cartridge #4933`); line_items[4].description wrong (raw `M844-88 USB-C docking station #7713`, printed `USB-C docking station #7713`); line_items[5].description wrong (raw `D304-87 Standing desk frame #4363`, printed `Standing desk frame #4363`); line_items[6].description wrong (raw `A802-50 Label printer tape #3439`, printed `Label printer tape #3439`); line_items[7].description wrong (raw `F889-14 Laser toner cartridge #8411`, printed `Laser toner cartridge #8411`); line_items[8].description wrong (raw `B752-88 Ergonomic office chair #3649`, printed `Ergonomic office chair #3649`); line_items[9].description wrong (raw `B719-10 Laser toner cartridge #9805`, printed `Laser toner cartridge #9805`); line_items[10].description wrong (raw `T448-20 Acoustic wall panel #8791`, printed `Acoustic wall panel #8791`); line_items[11].description wrong (raw `T961-98 Cable management kit #1669`, printed `Cable management kit #1669`); line_items[12].description wrong (raw `P706-63 Laser toner cartridge #1808`, printed `Laser toner cartridge #1808`); line_items[13].description wrong (raw `R698-76 Webcam 1080p #6651`, printed `Webcam 1080p #6651`); line_items[14].description wrong (raw `C982-50 Webcam 1080p #4555`, printed `Webcam 1080p #4555`); line_items[15].description wrong (raw `P177-88 Ergonomic office chair #9714`, printed `Ergonomic office chair #9714`); line_items[16].description wrong (raw `P487-67 Acoustic wall panel #2532`, printed `Acoustic wall panel #2532`); line_items[17].description wrong (raw `K757-56 Label printer tape #5308`, printed `Label printer tape #5308`); line_items[18].description wrong (raw `H690-60 Cable management kit #3546`, printed `Cable management kit #3546`); line_items[19].description wrong (raw `C533-71 LED desk lamp #9832`, printed `LED desk lamp #9832`); line_items[20].description wrong (raw `M394-42 A4 copy paper (box of 5 reams) #8600`, printed `A4 copy paper (box of 5 reams) #8600`); line_items[21].description wrong (raw `C461-35 USB-C docking station #6032`, printed `USB-C docking station #6032`); line_items[22].description wrong (raw `T576-20 Network switch, 8-port #8533`, printed `Network switch, 8-port #8533`); line_items[23].description wrong (raw `H601-97 USB-C docking station #9444`, printed `USB-C docking station #9444`); line_items[24].description wrong (raw `A817-79 LED desk lamp #9559`, printed `LED desk lamp #9559`); line_items[25].description wrong (raw `C243-43 Label printer tape #4941`, printed `Label printer tape #4941`); line_items[26].description wrong (raw `T374-40 Acoustic wall panel #5023`, printed `Acoustic wall panel #5023`); line_items[27].description wrong (raw `D816-96 Label printer tape #5821`, printed `Label printer tape #5821`); line_items[28].description wrong (raw `E288-71 A4 copy paper (box of 5 reams) #3099`, printed `A4 copy paper (box of 5 reams) #3099`); line_items[29].description wrong (raw `T464-47 Acoustic wall panel #7929`, printed `Acoustic wall panel #7929`); line_items[30].description wrong (raw `P842-79 Monitor arm #5754`, printed `Monitor arm #5754`); line_items[31].description wrong (raw `B963-32 Wireless keyboard #8361`, printed `Wireless keyboard #8361`); line_items[32].description wrong (raw `P100-28 Webcam 1080p #6722`, printed `Webcam 1080p #6722`); line_items[33].description wrong (raw `F192-47 Standing desk frame #2628`, printed `Standing desk frame #2628`); line_items[34].description wrong (raw `A285-52 Ergonomic office chair #4848`, printed `Ergonomic office chair #4848`); line_items[35].description wrong (raw `F335-74 Label printer tape #4927`, printed `Label printer tape #4927`); line_items[36].description wrong (raw `A638-76 Network switch, 8-port #9876`, printed `Network switch, 8-port #9876`); line_items[37].description wrong (raw `T526-32 Cable management kit #9205`, printed `Cable management kit #9205`); line_items[38].description wrong (raw `D744-40 Standing desk frame #1738`, printed `Standing desk frame #1738`); line_items[39].description wrong (raw `D530-34 Network switch, 8-port #2602`, printed `Network switch, 8-port #2602`); line_items[40].description wrong (raw `M782-52 Wireless keyboard #1948`, printed `Wireless keyboard #1948`); line_items[41].description wrong (raw `E389-94 Whiteboard markers (pack of 12) #4986`, printed `Whiteboard markers (pack of 12) #4986`) |
| test-22 | success | 157 of 157 fields | 155 of 157 fields | 2 | 37 of 37 matched, 0 extra | DATE_AMBIGUOUS | none |
| test-24 | success | 154 of 161 fields | 154 of 161 fields | 0 | 38 of 38 matched, 0 extra | none | line_items[31].description wrong (raw `B769-75 Label printer tape #2835`, printed `Label printer tape #2835`); line_items[32].description wrong (raw `T135-83 Whiteboard markers (pack of 12) #4778`, printed `Whiteboard markers (pack of 12) #4778`); line_items[33].description wrong (raw `F810-62 USB-C docking station #8606`, printed `USB-C docking station #8606`); line_items[34].description wrong (raw `R814-86 Whiteboard markers (pack of 12) #3229`, printed `Whiteboard markers (pack of 12) #3229`); line_items[35].description wrong (raw `D415-38 USB-C docking station #7042`, printed `USB-C docking station #7042`); line_items[36].description wrong (raw `F607-76 Laser toner cartridge #3316`, printed `Laser toner cartridge #3316`); line_items[37].description wrong (raw `R801-63 A4 copy paper (box of 5 reams) #7345`, printed `A4 copy paper (box of 5 reams) #7345`) |

### Wrapped descriptions (test-04, test-22)

Group: layer 1 186 of 186 fields, layer 2 184 of 186 fields, 2 ambiguous, lines fully right 42 of 42. Rest of the set (22 documents): layer 1 1163 of 1458, layer 2 1364 of 1458, lines 223 of 315.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-04 | success | 29 of 29 fields | 29 of 29 fields | 0 | 5 of 5 matched, 0 extra | none | none |
| test-22 | success | 157 of 157 fields | 155 of 157 fields | 2 | 37 of 37 matched, 0 extra | DATE_AMBIGUOUS | none |

### Prompt-injection line (test-03, test-09)

Group: layer 1 43 of 54 fields, layer 2 54 of 54 fields, 0 ambiguous, lines fully right 9 of 9. Rest of the set (22 documents): layer 1 1306 of 1590, layer 2 1494 of 1590, lines 256 of 348.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-03 | success | 29 of 29 fields | 29 of 29 fields | 0 | 5 of 5 matched, 0 extra | TOTAL_MISMATCH | none |
| test-09 | success | 14 of 25 fields | 25 of 25 fields | 0 | 4 of 4 matched, 0 extra | none | none |

### Deliberate arithmetic error (test-03, test-08, test-16, test-20)

Group: layer 1 207 of 268 fields, layer 2 226 of 268 fields, 0 ambiguous, lines fully right 16 of 58. Rest of the set (20 documents): layer 1 1142 of 1376, layer 2 1322 of 1376, lines 249 of 299.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-03 | success | 29 of 29 fields | 29 of 29 fields | 0 | 5 of 5 matched, 0 extra | TOTAL_MISMATCH | none |
| test-08 | success | 21 of 21 fields | 21 of 21 fields | 0 | 3 of 3 matched, 0 extra | SUBTOTAL_MISMATCH | none |
| test-16 | success | 22 of 41 fields | 41 of 41 fields | 0 | 8 of 8 matched, 0 extra | LINE_AMOUNT_MISMATCH | none |
| test-20 | success | 135 of 177 fields | 135 of 177 fields | 0 | 42 of 42 matched, 0 extra | LINE_AMOUNT_MISMATCH | line_items[0].description wrong (raw `T635-49 Whiteboard markers (pack of 12) #7870`, printed `Whiteboard markers (pack of 12) #7870`); line_items[1].description wrong (raw `D587-59 Network switch, 8-port #3595`, printed `Network switch, 8-port #3595`); line_items[2].description wrong (raw `A558-70 Label printer tape #2501`, printed `Label printer tape #2501`); line_items[3].description wrong (raw `H579-54 Laser toner cartridge #4933`, printed `Laser toner cartridge #4933`); line_items[4].description wrong (raw `M844-88 USB-C docking station #7713`, printed `USB-C docking station #7713`); line_items[5].description wrong (raw `D304-87 Standing desk frame #4363`, printed `Standing desk frame #4363`); line_items[6].description wrong (raw `A802-50 Label printer tape #3439`, printed `Label printer tape #3439`); line_items[7].description wrong (raw `F889-14 Laser toner cartridge #8411`, printed `Laser toner cartridge #8411`); line_items[8].description wrong (raw `B752-88 Ergonomic office chair #3649`, printed `Ergonomic office chair #3649`); line_items[9].description wrong (raw `B719-10 Laser toner cartridge #9805`, printed `Laser toner cartridge #9805`); line_items[10].description wrong (raw `T448-20 Acoustic wall panel #8791`, printed `Acoustic wall panel #8791`); line_items[11].description wrong (raw `T961-98 Cable management kit #1669`, printed `Cable management kit #1669`); line_items[12].description wrong (raw `P706-63 Laser toner cartridge #1808`, printed `Laser toner cartridge #1808`); line_items[13].description wrong (raw `R698-76 Webcam 1080p #6651`, printed `Webcam 1080p #6651`); line_items[14].description wrong (raw `C982-50 Webcam 1080p #4555`, printed `Webcam 1080p #4555`); line_items[15].description wrong (raw `P177-88 Ergonomic office chair #9714`, printed `Ergonomic office chair #9714`); line_items[16].description wrong (raw `P487-67 Acoustic wall panel #2532`, printed `Acoustic wall panel #2532`); line_items[17].description wrong (raw `K757-56 Label printer tape #5308`, printed `Label printer tape #5308`); line_items[18].description wrong (raw `H690-60 Cable management kit #3546`, printed `Cable management kit #3546`); line_items[19].description wrong (raw `C533-71 LED desk lamp #9832`, printed `LED desk lamp #9832`); line_items[20].description wrong (raw `M394-42 A4 copy paper (box of 5 reams) #8600`, printed `A4 copy paper (box of 5 reams) #8600`); line_items[21].description wrong (raw `C461-35 USB-C docking station #6032`, printed `USB-C docking station #6032`); line_items[22].description wrong (raw `T576-20 Network switch, 8-port #8533`, printed `Network switch, 8-port #8533`); line_items[23].description wrong (raw `H601-97 USB-C docking station #9444`, printed `USB-C docking station #9444`); line_items[24].description wrong (raw `A817-79 LED desk lamp #9559`, printed `LED desk lamp #9559`); line_items[25].description wrong (raw `C243-43 Label printer tape #4941`, printed `Label printer tape #4941`); line_items[26].description wrong (raw `T374-40 Acoustic wall panel #5023`, printed `Acoustic wall panel #5023`); line_items[27].description wrong (raw `D816-96 Label printer tape #5821`, printed `Label printer tape #5821`); line_items[28].description wrong (raw `E288-71 A4 copy paper (box of 5 reams) #3099`, printed `A4 copy paper (box of 5 reams) #3099`); line_items[29].description wrong (raw `T464-47 Acoustic wall panel #7929`, printed `Acoustic wall panel #7929`); line_items[30].description wrong (raw `P842-79 Monitor arm #5754`, printed `Monitor arm #5754`); line_items[31].description wrong (raw `B963-32 Wireless keyboard #8361`, printed `Wireless keyboard #8361`); line_items[32].description wrong (raw `P100-28 Webcam 1080p #6722`, printed `Webcam 1080p #6722`); line_items[33].description wrong (raw `F192-47 Standing desk frame #2628`, printed `Standing desk frame #2628`); line_items[34].description wrong (raw `A285-52 Ergonomic office chair #4848`, printed `Ergonomic office chair #4848`); line_items[35].description wrong (raw `F335-74 Label printer tape #4927`, printed `Label printer tape #4927`); line_items[36].description wrong (raw `A638-76 Network switch, 8-port #9876`, printed `Network switch, 8-port #9876`); line_items[37].description wrong (raw `T526-32 Cable management kit #9205`, printed `Cable management kit #9205`); line_items[38].description wrong (raw `D744-40 Standing desk frame #1738`, printed `Standing desk frame #1738`); line_items[39].description wrong (raw `D530-34 Network switch, 8-port #2602`, printed `Network switch, 8-port #2602`); line_items[40].description wrong (raw `M782-52 Wireless keyboard #1948`, printed `Wireless keyboard #1948`); line_items[41].description wrong (raw `E389-94 Whiteboard markers (pack of 12) #4986`, printed `Whiteboard markers (pack of 12) #4986`) |

### Document ambiguity (oracle) (test-02, test-17, test-22)

Group: layer 1 215 of 215 fields, layer 2 211 of 215 fields, 4 ambiguous, lines fully right 47 of 47. Rest of the set (21 documents): layer 1 1134 of 1429, layer 2 1337 of 1429, lines 218 of 310.

| Document | Outcome | Layer 1 | Layer 2 | Ambiguous | Lines | Flags | Errors |
|---|---|---|---|---|---|---|---|
| test-02 | success | 21 of 21 fields | 20 of 21 fields | 1 | 3 of 3 matched, 0 extra | CURRENCY_AMBIGUOUS | none |
| test-17 | success | 37 of 37 fields | 36 of 37 fields | 1 | 7 of 7 matched, 0 extra | CURRENCY_AMBIGUOUS | none |
| test-22 | success | 157 of 157 fields | 155 of 157 fields | 2 | 37 of 37 matched, 0 extra | DATE_AMBIGUOUS | none |

## Error causes (automatic; confirm in error_notes.md)

| Cause | Error fields |
|---|---|
| extraction | 92 |
