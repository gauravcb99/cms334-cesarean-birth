#!/usr/bin/env python3
"""
CMS334v7 Cesarean Birth (PC-02): the published eCQM logic, implemented in SQL
and tested on 15 synthetic deliveries at 2 synthetic hospitals.

EVERY PATIENT, HOSPITAL, DATE AND RECORD IN THIS FILE IS SYNTHETIC.
No CMS, OBI, hospital or patient data was used.

Source of record (read November 11, 2026)
  CMS334v7, eCQM Version Number 7.1.000, 2026 reporting period
  Measurement Period: January 1, 2026 through December 31, 2026
  Measure Steward: The Joint Commission.  CBE Number 0471e.  Short name PC-02.
  Measure page:  https://ecqi.healthit.gov/ecqm/hosp-inpt/2026/cms0334v7
  Specification: https://ecqi.healthit.gov/sites/default/files/ecqm/measures/CMS334-v7.1.000-QDM.html

  CMS334v8 (8.1.000) is posted for the 2027 reporting period:
                 https://ecqi.healthit.gov/sites/default/files/ecqm/measures/CMS334-v8.1.000-QDM.html
  Its Population Criteria, Definitions and Functions read the same as v7.1.000
  for every rule implemented here. It renames one definition and one value set
  (same OID). Its release notes also list value set content updates, which do
  not touch this file because no value set codes are used here.

Citations in the comments name the section of the v7.1.000 specification file:
  PC  = Population Criteria      Def = Definitions
  Fn  = Functions                G   = Guidance (measure header)

How the synthetic data stands in for the specification's terminology
  The specification binds each data element to a value set (by OID) or to a
  direct reference code. No codes are reproduced here. Each synthetic record
  carries the NAME of the value set or direct reference code it is taken to
  belong to, so value set membership is an input to this test.

  Value sets read by this code (names and OIDs from the Terminology section):
    Encounter Inpatient                              2.16.840.1.113883.3.666.5.307
    Delivery Procedures                              2.16.840.1.113762.1.4.1045.59
    Estimated Gestational Age at Delivery            2.16.840.1.113762.1.4.1045.26
    37 to 42 Plus Weeks Gestation                    2.16.840.1.113762.1.4.1110.68
    Delivery of Singleton                            2.16.840.1.113762.1.4.1045.99
    Abnormal Presentation                            2.16.840.1.113762.1.4.1045.105
    Placenta Accreta Spectrum Previa or Vasa Previa  2.16.840.1.113762.1.4.1110.37
    Genital Herpes                                   2.16.840.1.113883.3.464.1003.110.12.1049
    Cesarean Birth                                   2.16.840.1.113883.3.117.1.7.1.282
  Direct reference codes read by this code (LOINC, named in Terminology):
    Date and time of obstetric delivery; Delivery date Estimated;
    [#] Pregnancies; [#] Parity; [#] Births.preterm; [#] Births.term

Not implemented (see also the one-page summary)
  * Fn PCMaternal.HospitalizationWithEDOBTriageObservation extends the
    hospitalization back through an emergency department or OB triage visit and
    an observation stay that end within 1 hour of the next start. Here the
    hospitalization is inpatient admission to discharge. Value sets not read:
    ED Visit and OB Triage (2.16.840.1.113762.1.4.1029.369) and
    Observation Services (2.16.840.1.113762.1.4.1111.143).
  * Supplemental data elements (payer, race, ethnicity, sex) and QRDA reporting.
  * Each synthetic record has one timestamp. The specification also accepts a
    period for each element (Fn Global.NormalizeInterval, Global.EarliestOf).

Run:  python3 cms334_cesarean_birth_spec_test.py
Needs only the Python standard library (sqlite3).
"""

import sqlite3
import sys

# Measurement period of CMS334v7 eCQM version 7.1.000 (measure header).
MP_START, MP_END = "2026-01-01", "2026-12-31"


# =============================================================================
# 1. EXPECTED RESULTS, worked by hand from the specification before the query
#    below was written. Each tuple is (IP, DEN, EXCL, NUM).
#      IP   = Initial Population             DEN = Denominator
#      EXCL = Denominator Exclusion          NUM = Numerator counted in the rate,
#                                                  that is, after exclusions
# =============================================================================
EXPECTED = {
    # id        (IP, DEN, EXCL, NUM)   why
    "SYN-D01": ((1, 1, 0, 0), "Baseline. G1 P0, calculated 39 weeks (39w3d), singleton, vaginal."),
    "SYN-D02": ((1, 1, 0, 1), "Term boundary, in. Due date 21 days after delivery: (280-21) div 7 = 37. "
                              "Gravida 1 with parity not recorded. Cesarean."),
    "SYN-D03": ((1, 0, 0, 0), "Term boundary, out. Due date 22 days after delivery: (280-22) div 7 = 36. "
                              "A discrete field of 37 weeks exists but is not read, because the "
                              "calculated value is available."),
    "SYN-D04": ((1, 1, 0, 0), "No due date. Discrete gestational age field of 38 weeks, 2 hours before delivery."),
    "SYN-D05": ((1, 1, 0, 1), "No due date and no discrete field. Encounter diagnosis in "
                              "'37 to 42 Plus Weeks Gestation'. Cesarean."),
    "SYN-D06": ((1, 0, 0, 0), "Multiple birth: no 'Delivery of Singleton' encounter diagnosis. Cesarean, not counted."),
    "SYN-D07": ((1, 1, 0, 0), "G2 P0: parity 0 qualifies although gravida is 2. Vaginal."),
    "SYN-D08": ((1, 0, 0, 0), "G2 P1 with one prior term birth: not nulliparous. Cesarean, not counted."),
    "SYN-D09": ((1, 1, 0, 1), "Gravida and parity not recorded. Preterm 0 and term 0 before delivery qualify. "
                              "Term births updated to 1 after delivery is not read. Cesarean."),
    "SYN-D10": ((1, 1, 1, 0), "Abnormal presentation assessment during the stay, before delivery. Cesarean, excluded."),
    "SYN-D11": ((1, 1, 1, 0), "Abnormal presentation as an encounter diagnosis, no assessment. Cesarean, excluded."),
    "SYN-D12": ((1, 1, 0, 0), "Abnormal presentation assessed at a prenatal visit 20 days before admission only. "
                              "Not during the stay, so not excluded. Vaginal."),
    "SYN-D13": ((1, 1, 1, 0), "Encounter diagnosis in 'Placenta Accreta Spectrum Previa or Vasa Previa'. Cesarean, excluded."),
    "SYN-D14": ((1, 1, 1, 0), "Encounter diagnosis in 'Genital Herpes'. Cesarean, excluded."),
    "SYN-D15": ((0, 0, 0, 0), "Delivered December 31, 2026, discharged January 2, 2027: "
                              "the stay ends outside the measurement period."),
}

# Expected hospital roll-up: (IP, DEN, EXCL, DEN after exclusions, NUM)
EXPECTED_ROLLUP = {
    "SYN-HOSP-A": (7, 5, 2, 3, 1),   # rate 1 of 3
    "SYN-HOSP-B": (7, 6, 2, 4, 2),   # rate 2 of 4
}


# =============================================================================
# 2. SYNTHETIC DATA
# =============================================================================
SCHEMA = """
CREATE TABLE encounter (            -- QDM "Encounter, Performed"
    encounter_id TEXT PRIMARY KEY,  -- synthetic
    patient_id   TEXT NOT NULL,     -- synthetic, one delivery per synthetic patient
    hospital_id  TEXT NOT NULL,     -- synthetic
    birth_date   TEXT NOT NULL,
    value_set    TEXT NOT NULL,     -- value set NAME, not a code
    admit_dt     TEXT NOT NULL,     -- start of relevantPeriod
    discharge_dt TEXT NOT NULL      -- end of relevantPeriod
);
CREATE TABLE encounter_diagnosis (  -- the encounter's "diagnoses" attribute
    encounter_id TEXT NOT NULL,
    value_set    TEXT NOT NULL      -- value set NAME, not a code
);
CREATE TABLE procedure (            -- QDM "Procedure, Performed"
    patient_id   TEXT NOT NULL,
    value_set    TEXT NOT NULL,     -- value set NAME, not a code
    start_dt     TEXT NOT NULL
);
CREATE TABLE assessment (           -- QDM "Assessment, Performed"
    patient_id   TEXT NOT NULL,
    item         TEXT NOT NULL,     -- value set or direct reference code NAME
    recorded_dt  TEXT NOT NULL,     -- relevantDatetime
    result                          -- datetime, date, weeks or count; NULL if none
);
"""

INPT, DELIV, CSEC = "Encounter Inpatient", "Delivery Procedures", "Cesarean Birth"
SINGLE, TERM_DX = "Delivery of Singleton", "37 to 42 Plus Weeks Gestation"
ABN, PREVIA, HSV = "Abnormal Presentation", "Placenta Accreta Spectrum Previa or Vasa Previa", "Genital Herpes"
TOD, EDD, EGA = "Date and time of obstetric delivery", "Delivery date Estimated", "Estimated Gestational Age at Delivery"
GRAV, PAR, PRETERM, TERMB = "[#] Pregnancies", "[#] Parity", "[#] Births.preterm", "[#] Births.term"

# One dict per synthetic delivery. "cs" True adds a Cesarean Birth procedure.
# "assess" rows are (item, recorded, result). Timestamps are 'YYYY-MM-DD HH:MM:SS'.
DELIVERIES = [
    dict(id="SYN-D01", hosp="SYN-HOSP-A", born="1998-03-14",
         admit="2026-03-02 06:10:00", deliver="2026-03-02 15:42:00", discharge="2026-03-04 11:00:00",
         cs=False, dx=[SINGLE],
         assess=[(EDD, "2025-08-20 10:00:00", "2026-03-06"),
                 (GRAV, "2026-03-02 06:30:00", 1), (PAR, "2026-03-02 06:30:00", 0)]),
    dict(id="SYN-D02", hosp="SYN-HOSP-A", born="2001-07-22",
         admit="2026-04-10 05:30:00", deliver="2026-04-10 09:15:00", discharge="2026-04-13 10:00:00",
         cs=True, dx=[SINGLE],
         assess=[(EDD, "2025-09-25 09:00:00", "2026-05-01"),          # 21 days after delivery
                 (GRAV, "2026-04-10 05:50:00", 1)]),                  # parity not recorded
    dict(id="SYN-D03", hosp="SYN-HOSP-A", born="1995-11-02",
         admit="2026-05-18 22:00:00", deliver="2026-05-19 03:30:00", discharge="2026-05-21 10:00:00",
         cs=False, dx=[SINGLE],
         assess=[(EDD, "2025-11-04 11:00:00", "2026-06-10"),          # 22 days after delivery
                 (EGA, "2026-05-19 02:30:00", 37),                    # discrete field, 1 hour before delivery
                 (GRAV, "2026-05-18 22:20:00", 1), (PAR, "2026-05-18 22:20:00", 0)]),
    dict(id="SYN-D04", hosp="SYN-HOSP-A", born="2003-01-30",
         admit="2026-06-07 13:00:00", deliver="2026-06-07 20:10:00", discharge="2026-06-09 11:00:00",
         cs=False, dx=[SINGLE],
         assess=[(EGA, "2026-06-07 18:10:00", 38),                    # no due date; 2 hours before delivery
                 (GRAV, "2026-06-07 13:20:00", 1), (PAR, "2026-06-07 13:20:00", 0)]),
    dict(id="SYN-D05", hosp="SYN-HOSP-B", born="1992-09-09",
         admit="2026-02-11 07:00:00", deliver="2026-02-11 12:40:00", discharge="2026-02-14 10:00:00",
         cs=True, dx=[SINGLE, TERM_DX],                               # no due date, no discrete field
         assess=[(GRAV, "2026-02-11 07:20:00", 1), (PAR, "2026-02-11 07:20:00", 0)]),
    dict(id="SYN-D06", hosp="SYN-HOSP-A", born="1990-05-17",
         admit="2026-07-21 06:00:00", deliver="2026-07-21 08:30:00", discharge="2026-07-24 10:00:00",
         cs=True, dx=[],                                              # multiple birth: no singleton diagnosis
         assess=[(EDD, "2026-01-08 10:00:00", "2026-08-09"),          # 19 days after delivery, 37w2d
                 (GRAV, "2026-07-21 06:20:00", 1), (PAR, "2026-07-21 06:20:00", 0)]),
    dict(id="SYN-D07", hosp="SYN-HOSP-B", born="1994-12-01",
         admit="2026-08-03 02:00:00", deliver="2026-08-03 11:25:00", discharge="2026-08-05 11:00:00",
         cs=False, dx=[SINGLE],
         assess=[(EDD, "2026-01-15 10:00:00", "2026-08-09"),          # 6 days after delivery, 39w1d
                 (GRAV, "2026-08-03 02:20:00", 2), (PAR, "2026-08-03 02:20:00", 0)]),
    dict(id="SYN-D08", hosp="SYN-HOSP-B", born="1989-04-25",
         admit="2026-09-14 07:00:00", deliver="2026-09-14 09:10:00", discharge="2026-09-17 10:00:00",
         cs=True, dx=[SINGLE],
         assess=[(EDD, "2026-02-26 10:00:00", "2026-09-21"),          # 7 days after delivery, 39w0d
                 (GRAV, "2026-09-14 07:20:00", 2), (PAR, "2026-09-14 07:20:00", 1),
                 (PRETERM, "2026-09-14 07:20:00", 0), (TERMB, "2026-09-14 07:20:00", 1)]),
    dict(id="SYN-D09", hosp="SYN-HOSP-B", born="1999-08-08",
         admit="2026-10-05 21:00:00", deliver="2026-10-06 04:45:00", discharge="2026-10-09 10:00:00",
         cs=True, dx=[SINGLE],
         assess=[(EDD, "2026-03-19 10:00:00", "2026-10-06"),          # delivery on the due date, 40w0d
                 (PRETERM, "2026-10-05 21:20:00", 0), (TERMB, "2026-10-05 21:20:00", 0),
                 (TERMB, "2026-10-06 06:45:00", 1)]),                 # updated 2 hours after delivery
    dict(id="SYN-D10", hosp="SYN-HOSP-A", born="1997-02-19",
         admit="2026-11-02 06:00:00", deliver="2026-11-02 08:05:00", discharge="2026-11-05 10:00:00",
         cs=True, dx=[SINGLE],
         assess=[(EDD, "2026-04-16 10:00:00", "2026-11-09"),          # 7 days after delivery, 39w0d
                 (ABN, "2026-11-02 06:20:00", None),                  # assessed during the stay
                 (GRAV, "2026-11-02 06:15:00", 1), (PAR, "2026-11-02 06:15:00", 0)]),
    dict(id="SYN-D11", hosp="SYN-HOSP-B", born="2000-10-10",
         admit="2026-11-16 07:00:00", deliver="2026-11-16 09:30:00", discharge="2026-11-19 10:00:00",
         cs=True, dx=[SINGLE, ABN],                                   # encounter diagnosis, no assessment
         assess=[(EDD, "2026-04-30 10:00:00", "2026-11-22"),          # 6 days after delivery, 39w1d
                 (GRAV, "2026-11-16 07:20:00", 1), (PAR, "2026-11-16 07:20:00", 0)]),
    dict(id="SYN-D12", hosp="SYN-HOSP-B", born="1996-06-06",
         admit="2026-03-30 04:00:00", deliver="2026-03-30 13:15:00", discharge="2026-04-01 11:00:00",
         cs=False, dx=[SINGLE],
         assess=[(EDD, "2025-09-10 10:00:00", "2026-04-05"),          # 6 days after delivery, 39w1d
                 (ABN, "2026-03-10 14:00:00", None),                  # prenatal visit, 20 days before admission
                 (GRAV, "2026-03-30 04:20:00", 1), (PAR, "2026-03-30 04:20:00", 0)]),
    dict(id="SYN-D13", hosp="SYN-HOSP-A", born="1988-12-12",
         admit="2026-01-20 07:00:00", deliver="2026-01-20 08:40:00", discharge="2026-01-23 10:00:00",
         cs=True, dx=[SINGLE, PREVIA],
         assess=[(EDD, "2025-07-10 10:00:00", "2026-02-08"),          # 19 days after delivery, 37w2d
                 (GRAV, "2026-01-20 07:20:00", 1), (PAR, "2026-01-20 07:20:00", 0)]),
    dict(id="SYN-D14", hosp="SYN-HOSP-B", born="2002-03-03",
         admit="2026-06-22 07:00:00", deliver="2026-06-22 09:05:00", discharge="2026-06-25 10:00:00",
         cs=True, dx=[SINGLE, HSV],
         assess=[(EDD, "2025-12-04 10:00:00", "2026-06-28"),          # 6 days after delivery, 39w1d
                 (GRAV, "2026-06-22 07:20:00", 1), (PAR, "2026-06-22 07:20:00", 0)]),
    dict(id="SYN-D15", hosp="SYN-HOSP-A", born="1993-07-07",
         admit="2026-12-30 20:00:00", deliver="2026-12-31 05:30:00", discharge="2027-01-02 10:00:00",
         cs=False, dx=[SINGLE],
         assess=[(EDD, "2026-06-11 10:00:00", "2027-01-04"),          # 4 days after delivery, 39w3d
                 (GRAV, "2026-12-30 20:20:00", 1), (PAR, "2026-12-30 20:20:00", 0)]),
]


def load(con):
    con.executescript(SCHEMA)
    for d in DELIVERIES:
        pid = d["id"].replace("SYN-D", "SYN-PT")
        con.execute("INSERT INTO encounter VALUES (?,?,?,?,?,?,?)",
                    (d["id"], pid, d["hosp"], d["born"], INPT, d["admit"], d["discharge"]))
        for vs in d["dx"]:
            con.execute("INSERT INTO encounter_diagnosis VALUES (?,?)", (d["id"], vs))
        con.execute("INSERT INTO procedure VALUES (?,?,?)", (pid, DELIV, d["deliver"]))
        if d["cs"]:
            con.execute("INSERT INTO procedure VALUES (?,?,?)", (pid, CSEC, d["deliver"]))
        # time of delivery, charted 5 minutes after the birth
        con.execute("INSERT INTO assessment VALUES (?,?,datetime(?, '+5 minutes'),?)",
                    (pid, TOD, d["deliver"], d["deliver"]))
        for item, recorded, result in d["assess"]:
            con.execute("INSERT INTO assessment VALUES (?,?,?,?)", (pid, item, recorded, result))


# =============================================================================
# 3. THE MEASURE LOGIC, one SQL statement
# =============================================================================
MEASURE_SQL = """
CREATE TABLE result AS
WITH
-- Def Global."Inpatient Encounter": an "Encounter Inpatient" encounter whose
-- relevantPeriod "ends during day of" the Measurement Period.
inpatient AS (
    SELECT e.*
    FROM encounter e
    WHERE e.value_set = 'Encounter Inpatient'
      AND date(e.discharge_dt) BETWEEN :mp_start AND :mp_end
),
-- Def PCMaternal."Encounter With Age Range": AgeInYearsAt(date from start of
-- the encounter) >= 8 and < 65.
-- Def PCMaternal."Delivery Encounter With Age Range" = PC Initial Population:
-- a "Delivery Procedures" procedure starts during the hospitalization.
ip AS (
    SELECT i.*
    FROM inpatient i
    WHERE ( CAST(strftime('%Y', i.admit_dt) AS INTEGER) - CAST(strftime('%Y', i.birth_date) AS INTEGER)
            - (strftime('%m-%d', i.admit_dt) < strftime('%m-%d', i.birth_date)) ) >= 8
      AND ( CAST(strftime('%Y', i.admit_dt) AS INTEGER) - CAST(strftime('%Y', i.birth_date) AS INTEGER)
            - (strftime('%m-%d', i.admit_dt) < strftime('%m-%d', i.birth_date)) ) < 65
      AND EXISTS (SELECT 1 FROM procedure p
                  WHERE p.patient_id = i.patient_id AND p.value_set = 'Delivery Procedures'
                    AND p.start_dt BETWEEN i.admit_dt AND i.discharge_dt)
),
-- Fn PCMaternal.LastTimeOfDelivery: last "Date and time of obstetric delivery"
-- assessment charted during the hospitalization whose result is also during it.
tod AS (
    SELECT ip.encounter_id,
           (SELECT a.result FROM assessment a
            WHERE a.patient_id = ip.patient_id
              AND a.item = 'Date and time of obstetric delivery'
              AND a.recorded_dt BETWEEN ip.admit_dt AND ip.discharge_dt
              AND a.result      BETWEEN ip.admit_dt AND ip.discharge_dt
            ORDER BY a.recorded_dt DESC LIMIT 1) AS delivery_dt
    FROM ip
),
src AS (
    SELECT ip.*, t.delivery_dt,
        -- Fn PCMaternal.LastEstimatedDeliveryDate: last non-null result charted
        -- "42 weeks or less before or on" the time of delivery.
        (SELECT a.result FROM assessment a
         WHERE a.patient_id = ip.patient_id AND a.item = 'Delivery date Estimated'
           AND a.result IS NOT NULL
           AND a.recorded_dt >= datetime(t.delivery_dt, '-294 days')
           AND a.recorded_dt <= t.delivery_dt
         ORDER BY a.recorded_dt DESC LIMIT 1) AS edd,
        -- Fn PCMaternal.LastEstimatedGestationalAge: last non-null result charted
        -- "24 hours or less before or on" the time of delivery, or on the same
        -- day as delivery and during the hospitalization. Result in weeks.
        (SELECT a.result FROM assessment a
         WHERE a.patient_id = ip.patient_id AND a.item = 'Estimated Gestational Age at Delivery'
           AND a.result IS NOT NULL
           AND (   (a.recorded_dt >= datetime(t.delivery_dt, '-24 hours') AND a.recorded_dt <= t.delivery_dt)
                OR (date(a.recorded_dt) = date(t.delivery_dt)
                    AND a.recorded_dt BETWEEN ip.admit_dt AND ip.discharge_dt) )
         ORDER BY a.recorded_dt DESC LIMIT 1) AS ega_weeks,
        -- Fn LastGravida, LastParity, LastHistoryPretermBirth, LastHistoryTermBirth:
        -- last non-null result charted "42 weeks or less before" the time of
        -- delivery (before, not on or after).
        (SELECT a.result FROM assessment a
         WHERE a.patient_id = ip.patient_id AND a.item = '[#] Pregnancies' AND a.result IS NOT NULL
           AND a.recorded_dt >= datetime(t.delivery_dt, '-294 days') AND a.recorded_dt < t.delivery_dt
         ORDER BY a.recorded_dt DESC LIMIT 1) AS gravida,
        (SELECT a.result FROM assessment a
         WHERE a.patient_id = ip.patient_id AND a.item = '[#] Parity' AND a.result IS NOT NULL
           AND a.recorded_dt >= datetime(t.delivery_dt, '-294 days') AND a.recorded_dt < t.delivery_dt
         ORDER BY a.recorded_dt DESC LIMIT 1) AS parity,
        (SELECT a.result FROM assessment a
         WHERE a.patient_id = ip.patient_id AND a.item = '[#] Births.preterm' AND a.result IS NOT NULL
           AND a.recorded_dt >= datetime(t.delivery_dt, '-294 days') AND a.recorded_dt < t.delivery_dt
         ORDER BY a.recorded_dt DESC LIMIT 1) AS preterm_births,
        (SELECT a.result FROM assessment a
         WHERE a.patient_id = ip.patient_id AND a.item = '[#] Births.term' AND a.result IS NOT NULL
           AND a.recorded_dt >= datetime(t.delivery_dt, '-294 days') AND a.recorded_dt < t.delivery_dt
         ORDER BY a.recorded_dt DESC LIMIT 1) AS term_births,
        -- Def "Encounter With Abnormal Presentation": the last "Abnormal
        -- Presentation" assessment "before or on" the time of delivery.
        (SELECT a.recorded_dt FROM assessment a
         WHERE a.patient_id = ip.patient_id AND a.item = 'Abnormal Presentation'
           AND a.recorded_dt <= t.delivery_dt
         ORDER BY a.recorded_dt DESC LIMIT 1) AS last_abn_pres_dt,
        EXISTS (SELECT 1 FROM encounter_diagnosis d WHERE d.encounter_id = ip.encounter_id
                AND d.value_set = '37 to 42 Plus Weeks Gestation')                   AS term_dx,
        EXISTS (SELECT 1 FROM encounter_diagnosis d WHERE d.encounter_id = ip.encounter_id
                AND d.value_set = 'Delivery of Singleton')                           AS singleton_dx,
        EXISTS (SELECT 1 FROM encounter_diagnosis d WHERE d.encounter_id = ip.encounter_id
                AND d.value_set = 'Abnormal Presentation')                           AS abn_pres_dx,
        EXISTS (SELECT 1 FROM encounter_diagnosis d WHERE d.encounter_id = ip.encounter_id
                AND d.value_set = 'Placenta Accreta Spectrum Previa or Vasa Previa') AS previa_dx,
        EXISTS (SELECT 1 FROM encounter_diagnosis d WHERE d.encounter_id = ip.encounter_id
                AND d.value_set = 'Genital Herpes')                                  AS herpes_dx,
        -- Def "Delivery Encounter With Cesarean Birth": a "Cesarean Birth"
        -- procedure during the hospitalization.
        EXISTS (SELECT 1 FROM procedure p WHERE p.patient_id = ip.patient_id
                AND p.value_set = 'Cesarean Birth'
                AND p.start_dt BETWEEN ip.admit_dt AND ip.discharge_dt)              AS cesarean
    FROM ip JOIN tod t ON t.encounter_id = ip.encounter_id
),
-- Fn PCMaternal.CalculatedGestationalAge:
--   (280 - (difference in days between time of delivery and estimated delivery
--   date)) div 7.  "difference in days" counts calendar-day boundaries, so only
--   the two dates matter. SQLite "/" on integers truncates, as CQL "div" does.
f AS (
    SELECT s.*,
        (280 - CAST(ROUND(julianday(date(s.edd)) - julianday(date(s.delivery_dt))) AS INTEGER)) / 7 AS cga_weeks
    FROM src s
),
den AS (
    -- PC Denominator = Def "Singleton Delivery Encounters At 37 Plus Weeks
    -- Gravida 1 Parity 0, No Previous Births"
    SELECT f.*,
        CASE WHEN
            -- Def "Delivery Encounter With Gestational Age Greater Than Or Equal
            -- To 37 Weeks": union of calculated, estimated, and coding routes.
            (   f.cga_weeks >= 37
             OR (f.cga_weeks IS NULL AND f.ega_weeks >= 37)
             OR (f.cga_weeks IS NULL AND f.ega_weeks IS NULL AND f.term_dx = 1) )
            -- Def "Encounter With Singleton Delivery"
            AND f.singleton_dx = 1
            -- nulliparous: gravida 1, or parity 0, or preterm 0 and term 0
            AND (   f.gravida = 1
                 OR f.parity = 0
                 OR (f.preterm_births = 0 AND f.term_births = 0) )
        THEN 1 ELSE 0 END AS in_den
    FROM f
),
pops AS (
    SELECT d.*,
        -- PC Denominator Exclusions = Def "Encounter With Abnormal Presentation"
        -- union Def "Encounter With Genital Herpes, Placenta Previa, Vasa Previa
        -- Or Placenta Accreta Spectrum". Both are drawn from the denominator.
        CASE WHEN d.in_den = 1 AND (
                 d.last_abn_pres_dt BETWEEN d.admit_dt AND d.discharge_dt
              OR d.abn_pres_dx = 1
              OR d.previa_dx = 1
              OR d.herpes_dx = 1 )
        THEN 1 ELSE 0 END AS in_excl,
        -- PC Numerator = Def "Delivery Encounter With Cesarean Birth", drawn
        -- from the denominator.
        CASE WHEN d.in_den = 1 AND d.cesarean = 1 THEN 1 ELSE 0 END AS num_def
    FROM den d
)
SELECT e.encounter_id, e.hospital_id,
       CASE WHEN p.encounter_id IS NOT NULL THEN 1 ELSE 0 END  AS ip,
       COALESCE(p.in_den, 0)                                   AS den,
       COALESCE(p.in_excl, 0)                                  AS excl,
       -- Proportion scoring: denominator exclusions are removed before the
       -- numerator is counted.
       CASE WHEN p.num_def = 1 AND p.in_excl = 0 THEN 1 ELSE 0 END AS num,
       p.cga_weeks, p.ega_weeks, p.term_dx, p.gravida, p.parity,
       p.preterm_births, p.term_births, p.cesarean
FROM encounter e LEFT JOIN pops p ON p.encounter_id = e.encounter_id
ORDER BY e.encounter_id;
"""

ROLLUP_SQL = """
SELECT hospital_id,
       SUM(ip)          AS ip,
       SUM(den)         AS den,
       SUM(excl)        AS excl,
       SUM(den) - SUM(excl) AS den_after_excl,
       SUM(num)         AS num
FROM result GROUP BY hospital_id ORDER BY hospital_id;
"""


def run(sql=MEASURE_SQL):
    con = sqlite3.connect(":memory:")
    load(con)
    con.execute(sql, {"mp_start": MP_START, "mp_end": MP_END})
    rows = con.execute("SELECT * FROM result ORDER BY encounter_id").fetchall()
    cols = [c[1] for c in con.execute("PRAGMA table_info(result)")]
    per_case = {r[0]: dict(zip(cols, r)) for r in rows}
    rollup = {r[0]: tuple(r[1:]) for r in con.execute(ROLLUP_SQL)}
    con.close()
    return per_case, rollup


# =============================================================================
# 4. RULE-CHANGE CHECKS. Each entry edits one rule in the SQL and names the
#    synthetic case(s) that must then stop matching EXPECTED. This shows each
#    rule is held in place by at least one case. (old text, new text, count)
# =============================================================================
RULE_CHANGES = [
    ("Measurement period not applied",
     "AND date(e.discharge_dt) BETWEEN :mp_start AND :mp_end", "AND :mp_start <= :mp_end", 1, {"SYN-D15"}),
    ("Term threshold lowered to 36 weeks (calculated route)",
     "f.cga_weeks >= 37", "f.cga_weeks >= 36", 1, {"SYN-D03"}),
    ("Discrete gestational age read even when a calculated value exists",
     "(f.cga_weeks IS NULL AND f.ega_weeks >= 37)", "(f.ega_weeks >= 37)", 1, {"SYN-D03"}),
    ("Discrete gestational age route removed",
     "(f.cga_weeks IS NULL AND f.ega_weeks >= 37)", "(0)", 1, {"SYN-D04"}),
    ("Diagnosis coding route removed",
     "(f.cga_weeks IS NULL AND f.ega_weeks IS NULL AND f.term_dx = 1)", "(0)", 1, {"SYN-D05"}),
    ("Singleton requirement removed",
     "AND f.singleton_dx = 1", "", 1, {"SYN-D06"}),
    ("Gravida = 1 route removed",
     "f.gravida = 1", "0", 1, {"SYN-D02"}),
    ("Parity = 0 route removed",
     "OR f.parity = 0", "", 1, {"SYN-D07"}),
    ("Preterm 0 and term 0 route removed",
     "OR (f.preterm_births = 0 AND f.term_births = 0)", "", 1, {"SYN-D09"}),
    ("Counts charted after delivery are read",
     "AND a.recorded_dt < t.delivery_dt", "AND a.recorded_dt <= ip.discharge_dt", 4, {"SYN-D09"}),
    ("Abnormal presentation assessment route removed",
     "d.last_abn_pres_dt BETWEEN d.admit_dt AND d.discharge_dt", "0", 1, {"SYN-D10"}),
    ("Abnormal presentation assessment counted whenever charted",
     "d.last_abn_pres_dt BETWEEN d.admit_dt AND d.discharge_dt", "d.last_abn_pres_dt IS NOT NULL", 1, {"SYN-D12"}),
    ("Abnormal presentation diagnosis route removed",
     "OR d.abn_pres_dx = 1", "", 1, {"SYN-D11"}),
    ("Placenta previa, accreta spectrum, vasa previa exclusion removed",
     "OR d.previa_dx = 1", "", 1, {"SYN-D13"}),
    ("Genital herpes exclusion removed",
     "OR d.herpes_dx = 1", "", 1, {"SYN-D14"}),
    ("Excluded cesareans counted in the numerator",
     "WHEN p.num_def = 1 AND p.in_excl = 0 THEN 1", "WHEN p.num_def = 1 THEN 1", 1,
     {"SYN-D10", "SYN-D11", "SYN-D13", "SYN-D14"}),
]


def pops(row):
    return (row["ip"], row["den"], row["excl"], row["num"])


def main():
    failures = 0

    print("CMS334v7 Cesarean Birth (PC-02), eCQM version 7.1.000, 2026 reporting period")
    print("Specification test on SYNTHETIC deliveries. No real patient or hospital data.\n")

    per_case, rollup = run()

    print("TEST CASES: expected (worked by hand first) against the SQL result")
    print(f"{'id':8} {'hospital':11} {'expected':>12} {'result':>12}  {'':4}  GA calc/disc/dx  G  P  pre term  CS")
    print(f"{'':8} {'':11} {'IP DEN EX NUM':>12} {'IP DEN EX NUM':>12}")
    for cid, (exp, why) in EXPECTED.items():
        r = per_case[cid]
        got = pops(r)
        ok = got == exp
        failures += not ok
        show = lambda v: "-" if v is None else str(v)
        print(f"{cid:8} {r['hospital_id']:11} {'  '.join(map(str, exp)):>12} {'  '.join(map(str, got)):>12}  "
              f"{'PASS' if ok else 'FAIL'}  {show(r['cga_weeks']):>4}/{show(r['ega_weeks']):>3}/{show(r['term_dx']):>2}  "
              f"{show(r['gravida']):>2} {show(r['parity']):>2} {show(r['preterm_births']):>4} {show(r['term_births']):>4}  "
              f"{show(r['cesarean']):>2}")
    n = len(EXPECTED)
    print(f"\n{n - failures} of {n} cases match the expected result.\n")
    assert set(per_case) == set(EXPECTED), "case list and expected list differ"

    print("WHY EACH CASE IS EXPECTED AS IT IS")
    for cid, (exp, why) in EXPECTED.items():
        print(f"  {cid}: {why}")

    print("\nHOSPITAL ROLL-UP (synthetic hospitals; counts of delivery encounters)")
    print(f"{'hospital':11} {'IP':>3} {'DEN':>4} {'EXCL':>5} {'DEN after EXCL':>15} {'NUM':>4}  rate (arithmetic check only)")
    tot = [0, 0, 0, 0, 0]
    for hosp, exp in EXPECTED_ROLLUP.items():
        got = rollup[hosp]
        ok = got == exp
        failures += not ok
        tot = [a + b for a, b in zip(tot, got)]
        rate = f"{got[4]} of {got[3]} = {100 * got[4] / got[3]:.1f}%" if got[3] else "no denominator"
        print(f"{hosp:11} {got[0]:>3} {got[1]:>4} {got[2]:>5} {got[3]:>15} {got[4]:>4}  {rate}  {'PASS' if ok else 'FAIL'}")
    print(f"{'Both':11} {tot[0]:>3} {tot[1]:>4} {tot[2]:>5} {tot[3]:>15} {tot[4]:>4}  "
          f"{tot[4]} of {tot[3]} = {100 * tot[4] / tot[3]:.1f}%")
    assert set(rollup) == set(EXPECTED_ROLLUP), "hospital list and expected list differ"

    print("\nRULE-CHANGE CHECKS: edit one rule, confirm the named case(s) stop matching")
    caught = 0
    for label, old, new, count, must_change in RULE_CHANGES:
        assert MEASURE_SQL.count(old) == count, f"rule text not found {count} time(s): {old}"
        changed_cases, _ = run(MEASURE_SQL.replace(old, new))
        changed = {cid for cid, (exp, _) in EXPECTED.items() if pops(changed_cases[cid]) != exp}
        ok = changed == must_change
        caught += ok
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: changes {', '.join(sorted(changed)) or 'nothing'}")
    print(f"\n{caught} of {len(RULE_CHANGES)} rule changes are caught by exactly the case(s) named in advance.")

    print("\nRules implemented with no synthetic case on the failing side:")
    print("  age 8 to 64 at admission; presence of a delivery procedure; the 24-hour edge of the")
    print("  discrete gestational age window; the 42-week lookback edge.")

    print("\nALL CHECKS PASS" if failures == 0 else f"\n{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
