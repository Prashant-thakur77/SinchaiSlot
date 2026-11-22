# Altivar Solar ATV320: Modbus register map notes

These notes cover `register_map.yaml` and `fault_codes.yaml`. Every value in those files comes from the Schneider Electric documents listed below, with a document reference and page (or spreadsheet row) on each entry. Entries marked `verified: false` carry a note that says which part is unconfirmed.

## Source documents

All files were downloaded from `download.schneider-electric.com` (served from `download.se.com`) and stored in `docs/schneider/manuals/`.

| Ref | Title | Version | URL |
|---|---|---|---|
| NVE41308 | Altivar Machine ATV320 Modbus Serial Link Manual | 01 (04/2016), 84 p. | https://download.schneider-electric.com/doc/NVE41308/ATV320_Modbus_manual_EN_NVE41308_01.pdf |
| NVE41295 | ATV320 Programming Manual | 06 (NVE41295.06), 460 p. | https://download.schneider-electric.com/doc/NVE41295/ATV320_Programming_Manual_EN_NVE41295_06.pdf |
| NVE41316 | ATV320 Communication Parameters (address spreadsheet) | V3.5 (03 Jan 2022), .xlsx | https://download.schneider-electric.com/doc/NVE41316/ATV320_CommunicationParameters_NVE41316_V3.5.xlsx |
| PKR47019 | Altivar Solar ATV320 User Manual (drives for pumps with photovoltaic arrays) | 03 (11/2024), 186 p. | https://download.schneider-electric.com/doc/PKR47019/Altivar-Solar-ATV320-User-Manual-EN-PKR47019-03.pdf |

URLs that did not work:

- `https://download.schneider-electric.com/files?p_Doc_Ref=NVE41308&p_enDocType=User%20guide&p_File_Name=NVE41308.pdf` (and the same pattern for NVE41295 and NVE41294): HTTP 404. The `/doc/<ref>/<file name>` pattern above works.
- `https://download.schneider-electric.com/doc/NVE41295/ATV320_Programming_Manual_EN_NVE41295_04.pdf`: HTTP 404. Version 06 is the current one.
- `https://www.se.com/ww/en/download/document/NVE41316`: HTTP 403 for scripted requests. The direct file URL above works.
- NVE41294 is not the communication parameters document. The ATV320 communication parameters file is NVE41316.
- The combined Modbus/CANopen manual does not exist as a single document. CANopen is NVE41309 and was not downloaded because it is not needed for Modbus RTU.
- ATV600 / Altivar Process solar pumping: not downloaded. On se.com, "Altivar Solar" is the ATV320-based range (PKR47019 covers it), so the ATV600 documents are out of scope.

Page numbers are the printed page numbers. In all three PDFs they match the PDF page index. Spreadsheet references give the sheet name and the row number in that sheet (row 1 is the header).

## Modbus basics (confirmed)

| Item | Value | Source |
|---|---|---|
| Transmission mode | RTU, CRC16 | NVE41308 p.17 |
| Function codes | 03 read holding registers (max 63 words), 06 write single register, 16 (0x10) write multiple registers (max 61 words), 23 (0x17) read/write multiple registers (max 20 + 20 words), 43/14 (0x2B/0x0E) read device identification, 08 diagnostics | NVE41308 p.13, p.18 |
| Register addressing | The logical address is the PDU register address. For example, W3102 is requested as 0x0C1E. There is no 40001 offset and no -1. | NVE41308 p.19 |
| Byte order | High-order byte first in each 16-bit word | NVE41308 p.18 |
| Slave address [Modbus Address] Add (6001) | 1..247. **Factory setting is OFF (0)**, so the drive does not respond until an address is set. A restart is required after the change. Address 0 is broadcast. | NVE41308 p.17, p.32, p.60 |
| Baud rate tbr (6003) | 4800 / 9600 / 19200 / 38400. Factory 19200. | NVE41308 p.32 |
| Format tFO (6004) | 8O1 / 8E1 / 8N1 / 8N2. Factory 8E1. | NVE41308 p.32 |
| Timeout tto (6005) | 0.1..30 s. Factory 10 s. On expiry the drive raises SLF1, with the reaction set by SLL (7010; factory: freewheel stop with fault). | NVE41308 p.33, p.66 |
| Device identification (FC 43/14) | Object 0 "Schneider Electric", object 1 product reference (for example ATV320xxxxxx), object 2 version "MMmm" | NVE41308 p.21 |
| Communication scanner | Reading 12741.. (NM1..NM8) returns the parameters addressed by NMA1..8 (factory: ETA 3201, RFRD 8604). Writing 12761.. (NC1..NC8) writes the parameters addressed by NCA1..8 (factory: CMD 8501, LFRD 8602). | NVE41308 p.63; NVE41316 Parameters rows 212-227, 629-644 |

## Key registers (confirmed)

| Mnemonic | Address | Access | Scale / unit | Source |
|---|---|---|---|---|
| CMD control word | 8501 | RW | bit field | NVE41316 Parameters row 3; NVE41308 p.46 |
| LFR frequency reference | 8502 | RW | 0.1 Hz, signed | NVE41316 row 6; NVE41295 p.46 |
| LFRD speed setpoint | 8602 | RW | 1 rpm, signed | NVE41316 row 5; NVE41308 p.63 |
| ETA status word | 3201 | R | bit field | NVE41316 row 10; NVE41308 p.49 |
| ETI extended status | 3206 | R | bit field | NVE41316 row 12 |
| HMIS drive state | 3240 | R | enumeration | NVE41316 row 11 |
| RFR output frequency | 3202 | R | 0.1 Hz, signed | NVE41316 row 21; NVE41295 p.49 |
| RFRD output speed | 8604 | R | 1 rpm, signed | NVE41316 row 20; NVE41308 p.63 |
| LCR motor current | 3204 | R | 0.1 A | NVE41316 row 23; NVE41295 p.50 |
| OTR motor torque | 3205 | R | 0.1 %, signed | NVE41316 row 22; NVE41295 p.50 |
| ULN mains voltage | 3207 | R | 0.1 V | NVE41316 row 34; NVE41295 p.49-50 |
| UOP motor voltage | 3208 | R | 1 V | NVE41316 row 24; NVE41295 p.50 |
| THD drive thermal state | 3209 | R | 1 % (118 % = OHF) | NVE41316 row 35; NVE41295 p.50 |
| OPR motor power | 3211 | R | 1 % of nominal, signed | NVE41316 row 25; NVE41295 p.50 |
| APH energy | 3230 | R | Wh/kWh/MWh, unit from UNT bits 0-1 | NVE41316 row 758, Registers rows 671-674; NVE41295 p.66 |
| RTH motor run time | 3231 | R | s/min/h, unit from UNT bits 4-5 | NVE41316 row 37; NVE41295 p.66-67 |
| PTH power-on time | 3233 | R | s/min/h, unit from UNT bits 2-3 | NVE41316 row 38; NVE41295 p.67 |
| UNT counter units | 3234 | R | bit field | NVE41316 row 1071 |
| THR motor thermal state | 9630 | R | 1 % (118 % = OLF) | NVE41316 row 36; NVE41295 p.50 |
| LFT last fault | 7121 | R | enumeration | NVE41316 row 51, Enumerations rows 313-373 |
| DP1..DP8 fault history | 7201..7208 | R | LFT enumeration | NVE41316 rows 72-184 |

The YAML file also lists the configuration registers used for Modbus control (FR1, FR2, CHCF, CD1, CD2, CCS, RFC, RRS, RIN, DOTD, QSTD, STT, ACC, DEC, HSP, LSP, TFR), the motor nameplate registers, and the process underload (dry-run) settings ULT, LUL, LUN, RMUD, SRB, UDL and FTU.

## Control word CMD (8501), CiA402 profile (NVE41308 p.46)

| Bit | Meaning |
|---|---|
| 0 | Switch on |
| 1 | Enable voltage |
| 2 | Quick stop (0 = quick stop active) |
| 3 | Enable operation (run) |
| 4-6 | Reserved (0) |
| 7 | Fault reset on a 0 to 1 transition |
| 8 | Halt (stop per [Type of stop] Stt while staying in Operation enabled) |
| 9-10 | Reserved (0) |
| 11 | Default assignment on standard ATV320: reverse direction (0 forward, 1 reverse) (p.46, p.48) |
| 12-15 | Assignable (C112..C115) |

Command values: Shutdown 0x0006, Switch on 0x0007, Enable operation 0x000F, Disable operation 0x0007, Disable voltage 0x0000, Quick stop 0x0002, Fault reset 0x0080 (rising edge).

## Status word ETA (3201) (NVE41308 p.49)

Bits: 0 ready to switch on, 1 switched on, 2 operation enabled, 3 fault, 4 voltage enabled, 5 quick stop (0 = active), 6 switch on disabled, 7 warning, 9 remote (command or reference from the fieldbus), 10 target reached, 11 internal limit active, 14 stop by the STOP key, 15 direction (1 = reverse).

State decoding uses `ETA & 0x006F`:

| Masked value | State |
|---|---|
| 0x0040 | 2 Switch on disabled |
| 0x0021 | 3 Ready to switch on |
| 0x0023 | 4 Switched on |
| 0x0027 | 5 Operation enabled |
| 0x0007 | 6 Quick stop active |
| 0x0008 .. 0x0028 | 8 Fault |

On p.54, the unmasked status word in "Ready to switch on" reads 0x21 when the power stage supply is absent (display nLP) and 0x31 when it is present (display rdY). Bit 4 is the voltage-enabled flag.

## Start and stop sequence over Modbus (CiA402)

Prerequisites (NVE41308 p.60, p.70; PKR47019 p.96):

1. Set the Modbus address Add (6001) to 1..247 and restart the drive. The factory setting is OFF.
2. Standard ATV320: set FR1 (8413) = 164 (MDB) and CHCF (8401) = 1 (SIM, combined mode). Command and reference then both come from Modbus.
3. Altivar Solar factory settings are different (PKR47019 p.96): CHCF = SEP, CCS = LI4, RFC = LI4, FR2 = MDB, RRS = NO, RIN = YES, ACC = DEC = 100 (10.0 s). The Modbus reference is reference channel 2 and is selected by DI4. Command channel switching is also on DI4, and CD2 (8424) factory setting is MDB. Either drive DI4 accordingly or reconfigure FR1/CD1/CCS/RFC. Reverse is disabled by default on the solar product.

Sequence (drive supplied through its power stage, NVE41308 p.51-52):

1. Write CMD = 0x0006 (Shutdown). Wait until `ETA & 0x6F == 0x21`.
2. Optionally write CMD = 0x0007 (Switch on). Wait until `ETA & 0x6F == 0x23`. The manual says Enable operation alone is enough from state 3.
3. Write a non-zero reference: LFR (8502, 0.1 Hz) or LFRD (8602, rpm). Per p.43, Enable operation is accepted only after the reference has been received once when the channel provides both command and reference.
4. Write CMD = 0x000F (Enable operation, run). Wait until `ETA & 0x6F == 0x27`.
5. Reverse (standard ATV320 with RRS on bit 11): CMD = 0x080F. Halt without leaving Operation enabled: CMD = 0x010F.
6. Stop: CMD = 0x0007 (Disable operation). The stop follows DOTD (8652; factory 1 = ramp stop) and the drive returns to Switched on. CMD = 0x0000 (Disable voltage) gives freewheel to Switch on disabled. CMD = 0x0002 (Quick stop) gives a fast stop, then the drive follows QSTD (factory FST6: stays in Quick stop active until Disable voltage).
7. Fault reset: once the cause is gone, write CMD = 0x0000 then 0x0080 (rising edge on bit 7). The drive goes to Switch on disabled. Then restart from step 1.

Several single register writes (FC 06) or one FC 16 write starting at 8501 (CMD, LFR) can be used. For cyclic exchange, FC 23 on the scanner (read from 12741, write to 12761) sends CMD and LFRD and returns ETA and RFRD in one transaction (p.63).

## Faults

`fault_codes.yaml` holds 62 entries. Of these, 60 are verified: each has a mnemonic, the numeric LFT value (NVE41316 Enumerations), and the description, probable causes, remedies and clearing method from PKR47019.03 p.162-179, cross-checked against NVE41295.06 p.404-420. The wording is the same apart from page cross-references.

- Dry-run detection uses the process underload function: ULF, LFT value 100 (PKR47019 p.118-120, p.179). It is configured with ULT, LUN, LUL, RMUD, SRB, UDL and FTU.
- Process overload is OLC, LFT value 101.
- When PV power drops (low light), the DC bus falls below the USF threshold. The solar firmware holds the drive in a Low Light (LL) state for LITR seconds instead of restarting at once (PKR47019 p.122).
- PHF detection is disabled when PVSA (MPPT) is active (PKR47019 p.99, p.121).
- The solar manual shows SCF5 as "SCFS" in its fault headings (7-segment rendering). The clearing table on p.160 and the LFT enumeration (value 56) use SCF5.

## UNVERIFIED items

- **SCF2**: not present in any ATV320 manual or in the LFT enumeration. It does not appear to exist on the ATV320.
- **TSF (Tank probe error)**: documented in PKR47019 p.178 (causes and remedies verified). Its numeric LFT value is not in NVE41316 V3.5.
- **Solar-specific parameters with no published Modbus address**: PVSA, LDCA, LITR, GPPT, GPTT, SLFV (estimated flow, m3/h), PVLD (pumped volume, m3), PVLT (cumulated volume, dam3), PVCS, PCQ1-5, PCP1-5, JAMS. Their meaning, range and units are documented in PKR47019. Their fieldbus addresses are not published in NVE41316 V3.5, which covers the standard ATV320 firmware, or anywhere in PKR47019.
- **DC bus / PV input voltage**: no dedicated register is documented. ULN (3207) is "based on DC bus measurement" (NVE41295 p.50). Its exact meaning on a DC (PV) supply is not documented.
- **PV / solar input power**: no register is documented. OPR gives motor power in % of nominal.
- **MPPT / GMPPT running state**: shown only on the display ("GPPT"). No fieldbus register is documented.
- **Low Light state value in HMIS**, and **CFG = SUN numeric value**: not in the NVE41316 enumerations.
- **SPD (12004) scale**: the unit is rpm, but the fieldbus scale factor is not stated. Use RFRD (8604, 1 rpm) instead.
- **NPR (9613) scale**: not stated (kW or HP depending on BFR).

## Discrepancies between sources

- The programming manual (p.66-67) calls the counter unit parameter [Unit] UNI. The communication parameters file calls it UNT at 3234. The bit layout is in NVE41316 Registers rows 671-684.
- LUN factory value: 60 % in NVE41316, 50 % in PKR47019 p.119.
- NC1..NC8 (12761..12768) are marked read-only in NVE41316 but are written by the master in the NVE41308 p.63 example.
- NVE41316 V3.5 describes the standard ATV320 firmware. The CFG enumeration has no SUN value, and the solar parameters are missing. Check addresses against a real Altivar Solar drive (for example with SoMachine or DTM browsing) before relying on them for the solar-only functions.
