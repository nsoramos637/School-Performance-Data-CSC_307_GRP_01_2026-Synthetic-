# School Performance Data: CSC_307_GRP_01_2026 (Synthetic)

> **This dataset is entirely synthetic.** No real learner, teacher, school, examination result or personal identifier is included. School names, EMIS codes, index numbers, staff IDs and learner IDs are generated. Any resemblance to a real school or person is coincidental. Do not use it to judge any real school or district.

| Item | Detail |
|---|---|
| Course | CSC 307 Fundamentals of Data Mining and Warehousing, UBIDS (Department of Computer Science) |
| Group / Topic | Group 1 · Topic 01: A Basic and Senior High School Performance Data Warehouse |
| Sector | Education |
| Region | Upper West Region, Ghana: 11 districts |
| Coverage | Academic years 2020/2021 to 2024/2025; BECE and WASSCE 2021–2025 |
| Licence | CC BY 4.0 |
| Generator | `generate_data.py` v1.0.0, seed `307012026` |

## 1. Purpose
The warehouse tracks enrolment, attendance, dropout, staffing and examination results for basic and senior high schools. It is meant to help District Education Offices target support where learning outcomes lag. It answers three questions:

1. Which districts have the widest gap between girls' and boys' BECE pass rates, and is the gap narrowing?
2. Do schools without electricity or girls' toilets show higher dropout among girls?
3. How does the pupil-trained-teacher ratio relate to WASSCE core-subject passes?

## 2. Schema summary
This is a constellation schema: 3 fact tables share 8 dimensions. Every table appears in `schema.sql` and `star_schema.png`. There are **124 columns** in total, of which **94 are business attributes and measures**, excluding surrogate keys, foreign keys and SCD housekeeping columns. The brief requires at least 70.

| Table | Type | Grain | Rows |
|---|---|---|---|
| `fact_exam_result` (**main**) | Fact | One row per candidate per subject per examination | 162,293 |
| `fact_enrolment` | Fact | One row per school per class per academic term | 8,505 |
| `fact_staffing` | Fact | One row per school per academic term | 1,710 |
| `dim_date` | Conformed dimension | One row per day, 2020-09-01 to 2025-12-31 | 1,948 |
| `dim_location` | Conformed dimension | One row per town or community in the 11 districts | 45 |
| `dim_school` | **SCD Type 2** | One row per school per facilities version | 172 (114 schools) |
| `dim_learner` | Dimension | One row per examination candidate (pseudonymised) | 19,111 |
| `dim_subject` | Dimension | One row per subject per examination level | 32 |
| `dim_examination` | Dimension | One row per examination per year and sitting | 10 |
| `dim_teacher` | Dimension | One row per subject teacher in JHS and SHS schools | 1,039 |
| `dim_academic_term` | Dimension | One row per academic term | 15 |

**SCD Type 2 (`dim_school`).** The tracked attributes are `has_electricity`, `has_potable_water`, `has_girls_toilets`, `has_ict_lab`, `has_library` and `num_classrooms`. A facility upgrade closes the old row (`effective_to`) and opens a new one. Each fact row points to the version that was valid on its own date: the exam paper date, or the term-end date for enrolment and staffing. A dropout, for example, is therefore linked to the facilities the school had at the time.

**Conformed dimensions.** `dim_date` and `dim_location` follow the shared layout in the brief: district codes `UW01` to `UW11` and the same date attributes. Topics 02 to 10 can therefore be combined into one regional warehouse.

**Grading rules.** BECE grades run from 1 to 9, with cut-offs at 80, 70, 65, 60, 55, 50, 45 and 40. WASSCE grades run from A1 to F9, with cut-offs at 75, 70, 65, 60, 55, 50, 45 and 40. A pass is a BECE grade of 1 to 6 or a WASSCE grade of A1 to C6. When a candidate is absent, `grade` is `ABS` and both `raw_score` and `grade_point` are NULL.

## 3. Files
| File | Contents |
|---|---|
| `schema.sql` | PostgreSQL DDL with primary keys, foreign keys, CHECK constraints and indexes. It has been tested on PostgreSQL with every CSV loaded and all constraints enforced. |
| `star_schema.png` / `star_schema.dot` | Schema diagram, built from the same specification as `schema.sql` |
| `data_dictionary.csv` | One row per column (124 in all), giving the technical and business metadata: table, column, description, data type, key, reference, length, nullability, allowed values or range, unit, source system, SCD type and business rule |
| `metadata.json` | Operational metadata (generation time, seed, script version, row counts, rejected rows, check results), the grain of each table, business rules, and usage metadata (the questions each fact table answers and suggested measures) |
| `dim_*.csv`, `fact_*.csv` | Warehouse tables. They are clean, every foreign key is valid, and booleans are stored as `True`/`False`. |
| `generate_data.py` | Generator script with a fixed seed. Running it rebuilds every file above. |
| `quality_report.csv` | Results of the 285 automated quality checks. All of them pass. |

## 4. How the data was generated
Run `python generate_data.py --out output`. It needs Python 3.9+, pandas and numpy; Graphviz is optional and only used to draw the PNG. The seed is fixed, so every CSV comes out byte-for-byte the same on each run. The steps are:

1. **Locations.** Each of the 11 districts gets its capital plus three or four communities. Coordinates are approximate.
2. **Schools.** Each district gets 4 Primary schools (with KG classes attached), 4 JHS and 2 SHS; Wa Municipal gets 5, 5 and 4. Every school has a hidden "quality" score that is higher in urban areas and lower in remote districts. About 45% of schools receive one or two facility upgrades between 2021 and 2025, and each upgrade creates a new SCD2 version.
3. **Enrolment.** For each class, the term 1 roll is drawn first. Later terms carry the roll forward after subtracting dropouts and transfers out and adding transfers in. Girls' dropout rises where the school has no electricity or girls' toilets and in remote districts. Dropout is also higher in term 3, which falls in the farming season. Attendance is lower in term 3 and in remote areas.
4. **Staffing.** Teachers at post are set at the start of each year from the enrolment and the GES pupil-teacher norms: 35 for Primary and 25 for JHS and SHS. Remote schools fill fewer posts. The share of trained teachers rises by about 2 percentage points a year.
5. **Examinations.** The number of BECE and WASSCE candidates equals the term 3 roll of JHS3 and SHS3. Each candidate takes 9 or 10 BECE subjects, or 4 WASSCE core subjects plus 4 electives from their programme. A candidate's score combines: school quality, a district effect, subject difficulty, a learner ability shared across that learner's subjects, learner factors (distance to school, disability, who they live with, age), a trained-teacher effect, a pupil-trained-teacher-ratio effect (strongest in WASSCE core subjects), an ICT-lab effect on Computing, and a girls' gap in STEM subjects that narrows each year. About 1.3% of entries are absent.
6. **Quality checks** (all must pass, or the script stops with an error):
   - row counts against the minimums;
   - primary keys are unique;
   - 0% missing values in required columns;
   - VARCHAR lengths fit the DDL;
   - allowed-value and range checks on every coded column;
   - 100% foreign-key validity;
   - SCD2 versions do not overlap, have no gaps and have exactly one current row;
   - point-in-time validity of each fact's `school_key`;
   - business rules (an absent candidate has no score and cannot pass; attendance never exceeds the roll);
   - **reconciliations**: total enrolment summed directly equals the sum of district subtotals; `fact_staffing.total_enrolment` equals the sum from `fact_enrolment`; total raw score summed directly equals the sum of subject subtotals; the number of candidates equals the JHS3 + SHS3 term 3 roll.

Running the three questions on this dataset gives:
- The regional BECE gap between boys' and girls' pass rates narrows from about 8 percentage points (2021) to under 1 (2025). Wa East and Sissala West had the widest gaps in 2021–22.
- In JHS and SHS, girls' dropout is about 4.5% per term where a school has neither electricity nor girls' toilets, and about 1.2% where it has both.
- The WASSCE core pass rate falls from about 61% where the pupil-trained-teacher ratio is below 25 to about 19% where it is above 45.

## 5. Field findings reflected
The design takes the source systems named in the brief as its starting point: the EMIS annual school census, WAEC BECE/WASSCE results, CSSPS/Free SHS placement records and GES/CAGD staff records. The following assumptions **still have to be confirmed with the actors we interview**. Several of them are also noted in the `business_rule` column of the data dictionary:

- Pass thresholds: BECE grade 1–6 and WASSCE A1–C6.
- How the termly returns are kept (class-level counts sent to the District Education Office) and whether dropout is recorded by sex.
- Which facility attributes EMIS records and whether their history is kept. This decides which dimension needs SCD2.
- The real Upper West electoral areas and urban/rural classification. The current values are placeholders.
- The real GES term calendar and WAEC timetables. The dates used here are simplified because the 2021–2023 calendars were shifted by COVID-19.

*(Group: replace this list with the actual findings from the field report before you publish.)*

## 6. Limitations
- All values are synthetic. The effect sizes are designed so that the questions can be answered; they are not estimates from real data.
- Coordinates, electoral areas and some moveable public holidays are approximate.
- `dim_teacher` is a current snapshot (SCD Type 1), so teacher transfers between years are not tracked.
- Each school has a fixed set of subject teachers, and teachers are not linked to `fact_staffing` counts.
- There are no private WASSCE (Nov/Dec) candidates and no internal school examinations, although `dim_examination` allows for both.
- Basic schools are generated as separate Primary and JHS schools. In practice many share a compound.

## 7. Example query (PostgreSQL)
```sql
-- Q1: BECE girls' vs boys' pass-rate gap by district and year
SELECT l.district, e.exam_year,
       ROUND(100*(AVG(CASE WHEN dl.sex='Male'   THEN f.is_passed::int END)
                - AVG(CASE WHEN dl.sex='Female' THEN f.is_passed::int END)),1) AS gap_pp
FROM fact_exam_result f
JOIN dim_learner dl USING (learner_key)
JOIN dim_location l USING (location_key)
JOIN dim_examination e USING (exam_key)
WHERE e.exam_type = 'BECE' AND NOT f.is_absent
GROUP BY 1, 2 ORDER BY 1, 2;
```
