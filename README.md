# Cesarean Birth (CMS334v7, PC-02): eCQM spec implementation and test cases

This repo implements the CMS eCQM Cesarean Birth measure (CMS334v7, eCQM version 7.1.000, 2026 reporting period; steward: The Joint Commission; CBE 0471e) from its published specification, and tests it on synthetic deliveries.

**Every patient, hospital, date and record here is synthetic.** No CMS, hospital or patient data is used, and no value set codes are reproduced. Each synthetic record carries the name of the value set it stands for.

## Source followed
- CMS334v7, eCQM version 7.1.000, on the eCQI Resource Center: https://ecqi.healthit.gov/ecqm/hosp-inpt/2026/cms0334v7

## What the code does
- Implements the initial population, the 37-week gestational age logic (calculated, then discrete field, then diagnosis), singleton and nulliparity rules, the denominator exclusions (abnormal presentation, placenta previa / vasa previa / accreta spectrum, genital herpes) and the numerator, as one SQL statement run in SQLite.
- Runs 15 synthetic deliveries at 2 synthetic hospitals. Expected results were written out from the specification first, then compared with the SQL output.
- Runs 16 single-rule edits to the SQL and confirms each one is caught by exactly the cases named in advance.

## Not covered
The extension of the stay back through an ED or OB triage visit and an observation stay; value set contents; supplemental data elements and QRDA reporting; elements recorded as a period; cases on the failing side of the age bounds, the delivery procedure requirement, and the edges of the 24-hour and 42-week windows. This is the CMS eCQM only, not the chart-abstracted PC-02.

## Run
```
python3 cms334_cesarean_birth_spec_test.py
```
Python 3.8+, standard library only. Ends with "ALL CHECKS PASS".

Gaurav Bhatti, pharmacist by training, MHI (University of Michigan). bgaurav@umich.edu
