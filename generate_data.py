#!/usr/bin/env python3
"""
CSC 307 Group Project - Group 1, Topic 01 (Education)
A Basic and Senior High School Performance Data Warehouse - Upper West Region, Ghana

Generates a fully SYNTHETIC star-schema (constellation) dataset:
  8 dimension tables + 3 fact tables (main fact: fact_exam_result)
plus schema.sql, data_dictionary.csv, metadata.json, quality_report.csv
and star_schema.dot / star_schema.png (if Graphviz `dot` is installed).

Re-run:   python generate_data.py            (writes into ./output)
          python generate_data.py --out DIR
The random seed is fixed (SEED below), so every CSV is identical on every run.
Only the generated_at timestamp in metadata.json changes.

No real person, school, candidate or teacher is represented. School names,
EMIS codes, index numbers, staff IDs and learner IDs are generated.
"""
import argparse
import datetime as dt
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

SEED = 307_01_2026
SCRIPT_VERSION = "1.0.0"
REGION = "Upper West"
OPEN_END = dt.date(9999, 12, 31)          # SCD2 open-ended validity
DATE_START, DATE_END = dt.date(2020, 9, 1), dt.date(2025, 12, 31)
ACADEMIC_YEARS = [2020, 2021, 2022, 2023, 2024]   # start year of each academic year
EXAM_YEARS = [y + 1 for y in ACADEMIC_YEARS]      # 2021..2025

rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# 1. Reference data (field-work inputs; replace with what the group collects)
# ---------------------------------------------------------------------------
# (code, district, capital, lat, lon, other towns, home-language weights,
#  district score effect, girls' STEM gap in 2021 (score points), remoteness 0-1)
# Coordinates are approximate town centroids - verify with GhanaPostGPS/field GPS.
LANGS = ["Dagaare", "Sissali", "Waale", "Other"]
DISTRICTS = [
    ("UW01", "Wa Municipal", "Wa", 10.060, -2.501, ["Busa", "Charia", "Kperisi", "Jonga"],
     [0.30, 0.00, 0.60, 0.10], 5.0, 2.0, 0.0),
    ("UW02", "Wa East", "Funsi", 10.310, -1.960, ["Bulenga", "Loggu", "Kundungu"],
     [0.10, 0.10, 0.30, 0.50], -5.0, 6.0, 1.0),
    ("UW03", "Wa West", "Wechiau", 9.830, -2.680, ["Dorimon", "Ga", "Vieri"],
     [0.60, 0.00, 0.15, 0.25], -3.0, 5.0, 0.8),
    ("UW04", "Nadowli-Kaleo", "Nadowli", 10.370, -2.670, ["Kaleo", "Sankana", "Takpo"],
     [0.90, 0.00, 0.05, 0.05], 1.0, 3.5, 0.4),
    ("UW05", "Daffiama-Bussie-Issa", "Issa", 10.300, -2.420, ["Daffiama", "Bussie", "Fian"],
     [0.85, 0.05, 0.00, 0.10], -1.0, 4.5, 0.6),
    ("UW06", "Jirapa", "Jirapa", 10.530, -2.700, ["Ullo", "Tizza", "Han"],
     [0.95, 0.00, 0.00, 0.05], 2.0, 3.0, 0.3),
    ("UW07", "Lambussie", "Lambussie", 10.860, -2.620, ["Hamile", "Karni", "Piina"],
     [0.55, 0.40, 0.00, 0.05], -1.0, 4.5, 0.6),
    ("UW08", "Lawra", "Lawra", 10.640, -2.900, ["Babile", "Eremon", "Zambo"],
     [0.90, 0.00, 0.00, 0.10], 2.0, 3.0, 0.4),
    ("UW09", "Nandom", "Nandom", 10.850, -2.760, ["Ko", "Puffien", "Kokoligu"],
     [0.95, 0.00, 0.00, 0.05], 3.0, 2.5, 0.4),
    ("UW10", "Sissala East", "Tumu", 10.880, -1.980, ["Wellembelle", "Bujan", "Nabulo"],
     [0.05, 0.85, 0.00, 0.10], -1.0, 4.5, 0.6),
    ("UW11", "Sissala West", "Gwollu", 10.970, -2.220, ["Zini", "Jeffisi", "Dasima"],
     [0.10, 0.85, 0.00, 0.05], -4.0, 6.0, 0.9),
]

# Ghana public holidays used in dim_date (moveable dates approximate; verify).
FIXED_HOLIDAYS = {(1, 1): "New Year's Day", (1, 7): "Constitution Day",
                  (3, 6): "Independence Day", (5, 1): "May Day",
                  (8, 4): "Founders' Day", (9, 21): "Kwame Nkrumah Memorial Day",
                  (12, 25): "Christmas Day", (12, 26): "Boxing Day"}
EASTER = {2021: (4, 4), 2022: (4, 17), 2023: (4, 9), 2024: (3, 31), 2025: (4, 20)}
EID_FITR = {2021: (5, 13), 2022: (5, 2), 2023: (4, 21), 2024: (4, 10), 2025: (3, 31)}
EID_ADHA = {2021: (7, 20), 2022: (7, 9), 2023: (6, 28), 2024: (6, 16), 2025: (6, 6)}

BECE_SUBJECTS = [  # (code, name, core/elective, STEM, difficulty)
    ("BECE-ENG", "English Language", "Core", False, -2),
    ("BECE-MAT", "Mathematics", "Core", True, -6),
    ("BECE-SCI", "Integrated Science", "Core", True, -4),
    ("BECE-SOC", "Social Studies", "Core", False, 3),
    ("BECE-RME", "Religious and Moral Education", "Core", False, 5),
    ("BECE-CMP", "Computing", "Core", True, -3),
    ("BECE-GHL", "Ghanaian Language", "Core", False, 2),
    ("BECE-CTE", "Career Technology", "Core", False, 2),
    ("BECE-CAD", "Creative Arts and Design", "Core", False, 3),
    ("BECE-FRE", "French", "Elective", False, -5),
]
WASSCE_CORE = [
    ("WAS-ENG", "English Language", "Core", False, -3),
    ("WAS-CMT", "Core Mathematics", "Core", True, -7),
    ("WAS-ISC", "Integrated Science", "Core", True, -4),
    ("WAS-SOC", "Social Studies", "Core", False, 2),
]
WASSCE_ELECTIVES = [
    ("WAS-PHY", "Physics", True, -6), ("WAS-CHE", "Chemistry", True, -5),
    ("WAS-BIO", "Biology", True, -2), ("WAS-EMT", "Elective Mathematics", True, -8),
    ("WAS-LIT", "Literature-in-English", False, 0), ("WAS-GOV", "Government", False, 2),
    ("WAS-HIS", "History", False, 1), ("WAS-ECO", "Economics", False, -2),
    ("WAS-CRS", "Christian Religious Studies", False, 4), ("WAS-GEO", "Geography", False, -1),
    ("WAS-FAC", "Financial Accounting", False, -2), ("WAS-BMG", "Business Management", False, 1),
    ("WAS-CAC", "Cost Accounting", False, -4), ("WAS-GAG", "General Agriculture", True, 2),
    ("WAS-ANH", "Animal Husbandry", True, 2), ("WAS-FNU", "Food and Nutrition", False, 2),
    ("WAS-MIL", "Management in Living", False, 3), ("WAS-GKA", "General Knowledge in Art", False, 2),
]
PROGRAMMES = {
    "General Science": ["WAS-PHY", "WAS-CHE", "WAS-BIO", "WAS-EMT"],
    "General Arts": ["WAS-LIT", "WAS-GOV", "WAS-HIS", "WAS-ECO", "WAS-CRS", "WAS-GEO"],  # pick 4
    "Business": ["WAS-FAC", "WAS-BMG", "WAS-CAC", "WAS-ECO"],
    "Agricultural Science": ["WAS-GAG", "WAS-ANH", "WAS-CHE", "WAS-BIO"],
    "Home Economics": ["WAS-FNU", "WAS-MIL", "WAS-GKA", "WAS-BIO"],
}
PROGRAMME_WEIGHTS = {"General Arts": 0.36, "Agricultural Science": 0.20, "Business": 0.15,
                     "Home Economics": 0.15, "General Science": 0.14}
CLASSES = {"Primary": ["KG1", "KG2", "P1", "P2", "P3", "P4", "P5", "P6"],
           "JHS": ["JHS1", "JHS2", "JHS3"], "SHS": ["SHS1", "SHS2", "SHS3"]}
PTR_NORM = {"Primary": 35, "JHS": 25, "SHS": 25}

SRC_EMIS = "GES EMIS Annual School Census"
SRC_WAEC = "WAEC BECE/WASSCE results files"
SRC_HR = "GES HRMIS / CAGD payroll"
SRC_REG = "School registers and termly returns to District Education Office"
SRC_CAL = "Generated calendar (GES calendar, Ghana public holidays)"
SRC_LOC = "Ghana Statistical Service district list; GhanaPostGPS"
SRC_CSSPS = "CSSPS / Free SHS placement records"
SRC_DW = "Data warehouse (surrogate key / ETL)"

# ---------------------------------------------------------------------------
# 2. Table specification - single source for DDL, data dictionary and checks
# ---------------------------------------------------------------------------
def col(name, sqltype, desc, key="", ref=None, nullable=False, allowed=None, rng_=None,
        unit="", source="", rule="", scd="n/a"):
    return dict(name=name, sqltype=sqltype, desc=desc, key=key, ref=ref, nullable=nullable,
                allowed=allowed, range=rng_, unit=unit, source=source, rule=rule, scd=scd)

YN = ["Yes", "No"]
DIST_NAMES = [d[1] for d in DISTRICTS]
BECE_GRADES = [str(i) for i in range(1, 10)]
WASSCE_GRADES = ["A1", "B2", "B3", "C4", "C5", "C6", "D7", "E8", "F9"]

SPEC = {}
SPEC["dim_date"] = dict(kind="dimension", scd="Type 0 (static)", grain="One row per calendar day, 2020-09-01 to 2025-12-31.", cols=[
    col("date_key", "INTEGER", "Surrogate key in YYYYMMDD form", "PK", source=SRC_CAL, rng_=(20200901, 20251231)),
    col("full_date", "DATE", "Calendar date", source=SRC_CAL, scd="Type 0"),
    col("day_name", "VARCHAR(9)", "Name of the weekday", allowed=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], source=SRC_CAL, scd="Type 0"),
    col("day_of_week", "SMALLINT", "ISO day number (1 = Monday)", rng_=(1, 7), source=SRC_CAL, scd="Type 0"),
    col("day_of_month", "SMALLINT", "Day of the month", rng_=(1, 31), source=SRC_CAL, scd="Type 0"),
    col("month_number", "SMALLINT", "Month number", rng_=(1, 12), source=SRC_CAL, scd="Type 0"),
    col("month_name", "VARCHAR(9)", "Month name", source=SRC_CAL, scd="Type 0"),
    col("quarter", "SMALLINT", "Calendar quarter", rng_=(1, 4), source=SRC_CAL, scd="Type 0"),
    col("year", "SMALLINT", "Calendar year", rng_=(2020, 2025), source=SRC_CAL, scd="Type 0"),
    col("is_weekend", "BOOLEAN", "True on Saturday or Sunday", source=SRC_CAL, scd="Type 0"),
    col("is_public_holiday", "BOOLEAN", "True on a Ghana statutory public holiday", source=SRC_CAL, rule="Moveable Christian and Muslim holidays are approximate", scd="Type 0"),
    col("holiday_name", "VARCHAR(40)", "Name of the public holiday", nullable=True, source=SRC_CAL, rule="NULL when is_public_holiday is false", scd="Type 0"),
    col("season", "VARCHAR(5)", "Upper West season: rainy May-October, dry November-April", allowed=["Rainy", "Dry"], source=SRC_CAL, rule="Single (unimodal) rainy season in the north", scd="Type 0"),
])
SPEC["dim_location"] = dict(kind="dimension", scd="Type 1", grain="One row per town or community in the region's 11 districts (conformed dimension).", cols=[
    col("location_key", "INTEGER", "Surrogate key", "PK", source=SRC_DW),
    col("region", "VARCHAR(20)", "Administrative region", allowed=[REGION], source=SRC_LOC, scd="Type 1"),
    col("district_code", "VARCHAR(4)", "Warehouse district code UW01-UW11 (conformed across all CSC 307 topics)", allowed=[d[0] for d in DISTRICTS], source=SRC_LOC, scd="Type 1"),
    col("district", "VARCHAR(30)", "Municipal or district assembly area", allowed=DIST_NAMES, source=SRC_LOC, scd="Type 1"),
    col("district_capital", "VARCHAR(20)", "Capital town of the district", allowed=[d[2] for d in DISTRICTS], source=SRC_LOC, scd="Type 1"),
    col("town", "VARCHAR(30)", "Town or community where the school is located", source=SRC_LOC, scd="Type 1"),
    col("urban_rural", "VARCHAR(5)", "Settlement type", allowed=["Urban", "Rural"], source=SRC_LOC, rule="District capitals are Urban, all other towns Rural (to confirm in field)", scd="Type 1"),
    col("electoral_area", "VARCHAR(40)", "Electoral area (placeholder name built from the town)", source=SRC_LOC, rule="Placeholder until the real electoral-area list is collected", scd="Type 1"),
    col("latitude", "DECIMAL(8,5)", "Approximate latitude of the town", rng_=(9.5, 11.2), unit="decimal degrees", source=SRC_LOC, scd="Type 1"),
    col("longitude", "DECIMAL(8,5)", "Approximate longitude of the town", rng_=(-3.0, -1.5), unit="decimal degrees", source=SRC_LOC, scd="Type 1"),
])
SPEC["dim_school"] = dict(kind="dimension", scd="Type 2", grain="One row per school per version of its facilities; a new row is added when a tracked attribute changes.", cols=[
    col("school_key", "INTEGER", "Surrogate key (one per version)", "PK", source=SRC_DW),
    col("emis_code", "VARCHAR(12)", "Synthetic EMIS-style school code (natural key)", source=SRC_EMIS, rule="Format UWnn-L-sss; stable across versions"),
    col("school_name", "VARCHAR(40)", "Generated school name (does not refer to a real school)", source=SRC_EMIS, scd="Type 1"),
    col("school_level", "VARCHAR(7)", "Level of education offered", allowed=["Primary", "JHS", "SHS"], source=SRC_EMIS, rule="Primary schools include attached KG1-KG2 classes", scd="Type 1"),
    col("ownership", "VARCHAR(7)", "Ownership / management", allowed=["Public", "Mission", "Private"], source=SRC_EMIS, scd="Type 1"),
    col("gender_type", "VARCHAR(5)", "Sex of learners admitted", allowed=["Mixed", "Boys", "Girls"], source=SRC_EMIS, scd="Type 1"),
    col("boarding_status", "VARCHAR(13)", "Day or boarding arrangement", allowed=["Day", "Boarding", "Day/Boarding"], source=SRC_EMIS, scd="Type 1"),
    col("free_shs_category", "VARCHAR(14)", "Free SHS / CSSPS school category", allowed=["A", "B", "C", "D", "E", "Not applicable"], source=SRC_CSSPS, rule="Not applicable for Primary, JHS and private schools", scd="Type 1"),
    col("has_electricity", "BOOLEAN", "School connected to grid or solar power", source=SRC_EMIS, scd="Type 2"),
    col("has_potable_water", "BOOLEAN", "Borehole or pipe-borne water on site", source=SRC_EMIS, scd="Type 2"),
    col("has_girls_toilets", "BOOLEAN", "Separate toilet facilities for girls", source=SRC_EMIS, scd="Type 2"),
    col("has_ict_lab", "BOOLEAN", "Functional ICT laboratory", source=SRC_EMIS, scd="Type 2"),
    col("has_library", "BOOLEAN", "Library or reading room", source=SRC_EMIS, scd="Type 2"),
    col("num_classrooms", "SMALLINT", "Usable classrooms", rng_=(2, 60), unit="classrooms", source=SRC_EMIS, scd="Type 2"),
    col("distance_to_district_capital_km", "DECIMAL(5,1)", "Road distance from school to district capital", rng_=(0, 80), unit="km", source=SRC_EMIS, scd="Type 1"),
    col("effective_from", "DATE", "First date this version is valid", source=SRC_DW, rule="SCD2 housekeeping"),
    col("effective_to", "DATE", "Last date this version is valid (9999-12-31 if current)", source=SRC_DW, rule="Versions of one emis_code never overlap"),
    col("is_current", "BOOLEAN", "True for the latest version", source=SRC_DW, rule="Exactly one current row per emis_code"),
    col("version_no", "SMALLINT", "Version number of the school record", rng_=(1, 5), source=SRC_DW),
])
SPEC["dim_learner"] = dict(kind="dimension", scd="Type 1", grain="One row per examination candidate (pseudonymised).", cols=[
    col("learner_key", "INTEGER", "Surrogate key", "PK", source=SRC_DW),
    col("learner_pseudo_id", "VARCHAR(12)", "Pseudonymised learner ID (no link to any real person)", source=SRC_WAEC, rule="Random token; never a real index or Ghana Card number"),
    col("sex", "VARCHAR(6)", "Sex of learner", allowed=["Male", "Female"], source=SRC_WAEC, scd="Type 1"),
    col("learner_level", "VARCHAR(3)", "Level at which the candidate sat the examination", allowed=["JHS", "SHS"], source=SRC_WAEC, scd="Type 1"),
    col("age_at_entry", "SMALLINT", "Age when the learner entered JHS1 or SHS1", rng_=(10, 22), unit="years", source=SRC_EMIS, scd="Type 1"),
    col("disability_type", "VARCHAR(12)", "Main disability, if any", allowed=["None", "Visual", "Hearing", "Physical", "Intellectual", "Other"], source=SRC_EMIS, scd="Type 1"),
    col("home_language", "VARCHAR(8)", "Language spoken at home", allowed=LANGS, source=SRC_EMIS, scd="Type 1"),
    col("guardian_occupation", "VARCHAR(14)", "Main occupation of parent or guardian", allowed=["Farmer", "Trader", "Artisan", "Public servant", "Unemployed", "Other"], source=SRC_EMIS, scd="Type 1"),
    col("distance_home_to_school_km", "DECIMAL(4,1)", "Distance from home to school", rng_=(0, 25), unit="km", source=SRC_EMIS, scd="Type 1"),
    col("free_shs_beneficiary", "VARCHAR(14)", "Learner benefits from Free SHS", allowed=["Yes", "No", "Not applicable"], source=SRC_CSSPS, rule="Not applicable for JHS candidates", scd="Type 1"),
    col("lives_with", "VARCHAR(8)", "Who the learner lives with", allowed=["Parents", "Relative", "Other"], source=SRC_EMIS, scd="Type 1"),
    col("shs_programme", "VARCHAR(20)", "SHS programme of study", allowed=list(PROGRAMMES) + ["Not applicable"], source=SRC_CSSPS, rule="Not applicable for JHS candidates", scd="Type 1"),
])
SPEC["dim_subject"] = dict(kind="dimension", scd="Type 1", grain="One row per examination subject per examination level.", cols=[
    col("subject_key", "INTEGER", "Surrogate key", "PK", source=SRC_DW),
    col("subject_code", "VARCHAR(8)", "Warehouse subject code (mnemonic, not a WAEC paper code)", source=SRC_WAEC, scd="Type 1"),
    col("subject_name", "VARCHAR(30)", "Subject name", source=SRC_WAEC, scd="Type 1"),
    col("exam_level", "VARCHAR(6)", "Examination the subject belongs to", allowed=["BECE", "WASSCE"], source=SRC_WAEC, scd="Type 1"),
    col("core_or_elective", "VARCHAR(8)", "Core (compulsory) or elective", allowed=["Core", "Elective"], source=SRC_WAEC, scd="Type 1"),
    col("stem_flag", "BOOLEAN", "Science, technology, engineering or mathematics subject", source=SRC_WAEC, scd="Type 1"),
])
SPEC["dim_examination"] = dict(kind="dimension", scd="Type 1", grain="One row per examination type per year per sitting.", cols=[
    col("exam_key", "INTEGER", "Surrogate key", "PK", source=SRC_DW),
    col("exam_type", "VARCHAR(8)", "Examination type", allowed=["BECE", "WASSCE", "Internal"], source=SRC_WAEC, scd="Type 1"),
    col("exam_year", "SMALLINT", "Year the examination was written", rng_=(2021, 2025), source=SRC_WAEC, scd="Type 1"),
    col("sitting", "VARCHAR(8)", "Examination sitting", allowed=["May/June", "Nov/Dec", "Single"], source=SRC_WAEC, rule="BECE has a single sitting; school WASSCE is May/June", scd="Type 1"),
    col("examining_body", "VARCHAR(6)", "Body that sets and marks the examination", allowed=["WAEC", "School"], source=SRC_WAEC, scd="Type 1"),
    col("candidate_class", "VARCHAR(4)", "Class that sits the examination", allowed=["JHS3", "SHS3"], source=SRC_WAEC, scd="Type 1"),
    col("first_paper_date", "DATE", "Date of the first paper (stylised; real calendars shifted after COVID-19)", source=SRC_WAEC, scd="Type 1"),
])
SPEC["dim_teacher"] = dict(kind="dimension", scd="Type 1", grain="One row per subject teacher in an examination-sitting school (current snapshot).", cols=[
    col("teacher_key", "INTEGER", "Surrogate key", "PK", source=SRC_DW),
    col("staff_pseudo_id", "VARCHAR(10)", "Pseudonymised staff ID (not a real staff or payroll number)", source=SRC_HR),
    col("sex", "VARCHAR(6)", "Sex of teacher", allowed=["Male", "Female"], source=SRC_HR, scd="Type 1"),
    col("highest_qualification", "VARCHAR(40)", "Highest academic or professional qualification", allowed=["Diploma in Basic Education", "Bachelor of Education", "Bachelor's degree + PGDE", "Master's degree", "WASSCE/SSSCE", "HND", "Bachelor's degree (non-education)"], source=SRC_HR, scd="Type 1"),
    col("is_trained", "BOOLEAN", "Holds a recognised teaching qualification", source=SRC_HR, rule="Untrained = no Diploma/B.Ed/PGDE", scd="Type 1"),
    col("ges_rank", "VARCHAR(30)", "GES rank", allowed=["Superintendent II", "Superintendent I", "Senior Superintendent II", "Senior Superintendent I", "Principal Superintendent", "Assistant Director II", "Assistant Director I", "Not ranked (untrained)"], source=SRC_HR, scd="Type 1"),
    col("subject_specialism", "VARCHAR(30)", "Main subject taught", source=SRC_HR, scd="Type 1"),
    col("years_of_service", "SMALLINT", "Completed years of teaching service at the load date", rng_=(0, 35), unit="years", source=SRC_HR, scd="Type 1"),
    col("teaches_in_home_district", "BOOLEAN", "Teacher is posted in his or her home district", source=SRC_HR, scd="Type 1"),
    col("employment_type", "VARCHAR(20)", "Employment arrangement", allowed=["GES permanent", "National Service", "Community volunteer", "Private"], source=SRC_HR, scd="Type 1"),
])
SPEC["dim_academic_term"] = dict(kind="dimension", scd="Type 0 (static)", grain="One row per academic term.", cols=[
    col("term_key", "INTEGER", "Surrogate key", "PK", source=SRC_DW),
    col("academic_year", "VARCHAR(9)", "Academic year, e.g. 2023/2024", source=SRC_CAL, scd="Type 0"),
    col("term_number", "SMALLINT", "Term within the academic year", rng_=(1, 3), source=SRC_CAL, scd="Type 0"),
    col("term_label", "VARCHAR(20)", "Readable label, e.g. 2023/2024 T1", source=SRC_CAL, scd="Type 0"),
    col("term_start_date", "DATE", "First day of term (stylised GES calendar)", source=SRC_CAL, scd="Type 0"),
    col("term_end_date", "DATE", "Last day of term (stylised GES calendar)", source=SRC_CAL, scd="Type 0"),
])
SPEC["fact_exam_result"] = dict(kind="fact", main=True, scd="n/a", grain="One row per candidate per subject per examination.", cols=[
    col("exam_result_id", "BIGINT", "Surrogate key of the fact row", "PK", source=SRC_DW),
    col("learner_key", "INTEGER", "Candidate", "FK", ref="dim_learner", source=SRC_WAEC),
    col("school_key", "INTEGER", "School version valid on the exam date", "FK", ref="dim_school", source=SRC_WAEC, rule="Point-in-time join to dim_school"),
    col("location_key", "INTEGER", "Location of the school", "FK", ref="dim_location", source=SRC_EMIS),
    col("subject_key", "INTEGER", "Subject written", "FK", ref="dim_subject", source=SRC_WAEC),
    col("exam_key", "INTEGER", "Examination", "FK", ref="dim_examination", source=SRC_WAEC),
    col("exam_date_key", "INTEGER", "Date the subject paper was written", "FK", ref="dim_date", source=SRC_WAEC),
    col("teacher_key", "INTEGER", "Teacher who taught the subject to the class", "FK", ref="dim_teacher", source=SRC_HR),
    col("candidate_index_no", "VARCHAR(24)", "Synthetic candidate index number (degenerate dimension)", source=SRC_WAEC, rule="Prefix SYN- marks it as synthetic"),
    col("raw_score", "DECIMAL(4,1)", "Combined paper score", nullable=True, rng_=(0, 100), unit="marks out of 100", source=SRC_WAEC, rule="NULL only when is_absent is true"),
    col("grade", "VARCHAR(3)", "Grade awarded (BECE 1-9, WASSCE A1-F9, ABS = absent)", allowed=BECE_GRADES + WASSCE_GRADES + ["ABS"], source=SRC_WAEC, rule="BECE cut-offs 80/70/65/60/55/50/45/40; WASSCE 75/70/65/60/55/50/45/40"),
    col("grade_point", "SMALLINT", "Numeric grade, 1 = best, 9 = worst", nullable=True, rng_=(1, 9), source=SRC_WAEC, rule="NULL only when is_absent is true"),
    col("is_passed", "BOOLEAN", "Credit pass: BECE grade 1-6 or WASSCE A1-C6", source=SRC_WAEC, rule="Pass threshold to confirm with WAEC/DEO in field"),
    col("is_absent", "BOOLEAN", "Candidate registered but absent for the paper", source=SRC_WAEC),
])
SPEC["fact_enrolment"] = dict(kind="fact", scd="n/a", grain="One row per school per class per academic term.", cols=[
    col("enrolment_id", "BIGINT", "Surrogate key of the fact row", "PK", source=SRC_DW),
    col("school_key", "INTEGER", "School version valid at term end", "FK", ref="dim_school", source=SRC_EMIS),
    col("location_key", "INTEGER", "Location of the school", "FK", ref="dim_location", source=SRC_EMIS),
    col("term_key", "INTEGER", "Academic term", "FK", ref="dim_academic_term", source=SRC_REG),
    col("snapshot_date_key", "INTEGER", "Date of the termly return (term end date)", "FK", ref="dim_date", source=SRC_REG),
    col("class_name", "VARCHAR(4)", "Class (degenerate dimension)", allowed=sum(CLASSES.values(), []), source=SRC_REG),
    col("enrolled_boys", "INTEGER", "Boys on roll at term end", rng_=(0, 400), unit="pupils", source=SRC_REG),
    col("enrolled_girls", "INTEGER", "Girls on roll at term end", rng_=(0, 400), unit="pupils", source=SRC_REG),
    col("pupils_with_disability", "INTEGER", "Pupils on roll with a disability", rng_=(0, 50), unit="pupils", source=SRC_REG),
    col("avg_daily_attendance", "DECIMAL(6,1)", "Average number of pupils present per school day", rng_=(0, 800), unit="pupils", source=SRC_REG, rule="Never exceeds enrolled_boys + enrolled_girls"),
    col("dropouts_boys", "INTEGER", "Boys who left school during the term without transfer", rng_=(0, 100), unit="pupils", source=SRC_REG),
    col("dropouts_girls", "INTEGER", "Girls who left school during the term without transfer", rng_=(0, 100), unit="pupils", source=SRC_REG),
    col("repeaters", "INTEGER", "Pupils repeating this class in the academic year", rng_=(0, 100), unit="pupils", source=SRC_REG),
    col("transfers_in", "INTEGER", "Pupils who joined from another school during the term", rng_=(0, 50), unit="pupils", source=SRC_REG),
    col("transfers_out", "INTEGER", "Pupils who moved to another school during the term", rng_=(0, 50), unit="pupils", source=SRC_REG),
])
SPEC["fact_staffing"] = dict(kind="fact", scd="n/a", grain="One row per school per academic term.", cols=[
    col("staffing_id", "BIGINT", "Surrogate key of the fact row", "PK", source=SRC_DW),
    col("school_key", "INTEGER", "School version valid at term end", "FK", ref="dim_school", source=SRC_EMIS),
    col("location_key", "INTEGER", "Location of the school", "FK", ref="dim_location", source=SRC_EMIS),
    col("term_key", "INTEGER", "Academic term", "FK", ref="dim_academic_term", source=SRC_EMIS),
    col("snapshot_date_key", "INTEGER", "Date of the staffing return (term end date)", "FK", ref="dim_date", source=SRC_EMIS),
    col("trained_teachers", "SMALLINT", "Teachers at post holding a teaching qualification", rng_=(1, 200), unit="teachers", source=SRC_HR),
    col("untrained_teachers", "SMALLINT", "Teachers at post without a teaching qualification", rng_=(0, 100), unit="teachers", source=SRC_HR),
    col("female_teachers", "SMALLINT", "Female teachers at post", rng_=(0, 200), unit="teachers", source=SRC_HR),
    col("teacher_vacancies", "SMALLINT", "Posts needed to reach the GES pupil-teacher norm, minus teachers at post", rng_=(0, 100), unit="posts", source=SRC_EMIS, rule="Norms: Primary 35, JHS 25, SHS 25 pupils per teacher"),
    col("total_enrolment", "INTEGER", "Pupils on roll (sum of fact_enrolment for the school and term)", rng_=(1, 5000), unit="pupils", source=SRC_REG, rule="Must reconcile with fact_enrolment"),
    col("pupil_teacher_ratio", "DECIMAL(5,1)", "total_enrolment / (trained + untrained teachers)", rng_=(1, 200), unit="pupils per teacher", source=SRC_EMIS),
    col("pupil_trained_teacher_ratio", "DECIMAL(5,1)", "total_enrolment / trained_teachers", rng_=(1, 300), unit="pupils per trained teacher", source=SRC_EMIS),
])

USAGE = {
    "fact_exam_result": dict(
        questions=["Which districts have the widest gap between girls' and boys' BECE pass rates, and is it narrowing?",
                   "How does the pupil-trained-teacher ratio relate to WASSCE core-subject passes? (join fact_staffing on school and term 3 of the exam year)",
                   "Do trained subject teachers and schools with ICT labs get better Computing/STEM results?"],
        measures=["Pass rate = AVG(is_passed) over non-absent rows", "Mean raw_score", "Absence rate = AVG(is_absent)",
                  "Candidates = COUNT(DISTINCT learner_key)", "Girls-minus-boys pass-rate gap (percentage points)"]),
    "fact_enrolment": dict(
        questions=["Do schools without electricity or girls' toilets show higher dropout among girls?",
                   "How do enrolment, attendance and dropout vary by district, term and season?",
                   "What is the gender parity index by level and district?"],
        measures=["Girls' dropout rate = SUM(dropouts_girls) / SUM(enrolled_girls + dropouts_girls)",
                  "Attendance rate = SUM(avg_daily_attendance) / SUM(enrolled_boys + enrolled_girls)",
                  "Gender parity index = SUM(enrolled_girls) / SUM(enrolled_boys)", "Repetition rate"]),
    "fact_staffing": dict(
        questions=["Which schools and districts have the highest pupil-trained-teacher ratios?",
                   "Where are teacher vacancies concentrated, and is the share of trained teachers rising?"],
        measures=["Pupil-trained-teacher ratio", "Share of trained teachers = trained / (trained + untrained)",
                  "Total vacancies", "Female teacher share"]),
}

# ---------------------------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------------------------
def dkey(d):
    return d.year * 10000 + d.month * 100 + d.day


def choice(options, p=None):
    return options[rng.choice(len(options), p=p)]


def next_weekday(d):
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def nth_weekday(year, month, weekday, n=1):
    d = dt.date(year, month, 1)
    while d.weekday() != weekday:
        d += dt.timedelta(days=1)
    return d + dt.timedelta(weeks=n - 1)


# ---------------------------------------------------------------------------
# 4. Dimensions
# ---------------------------------------------------------------------------
def build_dim_date():
    hol = {}
    for y in range(2020, 2026):
        for (m, d), name in FIXED_HOLIDAYS.items():
            hol[dt.date(y, m, d)] = name
        hol[nth_weekday(y, 12, 4, 1)] = "Farmers' Day"  # first Friday of December
        if y in EASTER:
            e = dt.date(y, *EASTER[y])
            hol[e - dt.timedelta(days=2)] = "Good Friday"
            hol[e + dt.timedelta(days=1)] = "Easter Monday"
        if y in EID_FITR:
            hol[dt.date(y, *EID_FITR[y])] = "Eid al-Fitr"
        if y in EID_ADHA:
            hol[dt.date(y, *EID_ADHA[y])] = "Eid al-Adha"
    rows, d = [], DATE_START
    while d <= DATE_END:
        rows.append(dict(date_key=dkey(d), full_date=d, day_name=d.strftime("%A"),
                         day_of_week=d.isoweekday(), day_of_month=d.day, month_number=d.month,
                         month_name=d.strftime("%B"), quarter=(d.month - 1) // 3 + 1, year=d.year,
                         is_weekend=d.weekday() >= 5, is_public_holiday=d in hol,
                         holiday_name=hol.get(d), season="Rainy" if 5 <= d.month <= 10 else "Dry"))
        d += dt.timedelta(days=1)
    return pd.DataFrame(rows)


def build_dim_location():
    rows, towns = [], []
    k = 1
    for code, dist, cap, lat, lon, others, *_ in DISTRICTS:
        for i, town in enumerate([cap] + others):
            if i == 0:
                tlat, tlon, dist_km = lat, lon, 0.0
            else:
                ang = rng.uniform(0, 2 * math.pi)
                r = rng.uniform(0.05, 0.16)
                tlat, tlon = lat + r * math.sin(ang), lon + r * math.cos(ang)
                dist_km = round(r * 111 * rng.uniform(1.1, 1.4), 1)  # road factor
            rows.append(dict(location_key=k, region=REGION, district_code=code, district=dist,
                             district_capital=cap, town=town, urban_rural="Urban" if i == 0 else "Rural",
                             electoral_area=f"{town} Electoral Area", latitude=round(tlat, 5),
                             longitude=round(tlon, 5)))
            towns.append(dict(location_key=k, district_code=code, town=town, is_capital=i == 0,
                              dist_km=dist_km))
            k += 1
    return pd.DataFrame(rows), towns


def build_schools(towns):
    """Base school list (one per EMIS code) with latent quality parameters."""
    dinfo = {d[0]: d for d in DISTRICTS}
    schools = []
    counters = {}
    for code, *_ in DISTRICTS:
        dtowns = [t for t in towns if t["district_code"] == code]
        is_wa = code == "UW01"
        plan = [("Primary", 5 if is_wa else 4), ("JHS", 5 if is_wa else 4), ("SHS", 4 if is_wa else 2)]
        for level, n in plan:
            for i in range(n):
                # first school of each level sits in the capital; SHS mostly in capitals
                if i == 0 or (level == "SHS" and rng.random() < 0.6):
                    town = dtowns[0]
                else:
                    town = dtowns[1 + (i - 1) % (len(dtowns) - 1)] if level != "SHS" else choice(dtowns[1:])
                urban = town["is_capital"]
                counters[(code, level)] = counters.get((code, level), 0) + 1
                serial = counters[(code, level)]
                if level == "SHS":
                    own = "Private" if (is_wa and serial == 4) else choice(["Public", "Mission"], [0.7, 0.3])
                    gtype = choice(["Mixed", "Girls", "Boys"], [0.85, 0.10, 0.05]) if own != "Private" else "Mixed"
                    board = choice(["Boarding", "Day/Boarding", "Day"], [0.3, 0.55, 0.15])
                    if own == "Private":
                        cat = "Not applicable"
                    elif is_wa:
                        cat = choice(["A", "B", "C"], [0.15, 0.5, 0.35])
                    else:
                        cat = choice(["B", "C", "D", "E"], [0.1, 0.45, 0.3, 0.15])
                else:
                    own = choice(["Public", "Mission", "Private"], [0.62, 0.23, 0.15] if urban else [0.75, 0.22, 0.03])
                    gtype, board, cat = "Mixed", "Day", "Not applicable"
                p_urb = 1.0 if urban else 0.0
                fac = dict(
                    has_electricity=bool(rng.random() < (0.97 if level == "SHS" else 0.9 * p_urb + 0.45 * (1 - p_urb))),
                    has_potable_water=bool(rng.random() < (0.9 if level == "SHS" else 0.8 * p_urb + 0.55 * (1 - p_urb))),
                    has_girls_toilets=bool(rng.random() < (0.85 if level == "SHS" else 0.75 * p_urb + 0.4 * (1 - p_urb))),
                    has_ict_lab=bool(rng.random() < {"SHS": 0.75, "JHS": 0.45 * p_urb + 0.12, "Primary": 0.05}[level]),
                    has_library=bool(rng.random() < {"SHS": 0.7, "JHS": 0.25, "Primary": 0.1}[level]),
                    num_classrooms=int({"SHS": rng.integers(14, 40), "JHS": rng.integers(3, 7), "Primary": rng.integers(6, 10)}[level]),
                )
                remote = dinfo[code][9]
                quality = rng.normal(0, 1) + 0.8 * p_urb - 0.6 * remote + (0.5 if own == "Private" else 0) \
                    + (0.4 if cat in ("A", "B") else 0)
                schools.append(dict(
                    school_id=len(schools), emis_code=f"{code}-{level[0]}-{serial:03d}",
                    school_name=f"{dinfo[code][1]} {level} School {serial:02d}",
                    school_level=level, ownership=own, gender_type=gtype, boarding_status=board,
                    free_shs_category=cat,
                    distance_to_district_capital_km=round(town["dist_km"] + (rng.uniform(0, 2.5) if not urban else rng.uniform(0, 3)), 1),
                    location_key=town["location_key"], district_code=code, urban=urban,
                    quality=quality, remote=remote,
                    trained_share0=float(np.clip(rng.normal(0.88 if urban else 0.7, 0.07) - 0.1 * remote, 0.35, 0.98)),
                    fac0=fac))
    return schools


def build_school_versions(schools):
    """SCD Type 2: facility upgrades create new versions."""
    rows, k = [], 1
    for s in schools:
        fac = dict(s["fac0"])
        events = []
        n_ev = rng.choice([0, 1, 2], p=[0.55, 0.33, 0.12])
        for _ in range(n_ev):
            events.append(DATE_START + dt.timedelta(days=int(rng.integers(270, 1700))))
        events = sorted(set(events))
        starts = [DATE_START] + events
        s["versions"] = []
        for v, start in enumerate(starts, 1):
            if v > 1:  # apply an upgrade
                missing = [f for f in ("has_electricity", "has_girls_toilets", "has_potable_water", "has_ict_lab", "has_library") if not fac[f]]
                if missing and rng.random() < 0.8:
                    # electricity and girls' toilets are the most common upgrades (GETFund / DA projects)
                    w = np.array([3.0 if f in ("has_electricity", "has_girls_toilets") else 1.0 for f in missing])
                    fac[missing[rng.choice(len(missing), p=w / w.sum())]] = True
                else:
                    fac["num_classrooms"] += int(rng.integers(1, 4))
            end = (starts[v] - dt.timedelta(days=1)) if v < len(starts) else OPEN_END
            row = dict(school_key=k, emis_code=s["emis_code"], school_name=s["school_name"],
                       school_level=s["school_level"], ownership=s["ownership"],
                       gender_type=s["gender_type"], boarding_status=s["boarding_status"],
                       free_shs_category=s["free_shs_category"], **fac,
                       distance_to_district_capital_km=s["distance_to_district_capital_km"],
                       effective_from=start, effective_to=end, is_current=end == OPEN_END, version_no=v)
            rows.append(row)
            s["versions"].append((k, start, end, dict(fac)))
            k += 1
    return pd.DataFrame(rows)


def version_at(s, d):
    for key, start, end, fac in s["versions"]:
        if start <= d <= end:
            return key, fac
    raise ValueError("no version")


def build_terms():
    rows, k = [], 1
    for y in ACADEMIC_YEARS:
        spans = [(dt.date(y, 9, 7), dt.date(y, 12, 17)), (dt.date(y + 1, 1, 10), dt.date(y + 1, 4, 8)),
                 (dt.date(y + 1, 4, 29), dt.date(y + 1, 7, 29))]
        for t, (a, b) in enumerate(spans, 1):
            rows.append(dict(term_key=k, academic_year=f"{y}/{y + 1}", term_number=t,
                             term_label=f"{y}/{y + 1} T{t}", term_start_date=next_weekday(a), term_end_date=b,
                             ay=y))
            k += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Facts: enrolment and staffing
# ---------------------------------------------------------------------------
def build_enrolment(schools, terms):
    rows, k = [], 1
    jhs3_t3, shs3_t3 = {}, {}   # candidates for BECE / WASSCE
    for s in schools:
        lvl = s["school_level"]
        base = {"Primary": 55 if s["urban"] else 34, "JHS": 58 if s["urban"] else 33,
                "SHS": 110 if s["urban"] else 62}[lvl] * np.exp(rng.normal(0, 0.22))
        girl_share0 = {"Primary": 0.495, "JHS": 0.488, "SHS": 0.47}[lvl]
        for yi, y in enumerate(ACADEMIC_YEARS):
            yterms = terms[terms.ay == y].sort_values("term_number")
            for ci, cname in enumerate(CLASSES[lvl]):
                # attrition up the grades, slow growth over years
                size = base * (1.02 ** yi) * (1 - 0.035 * ci if lvl == "Primary" else 1 - 0.06 * ci)
                _, fac_start = version_at(s, yterms.iloc[0].term_start_date)
                gs = girl_share0 - (0.03 if not fac_start["has_girls_toilets"] and lvl != "Primary" else 0) - 0.01 * s["remote"]
                if s["gender_type"] == "Girls":
                    gs = 1.0
                elif s["gender_type"] == "Boys":
                    gs = 0.0
                girls = int(rng.poisson(size * gs))
                boys = int(rng.poisson(size * (1 - gs)))
                for _, tr in yterms.iterrows():
                    skey, fac = version_at(s, tr.term_end_date)
                    t3 = tr.term_number == 3
                    base_rate = {"Primary": 0.006, "JHS": 0.013, "SHS": 0.008}[lvl]
                    term_mult = 1.35 if t3 else 1.0          # farming season / end of year
                    g_mult = 1 + 0.9 * (not fac["has_electricity"]) + (1.0 if lvl != "Primary" else 0.3) * (not fac["has_girls_toilets"]) + 0.4 * s["remote"]
                    b_mult = 1 + 0.25 * (not fac["has_electricity"]) + 0.3 * s["remote"]
                    d_g = int(rng.binomial(girls, min(0.2, base_rate * term_mult * g_mult)))
                    d_b = int(rng.binomial(boys, min(0.2, base_rate * term_mult * b_mult)))
                    t_out = int(rng.poisson(0.7 + 0.01 * (boys + girls) / 10))
                    t_in = int(rng.poisson(0.6 + (0.4 if s["urban"] else 0)))
                    t_out = min(t_out, boys + girls - d_g - d_b)
                    out_g = int(rng.binomial(t_out, 0.5)) if gs not in (0.0, 1.0) else (t_out if gs == 1.0 else 0)
                    in_g = int(rng.binomial(t_in, 0.5)) if gs not in (0.0, 1.0) else (t_in if gs == 1.0 else 0)
                    girls = max(0, girls - d_g - out_g + in_g)
                    boys = max(0, boys - d_b - (t_out - out_g) + (t_in - in_g))
                    roll = boys + girls
                    rep_rate = {"KG1": 0.01, "KG2": 0.01, "P1": 0.06, "P2": 0.05}.get(cname, 0.035 if lvl != "SHS" else 0.01)
                    att_rate = 0.88 + 0.03 * fac["has_electricity"] + 0.02 * s["urban"] - 0.05 * s["remote"] \
                        - (0.06 if t3 else 0.02 if tr.term_number == 1 else 0) + rng.normal(0, 0.02)
                    rows.append(dict(enrolment_id=k, school_key=skey, location_key=s["location_key"],
                                     term_key=int(tr.term_key), snapshot_date_key=dkey(tr.term_end_date),
                                     class_name=cname, enrolled_boys=boys, enrolled_girls=girls,
                                     pupils_with_disability=int(rng.binomial(roll, 0.013)),
                                     avg_daily_attendance=round(roll * float(np.clip(att_rate, 0.55, 0.99)), 1),
                                     dropouts_boys=d_b, dropouts_girls=d_g,
                                     repeaters=int(rng.binomial(roll, rep_rate)),
                                     transfers_in=t_in, transfers_out=t_out))
                    k += 1
                    if t3 and cname == "JHS3":
                        jhs3_t3[(s["school_id"], y + 1)] = (boys, girls)
                    if t3 and cname == "SHS3":
                        shs3_t3[(s["school_id"], y + 1)] = (boys, girls)
    return pd.DataFrame(rows), jhs3_t3, shs3_t3


def build_staffing(schools, terms, enrol):
    tot = enrol.groupby(["school_key", "term_key"])[["enrolled_boys", "enrolled_girls"]].sum().sum(axis=1)
    rows, k, pttr_lookup = [], 1, {}
    for s in schools:
        lvl = s["school_level"]
        posted = None
        for _, tr in terms.sort_values("term_key").iterrows():
            skey, _ = version_at(s, tr.term_end_date)
            total = int(tot.loc[(skey, int(tr.term_key))])
            need = math.ceil(total / PTR_NORM[lvl])
            yi = ACADEMIC_YEARS.index(tr.ay)
            if tr.term_number == 1 or posted is None:   # postings happen at the start of the year
                fill = float(np.clip(rng.normal(0.95 if s["urban"] else 0.82, 0.08) - 0.08 * s["remote"], 0.5, 1.15))
                posted = max(2, round(need * fill))
                share = min(0.98, s["trained_share0"] + 0.02 * yi)
                trained = max(1, int(rng.binomial(posted, share)))
            else:
                posted = max(2, posted + int(rng.choice([-1, 0, 0, 0, 1])))
                trained = max(1, min(posted, trained + int(rng.choice([-1, 0, 0, 0]))))
            untrained = posted - trained
            female = int(rng.binomial(posted, 0.45 if s["urban"] else 0.3))
            rows.append(dict(staffing_id=k, school_key=skey, location_key=s["location_key"],
                             term_key=int(tr.term_key), snapshot_date_key=dkey(tr.term_end_date),
                             trained_teachers=trained, untrained_teachers=untrained, female_teachers=female,
                             teacher_vacancies=max(0, need - posted), total_enrolment=total,
                             pupil_teacher_ratio=round(total / posted, 1),
                             pupil_trained_teacher_ratio=round(total / trained, 1)))
            if tr.term_number == 3:
                pttr_lookup[(s["school_id"], tr.ay + 1)] = total / trained
            k += 1
    return pd.DataFrame(rows), pttr_lookup


# ---------------------------------------------------------------------------
# 6. Subjects, examinations, teachers, learners and exam results
# ---------------------------------------------------------------------------
def build_subjects():
    rows, k, info = [], 1, {}
    for code, name, ce, stem, diff in BECE_SUBJECTS:
        rows.append(dict(subject_key=k, subject_code=code, subject_name=name, exam_level="BECE", core_or_elective=ce, stem_flag=stem))
        info[code] = dict(key=k, name=name, stem=stem, diff=diff); k += 1
    for code, name, ce, stem, diff in WASSCE_CORE:
        rows.append(dict(subject_key=k, subject_code=code, subject_name=name, exam_level="WASSCE", core_or_elective=ce, stem_flag=stem))
        info[code] = dict(key=k, name=name, stem=stem, diff=diff); k += 1
    for code, name, stem, diff in WASSCE_ELECTIVES:
        rows.append(dict(subject_key=k, subject_code=code, subject_name=name, exam_level="WASSCE", core_or_elective="Elective", stem_flag=stem))
        info[code] = dict(key=k, name=name, stem=stem, diff=diff); k += 1
    return pd.DataFrame(rows), info


def build_exams():
    rows, k, info = [], 1, {}
    for y in EXAM_YEARS:
        bece = next_weekday(dt.date(y, 6, 14))
        wassce = next_weekday(dt.date(y, 5, 10))
        rows.append(dict(exam_key=k, exam_type="BECE", exam_year=y, sitting="Single", examining_body="WAEC", candidate_class="JHS3", first_paper_date=bece))
        info[("BECE", y)] = dict(key=k, start=bece); k += 1
        rows.append(dict(exam_key=k, exam_type="WASSCE", exam_year=y, sitting="May/June", examining_body="WAEC", candidate_class="SHS3", first_paper_date=wassce))
        info[("WASSCE", y)] = dict(key=k, start=wassce); k += 1
    return pd.DataFrame(rows), info


def paper_date(start, idx, span_days):
    d = start + dt.timedelta(days=int(idx * span_days))
    return next_weekday(d)


RANKS = [(3, "Superintendent II"), (7, "Superintendent I"), (11, "Senior Superintendent II"),
         (15, "Senior Superintendent I"), (20, "Principal Superintendent"), (25, "Assistant Director II"),
         (99, "Assistant Director I")]


def build_teachers(schools, subj):
    rows, k, by_school = [], 1, {}
    for s in schools:
        lvl = s["school_level"]
        if lvl == "Primary":
            continue
        if lvl == "JHS":
            codes = [c[0] for c in BECE_SUBJECTS]
            offered = None
        else:
            offered = list(PROGRAMMES) if s["urban"] else ["General Arts", "Agricultural Science"] + \
                [p for p in ["Business", "Home Economics", "General Science"] if rng.random() < 0.55]
            s["programmes"] = offered
            codes = [c[0] for c in WASSCE_CORE] + sorted({c for p in offered for c in PROGRAMMES[p]})
        share = min(0.98, s["trained_share0"] + 0.08)   # load-date snapshot (2025)
        for code in codes:
            n = 2 if (lvl == "SHS" and code in [c[0] for c in WASSCE_CORE] and s["urban"]) else 1
            for _ in range(n):
                trained = bool(rng.random() < share)
                yrs = int(rng.integers(1, 34) if trained else rng.integers(0, 4))
                if trained:
                    qual = choice(["Diploma in Basic Education", "Bachelor of Education", "Bachelor's degree + PGDE", "Master's degree"],
                                  [0.45, 0.4, 0.1, 0.05] if lvl == "JHS" else [0.03, 0.6, 0.22, 0.15])
                    rank = next(r for lim, r in RANKS if yrs < lim)
                    emp = "Private" if s["ownership"] == "Private" else "GES permanent"
                else:
                    qual = choice(["WASSCE/SSSCE", "HND", "Bachelor's degree (non-education)"], [0.4, 0.25, 0.35])
                    rank = "Not ranked (untrained)"
                    emp = "Private" if s["ownership"] == "Private" else choice(["National Service", "Community volunteer"], [0.6, 0.4])
                rows.append(dict(teacher_key=k, staff_pseudo_id=f"T{rng.integers(16**7, 16**8):08X}"[:9],
                                 sex=choice(["Male", "Female"], [0.66, 0.34] if not s["urban"] else [0.55, 0.45]),
                                 highest_qualification=qual, is_trained=trained, ges_rank=rank,
                                 subject_specialism=subj[code]["name"], years_of_service=yrs,
                                 teaches_in_home_district=bool(rng.random() < 0.45), employment_type=emp))
                by_school.setdefault((s["school_id"], code), []).append((k, trained, qual))
                k += 1
    return pd.DataFrame(rows), by_school


def grade_of(score, exam_type):
    cuts = [80, 70, 65, 60, 55, 50, 45, 40] if exam_type == "BECE" else [75, 70, 65, 60, 55, 50, 45, 40]
    gp = 9
    for i, c in enumerate(cuts):
        if score >= c:
            gp = i + 1
            break
    return (str(gp) if exam_type == "BECE" else WASSCE_GRADES[gp - 1]), gp


def build_learners_and_results(schools, jhs3, shs3, subj, exams, teachers_by_school, pttr):
    dinfo = {d[0]: d for d in DISTRICTS}
    learners, results = [], []
    lk, rk = 1, 1
    used_ids = set()
    for s in schools:
        lvl = s["school_level"]
        if lvl == "Primary":
            continue
        exam_type = "BECE" if lvl == "JHS" else "WASSCE"
        d = dinfo[s["district_code"]]
        lang_w = np.array(d[6]) / sum(d[6])
        for y in EXAM_YEARS:
            boys, girls = (jhs3 if lvl == "JHS" else shs3)[(s["school_id"], y)]
            ex = exams[(exam_type, y)]
            yi = y - EXAM_YEARS[0]
            pttr_eff = -0.18 * (pttr[(s["school_id"], y)] - 35)
            sexes = ["Male"] * boys + ["Female"] * girls
            for seq, sex in enumerate(sexes, 1):
                # ---- learner (dimension row)
                female = sex == "Female"
                age = int(np.clip(round(rng.normal(12.9 + 0.5 * s["remote"], 0.8) if lvl == "JHS" else rng.normal(15.9 + 0.3 * s["remote"], 0.8)), 10, 22))
                disab = choice(["None", "Visual", "Hearing", "Physical", "Intellectual", "Other"], [0.985, 0.004, 0.003, 0.004, 0.002, 0.002])
                lang = LANGS[rng.choice(4, p=lang_w)]
                occ = choice(["Farmer", "Trader", "Artisan", "Public servant", "Unemployed", "Other"],
                             [0.36, 0.24, 0.12, 0.18, 0.05, 0.05] if s["urban"] else [0.64, 0.13, 0.08, 0.05, 0.05, 0.05])
                boarder = lvl == "SHS" and s["boarding_status"] != "Day" and rng.random() < 0.6
                dist = round(float(np.clip(rng.gamma(2.0, 0.6 if boarder else (1.0 if s["urban"] else 1.8)), 0.1, 25)), 1)
                lives = choice(["Parents", "Relative", "Other"], [0.7, 0.22, 0.08])
                prog = "Not applicable"
                fshs = "Not applicable"
                if lvl == "SHS":
                    opts = s["programmes"]
                    w = np.array([PROGRAMME_WEIGHTS[p] for p in opts])
                    if female:   # fewer girls in General Science / Agric; more in Home Economics
                        w = w * np.array([0.7 if p in ("General Science", "Agricultural Science") else 1.6 if p == "Home Economics" else 1 for p in opts])
                    prog = opts[rng.choice(len(opts), p=w / w.sum())]
                    fshs = "No" if s["ownership"] == "Private" else ("Yes" if rng.random() < 0.985 else "No")
                while True:
                    pid = f"L{rng.integers(16**9, 16**10):010X}"[:11]
                    if pid not in used_ids:
                        used_ids.add(pid)
                        break
                learners.append(dict(learner_key=lk, learner_pseudo_id=pid, sex=sex, learner_level=lvl,
                                     age_at_entry=age, disability_type=disab, home_language=lang,
                                     guardian_occupation=occ, distance_home_to_school_km=dist,
                                     free_shs_beneficiary=fshs, lives_with=lives, shs_programme=prog))
                # ---- subjects taken
                if lvl == "JHS":
                    codes = [c[0] for c in BECE_SUBJECTS if c[0] != "BECE-FRE"]
                    if rng.random() < (0.35 if s["urban"] else 0.12):
                        codes.append("BECE-FRE")
                else:
                    el = PROGRAMMES[prog]
                    if len(el) > 4:
                        el = [el[i] for i in sorted(rng.choice(len(el), 4, replace=False))]
                    codes = [c[0] for c in WASSCE_CORE] + el
                ability = rng.normal(0, 7)
                learner_eff = -2.0 * (dist > 5) - 3.0 * (disab != "None") - 1.0 * (lives != "Parents") \
                    + 1.5 * (occ == "Public servant") - 1.0 * (age > (14 if lvl == "JHS" else 17))
                whole_absent = rng.random() < (0.008 + 0.012 * (dist > 6))
                index_no = f"SYN-{exam_type[0]}{y}-{s['emis_code'][2:4]}{s['emis_code'][-3:]}-{seq:04d}"
                span = 1.4 if lvl == "JHS" else 3.0
                for idx, code in enumerate(codes):
                    sj = subj[code]
                    t_opts = teachers_by_school[(s["school_id"], code)]
                    tkey, t_trained, t_qual = t_opts[rng.integers(len(t_opts))]
                    absent = whole_absent or rng.random() < 0.004
                    pdate = paper_date(ex["start"], idx, span)
                    skey, fac = version_at(s, pdate)   # SCD2 point-in-time version
                    if absent:
                        score, grade, gp, passed = None, "ABS", None, False
                    else:
                        sex_eff = 0.0
                        if female and sj["stem"]:                       # gap narrows each year
                            sex_eff = -max(0.0, 1.3 * d[8] - 1.0 * yi)
                        elif female and "English" in sj["name"]:
                            sex_eff = 1.5
                        elif female:
                            sex_eff = -max(0.0, 0.6 * d[8] - 0.45 * yi)
                        ict_eff = (-4.0 if not (fac["has_ict_lab"] and fac["has_electricity"]) else 1.0) if code in ("BECE-CMP",) else 0.0
                        core_eff = pttr_eff if (lvl == "SHS" and code in [c[0] for c in WASSCE_CORE]) else pttr_eff * 0.5
                        teach_eff = (2.5 if t_trained else -2.0) + (1.0 if t_qual == "Master's degree" else 0.0)
                        mean = (50 if lvl == "JHS" else 47) + 4.0 * s["quality"] + d[7] + sj["diff"] + 0.8 * yi \
                            + ability + sex_eff + ict_eff + core_eff + teach_eff + learner_eff
                        score = round(float(np.clip(rng.normal(mean, 10.5), 0, 100)), 1)
                        grade, gp = grade_of(score, exam_type)
                        passed = gp <= 6
                    results.append(dict(exam_result_id=rk, learner_key=lk, school_key=skey,
                                        location_key=s["location_key"], subject_key=sj["key"],
                                        exam_key=ex["key"], exam_date_key=dkey(pdate), teacher_key=tkey,
                                        candidate_index_no=index_no, raw_score=score, grade=grade,
                                        grade_point=gp, is_passed=passed, is_absent=absent))
                    rk += 1
                lk += 1
    res = pd.DataFrame(results)
    res["grade_point"] = res["grade_point"].astype("Int16")
    return pd.DataFrame(learners), res


# ---------------------------------------------------------------------------
# 7. Schema, dictionary, diagram
# ---------------------------------------------------------------------------
def schema_sql():
    out = ["-- CSC 307 Group 1 - Topic 01: Basic and Senior High School Performance Data Warehouse",
           "-- Upper West Region, Ghana. SYNTHETIC DATA. Generated by generate_data.py v" + SCRIPT_VERSION,
           "-- Target: PostgreSQL 13+ (also runs on DuckDB). Dimensions first, then facts.", "",
           "DROP TABLE IF EXISTS " + ", ".join([t for t in SPEC if SPEC[t]["kind"] == "fact"] +
                                               [t for t in SPEC if SPEC[t]["kind"] == "dimension"]) + ";", ""]
    for t in [t for t in SPEC if SPEC[t]["kind"] == "dimension"] + [t for t in SPEC if SPEC[t]["kind"] == "fact"]:
        sp = SPEC[t]
        out.append(f"-- {t}: {sp['grain']} SCD: {sp['scd']}")
        lines = []
        for c in sp["cols"]:
            ln = f"    {c['name']:<34} {c['sqltype']:<14}"
            if c["key"] == "PK":
                ln += " PRIMARY KEY"
            elif not c["nullable"]:
                ln += " NOT NULL"
            lines.append(ln.rstrip())
        for c in sp["cols"]:
            if c["key"] == "FK":
                ref_pk = next(x["name"] for x in SPEC[c["ref"]]["cols"] if x["key"] == "PK")
                lines.append(f"    CONSTRAINT fk_{t}_{c['name']} FOREIGN KEY ({c['name']}) REFERENCES {c['ref']} ({ref_pk})")
        if t == "dim_school":
            lines.append("    CONSTRAINT uq_dim_school_version UNIQUE (emis_code, version_no)")
            lines.append("    CONSTRAINT ck_dim_school_dates CHECK (effective_from <= effective_to)")
        if t == "fact_exam_result":
            lines.append("    CONSTRAINT ck_absent_score CHECK ((is_absent AND raw_score IS NULL) OR (NOT is_absent AND raw_score IS NOT NULL))")
        out.append(f"CREATE TABLE {t} (\n" + ",\n".join(lines) + "\n);\n")
    out.append("-- Helpful indexes on fact foreign keys")
    for t, sp in SPEC.items():
        for c in sp["cols"]:
            if c["key"] == "FK":
                out.append(f"CREATE INDEX ix_{t}_{c['name']} ON {t} ({c['name']});")
    return "\n".join(out) + "\n"


def data_dictionary():
    rows = []
    for t, sp in SPEC.items():
        for c in sp["cols"]:
            if c["allowed"]:
                av = "; ".join(map(str, c["allowed"]))
            elif c["range"]:
                av = f"{c['range'][0]} to {c['range'][1]}"
            elif c["sqltype"] == "BOOLEAN":
                av = "True; False"
            else:
                av = "free text" if c["sqltype"].startswith("VARCHAR") else "any valid value"
            ln = c["sqltype"][c["sqltype"].find("(") + 1:-1] if "(" in c["sqltype"] else \
                {"INTEGER": "4 bytes", "BIGINT": "8 bytes", "SMALLINT": "2 bytes", "DATE": "4 bytes", "BOOLEAN": "1 byte"}[c["sqltype"]]
            rows.append(dict(table_name=t, table_type=sp["kind"], column_name=c["name"], description=c["desc"],
                             data_type=c["sqltype"], key_type=c["key"] or "",
                             references=f"{c['ref']}" if c["ref"] else "", length=ln,
                             nullable="Yes" if c["nullable"] else "No", allowed_values_or_range=av,
                             unit=c["unit"], source_system=c["source"], scd_type=c["scd"],
                             business_rule=c["rule"]))
    return pd.DataFrame(rows)


def star_dot():
    fact_col, dim_col = "#F4B183", "#9DC3E6"
    lines = ['digraph star {', '  graph [rankdir=LR, splines=true, overlap=false, nodesep=0.35, ranksep=1.2, bgcolor="white", '
             'label="CSC 307 Group 1 - School Performance Data Warehouse (Upper West, synthetic)\\nConstellation schema: 3 fact tables share conformed dimensions", labelloc=t, fontsize=20, fontname="Helvetica-Bold"];',
             '  node [shape=plaintext, fontname="Helvetica", fontsize=10];', '  edge [color="#555555", arrowhead=crow, arrowtail=none];']
    for t, sp in SPEC.items():
        colr = fact_col if sp["kind"] == "fact" else dim_col
        title = t + (" (SCD 2)" if sp["scd"] == "Type 2" else "") + ("  [MAIN FACT]" if sp.get("main") else "")
        rows = [f'<tr><td bgcolor="{colr}" align="center"><b>{title}</b></td></tr>']
        for c in sp["cols"]:
            tag = "PK " if c["key"] == "PK" else "FK " if c["key"] == "FK" else ""
            rows.append(f'<tr><td align="left">{tag}{c["name"]} : {c["sqltype"].lower()}</td></tr>')
        lines.append(f'  {t} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="3">{"".join(rows)}</table>>];')
    for t, sp in SPEC.items():
        for c in sp["cols"]:
            if c["key"] == "FK":
                lines.append(f'  {c["ref"]} -> {t} [taillabel="1", headlabel="*", fontsize=8];')
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 8. Quality checks
# ---------------------------------------------------------------------------
def quality_checks(tables, schools):
    checks = []

    def add(check, table, column, result, passed, detail=""):
        checks.append(dict(check=check, table=table, column=column, result=result, passed=bool(passed), detail=detail))

    for t, df in tables.items():
        sp = SPEC[t]
        minimum = 5000 if sp.get("main") else (500 if sp["kind"] == "fact" else 1)
        add("row_count", t, "", len(df), len(df) >= minimum, f"minimum {minimum}")
        pk = next(c["name"] for c in sp["cols"] if c["key"] == "PK")
        add("primary_key_unique", t, pk, int(df[pk].duplicated().sum()), not df[pk].duplicated().any(), "duplicate keys")
        for c in sp["cols"]:
            s = df[c["name"]]
            miss = round(100 * s.isna().mean(), 3)
            if not c["nullable"]:
                add("missing_pct_required", t, c["name"], miss, miss == 0)
            else:
                add("missing_pct_nullable", t, c["name"], miss, True, "nullable by design")
            nn = s.dropna()
            if c["sqltype"].startswith("VARCHAR"):
                maxlen = int(c["sqltype"][8:-1])
                bad = int((nn.astype(str).str.len() > maxlen).sum())
                add("varchar_length", t, c["name"], bad, bad == 0, f"values longer than {maxlen}")
            if c["allowed"]:
                bad = int((~nn.astype(str).isin([str(a) for a in c["allowed"]])).sum())
                add("allowed_values", t, c["name"], bad, bad == 0, "rows outside allowed list")
            if c["range"]:
                lo, hi = c["range"]
                bad = int(((nn.astype(float) < lo) | (nn.astype(float) > hi)).sum())
                add("value_range", t, c["name"], bad, bad == 0, f"rows outside {lo}..{hi}")
            if c["key"] == "FK":
                ref = tables[c["ref"]]
                ref_pk = next(x["name"] for x in SPEC[c["ref"]]["cols"] if x["key"] == "PK")
                ok = round(100 * s.isin(ref[ref_pk]).mean(), 3)
                add("fk_validity_pct", t, c["name"], ok, ok == 100.0, f"-> {c['ref']}.{ref_pk}")
    # SCD2: non-overlapping, one current row per natural key
    ds = tables["dim_school"].sort_values(["emis_code", "effective_from"])
    overlaps = 0
    for _, g in ds.groupby("emis_code"):
        f, to = list(g.effective_from), list(g.effective_to)
        overlaps += sum(1 for i in range(1, len(f)) if f[i] <= to[i - 1] or f[i] != to[i - 1] + dt.timedelta(days=1))
    add("scd2_non_overlapping_contiguous", "dim_school", "effective_from/to", overlaps, overlaps == 0)
    cur = ds.groupby("emis_code").is_current.sum()
    add("scd2_one_current_row", "dim_school", "is_current", int((cur != 1).sum()), (cur == 1).all())
    # SCD2 point-in-time: fact date inside the version's validity window
    dd = tables["dim_date"].set_index("date_key").full_date
    for t, dcol in [("fact_exam_result", "exam_date_key"), ("fact_enrolment", "snapshot_date_key"), ("fact_staffing", "snapshot_date_key")]:
        f = tables[t][["school_key", dcol]].drop_duplicates().merge(ds[["school_key", "effective_from", "effective_to"]], on="school_key")
        fd = f[dcol].map(dd)
        bad = int(((fd < f.effective_from) | (fd > f.effective_to)).sum())
        add("scd2_point_in_time", t, "school_key", bad, bad == 0, "fact date outside school version validity")
    # business rules
    fe = tables["fact_exam_result"]
    bad = int((fe.is_absent & fe.raw_score.notna()).sum() + (~fe.is_absent & fe.raw_score.isna()).sum())
    add("rule_absent_has_no_score", "fact_exam_result", "raw_score", bad, bad == 0)
    bad = int((fe.is_passed & fe.is_absent).sum())
    add("rule_absent_not_passed", "fact_exam_result", "is_passed", bad, bad == 0)
    en = tables["fact_enrolment"]
    bad = int((en.avg_daily_attendance > en.enrolled_boys + en.enrolled_girls).sum())
    add("rule_attendance_le_roll", "fact_enrolment", "avg_daily_attendance", bad, bad == 0)
    # reconciliation 1 (as Code 2.2): total enrolment computed two ways
    direct = int((en.enrolled_boys + en.enrolled_girls).sum())
    via_dist = int(en.merge(tables["dim_location"], on="location_key").groupby("district")[["enrolled_boys", "enrolled_girls"]].sum().sum().sum())
    add("reconciliation_enrolment_direct_vs_by_district", "fact_enrolment", "enrolled_boys+enrolled_girls",
        f"{direct} vs {via_dist}", direct == via_dist)
    # reconciliation 2: staffing total_enrolment vs enrolment fact
    st = tables["fact_staffing"]
    via_en = int(en.groupby(["school_key", "term_key"])[["enrolled_boys", "enrolled_girls"]].sum().sum(axis=1).sum())
    add("reconciliation_staffing_total_vs_enrolment", "fact_staffing", "total_enrolment",
        f"{int(st.total_enrolment.sum())} vs {via_en}", int(st.total_enrolment.sum()) == via_en)
    # reconciliation 3: raw score total direct vs by subject
    s1 = round(fe.raw_score.sum(), 1)
    s2 = round(fe.merge(tables["dim_subject"], on="subject_key").groupby("subject_name").raw_score.sum().sum(), 1)
    add("reconciliation_raw_score_direct_vs_by_subject", "fact_exam_result", "raw_score", f"{s1} vs {s2}", abs(s1 - s2) < 0.05)
    # reconciliation 4: JHS3/SHS3 term-3 roll = candidates
    cand = tables["dim_learner"].shape[0]
    roll = en[(en.class_name.isin(["JHS3", "SHS3"])) & (en.term_key.isin(tables["dim_academic_term"].query("term_number == 3").term_key))]
    roll = int((roll.enrolled_boys + roll.enrolled_girls).sum())
    add("reconciliation_candidates_vs_exam_class_roll", "dim_learner", "learner_key", f"{cand} vs {roll}", cand == roll)
    return pd.DataFrame(checks)


# ---------------------------------------------------------------------------
# 9. Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    dim_date = build_dim_date()
    dim_location, towns = build_dim_location()
    schools = build_schools(towns)
    dim_school = build_school_versions(schools)
    terms = build_terms()
    fact_enrolment, jhs3, shs3 = build_enrolment(schools, terms)
    fact_staffing, pttr = build_staffing(schools, terms, fact_enrolment)
    dim_subject, subj = build_subjects()
    dim_exam, exams = build_exams()
    dim_teacher, t_by_school = build_teachers(schools, subj)
    dim_learner, fact_exam = build_learners_and_results(schools, jhs3, shs3, subj, exams, t_by_school, pttr)

    tables = {"dim_date": dim_date, "dim_location": dim_location, "dim_school": dim_school,
              "dim_learner": dim_learner, "dim_subject": dim_subject, "dim_examination": dim_exam,
              "dim_teacher": dim_teacher, "dim_academic_term": terms.drop(columns="ay"),
              "fact_exam_result": fact_exam, "fact_enrolment": fact_enrolment, "fact_staffing": fact_staffing}
    # keep spec column order
    for t in tables:
        tables[t] = tables[t][[c["name"] for c in SPEC[t]["cols"]]]

    qc = quality_checks(tables, schools)
    failed = qc[~qc.passed]
    rejected = {t: 0 for t in tables}   # rows dropped by validation (none expected)

    for t, df in tables.items():
        df.to_csv(os.path.join(args.out, f"{t}.csv"), index=False)
    with open(os.path.join(args.out, "schema.sql"), "w") as f:
        f.write(schema_sql())
    dd = data_dictionary()
    dd.to_csv(os.path.join(args.out, "data_dictionary.csv"), index=False)
    qc.to_csv(os.path.join(args.out, "quality_report.csv"), index=False)
    with open(os.path.join(args.out, "star_schema.dot"), "w") as f:
        f.write(star_dot())
    if shutil.which("dot"):
        subprocess.run(["dot", "-Tpng", "-Gdpi=110", os.path.join(args.out, "star_schema.dot"),
                        "-o", os.path.join(args.out, "star_schema.png")], check=True)

    keys = {"PK", "FK"}
    housekeeping = {"effective_from", "effective_to", "is_current", "version_no"}
    business_attrs = int(sum(1 for t in SPEC for c in SPEC[t]["cols"] if c["key"] not in keys and c["name"] not in housekeeping))
    meta = {
        "dataset": "School Performance Data: CSC_307_GRP_01_2026 (Synthetic)",
        "course": "CSC 307 Fundamentals of Data Mining and Warehousing, UBIDS",
        "group": 1, "topic": "01 - A Basic and Senior High School Performance Data Warehouse",
        "sector": "Education", "region": REGION, "districts": DIST_NAMES,
        "synthetic": True,
        "synthetic_statement": "All records are synthetic. No real learner, teacher, school or examination result is represented.",
        "licence": "CC BY 4.0",
        "operational": {
            "script": "generate_data.py", "script_version": SCRIPT_VERSION, "random_seed": SEED,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "load_date": dt.date.today().isoformat(),
            "coverage": {"calendar": f"{DATE_START} to {DATE_END}", "academic_years": [f"{y}/{y + 1}" for y in ACADEMIC_YEARS],
                         "exam_years": EXAM_YEARS},
            "row_counts": {t: int(len(df)) for t, df in tables.items()},
            "rejected_rows": rejected,
            "quality_checks_run": int(len(qc)), "quality_checks_failed": int(len(failed)),
        },
        "schema": {
            "type": "Constellation (fact constellation / galaxy) star schema",
            "fact_tables": [t for t in SPEC if SPEC[t]["kind"] == "fact"],
            "dimension_tables": [t for t in SPEC if SPEC[t]["kind"] == "dimension"],
            "conformed_dimensions": ["dim_date", "dim_location", "dim_school", "dim_academic_term"],
            "total_columns": int(sum(len(SPEC[t]["cols"]) for t in SPEC)),
            "business_attributes_and_measures": business_attrs,
        },
        "tables": {t: {"type": SPEC[t]["kind"], "grain": SPEC[t]["grain"], "scd": SPEC[t]["scd"],
                       "primary_key": next(c["name"] for c in SPEC[t]["cols"] if c["key"] == "PK"),
                       "foreign_keys": {c["name"]: c["ref"] for c in SPEC[t]["cols"] if c["key"] == "FK"},
                       "row_count": int(len(tables[t])), "columns": len(SPEC[t]["cols"]),
                       "business_rules": [f"{c['name']}: {c['rule']}" for c in SPEC[t]["cols"] if c["rule"]],
                       **({"usage": USAGE[t]} if t in USAGE else {})}
                   for t in SPEC},
    }
    with open(os.path.join(args.out, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"Wrote {len(tables)} tables to {args.out}/")
    for t, df in tables.items():
        print(f"  {t:<20} {len(df):>8,} rows")
    print(f"Business attributes + measures: {business_attrs}; total columns: {meta['schema']['total_columns']}")
    print(f"Quality checks: {len(qc)} run, {len(failed)} failed")
    if len(failed):
        print(failed.to_string())
        sys.exit(1)


if __name__ == "__main__":
    main()
