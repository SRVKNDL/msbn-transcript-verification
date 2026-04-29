"""Mississippi Practical Nursing curriculum reference data."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PNVCourse:
    code: str
    name: str
    credit_hours: int
    contact_hours: int
    lecture_hours: int
    lab_hours: int
    clinical_hours: int
    # Earliest allowed semester, using Option #1 as the baseline.
    earliest_semester: int
    # Tracks equivalent courses across the different scheduling options.
    option_group: Optional[str] = None


# 2024 PNV framework, with Option #1 hours as the baseline.
FRAMEWORK_CITATION = "according to PRACTICAL NURSING MISSISSIPPI CURRICULUM FRAMEWORK (2024)"

MS_PN_COURSES: dict[str, PNVCourse] = {
    "PNV 1116": PNVCourse(
        code="PNV 1116", name="Practical Nursing Foundations",
        credit_hours=16, contact_hours=375,
        lecture_hours=135, lab_hours=150, clinical_hours=90,
        earliest_semester=1,
        option_group="foundations_combined",
    ),
    "PNV 1213": PNVCourse(
        code="PNV 1213", name="Body Structure and Function",
        credit_hours=3, contact_hours=45,
        lecture_hours=45, lab_hours=0, clinical_hours=0,
        earliest_semester=1,
    ),
    "PNV 1216": PNVCourse(
        code="PNV 1216", name="Intermediate Practical Nursing (FS)",
        credit_hours=16, contact_hours=375,
        lecture_hours=165, lab_hours=30, clinical_hours=180,
        earliest_semester=2,
        option_group="intermediate_combined",
    ),
    "PNV 1312": PNVCourse(
        code="PNV 1312", name="Intermediate Practical Nursing (SS)",
        credit_hours=12, contact_hours=230,
        lecture_hours=155, lab_hours=0, clinical_hours=75,
        earliest_semester=3,
        option_group="intermediate_combined",
    ),
    "PNV 1412": PNVCourse(
        code="PNV 1412", name="Advanced Practical Nursing",
        credit_hours=12, contact_hours=300,
        lecture_hours=120, lab_hours=0, clinical_hours=180,
        earliest_semester=2,
        option_group="advanced_combined",
    ),
    "PNV 1426": PNVCourse(
        code="PNV 1426", name="Fundamentals of Nursing Theory",
        credit_hours=6, contact_hours=90,
        lecture_hours=90, lab_hours=0, clinical_hours=0,
        earliest_semester=1,
        option_group="foundations_separate",
    ),
    "PNV 1437": PNVCourse(
        code="PNV 1437", name="Fundamentals of Nursing Lab/Clinical",
        credit_hours=7, contact_hours=240,
        lecture_hours=0, lab_hours=150, clinical_hours=90,
        earliest_semester=1,
        option_group="foundations_separate",
    ),
    "PNV 1443": PNVCourse(
        code="PNV 1443", name="Nursing Fundamentals and Clinical",
        credit_hours=13, contact_hours=330,
        lecture_hours=90, lab_hours=150, clinical_hours=90,
        earliest_semester=1,
        option_group="foundations_option2",
    ),
    "PNV 1516": PNVCourse(
        code="PNV 1516", name="Advanced Practical Nursing (SS)",
        credit_hours=16, contact_hours=390,
        lecture_hours=165, lab_hours=0, clinical_hours=225,
        earliest_semester=3,
        option_group="advanced_combined",
    ),
    "PNV 1524": PNVCourse(
        code="PNV 1524", name="IV Therapy & Pharmacology",
        credit_hours=4, contact_hours=75,
        lecture_hours=45, lab_hours=30, clinical_hours=0,
        earliest_semester=2,
    ),
    "PNV 1614": PNVCourse(
        code="PNV 1614", name="Medical/Surgical Nursing Theory",
        credit_hours=4, contact_hours=60,
        lecture_hours=60, lab_hours=0, clinical_hours=0,
        earliest_semester=2,
        option_group="medsurg_separate",
    ),
    "PNV 1622": PNVCourse(
        code="PNV 1622", name="Medical/Surgical Nursing Clinical",
        credit_hours=2, contact_hours=90,
        lecture_hours=0, lab_hours=0, clinical_hours=90,
        earliest_semester=2,
        option_group="medsurg_separate",
    ),
    "PNV 1634": PNVCourse(
        code="PNV 1634", name="Alterations in Adult Health Theory",
        credit_hours=4, contact_hours=60,
        lecture_hours=60, lab_hours=0, clinical_hours=0,
        earliest_semester=2,
        option_group="medsurg_separate",
    ),
    "PNV 1642": PNVCourse(
        code="PNV 1642", name="Alterations in Adult Health Clinical",
        credit_hours=2, contact_hours=90,
        lecture_hours=0, lab_hours=0, clinical_hours=90,
        earliest_semester=2,
        option_group="medsurg_separate",
    ),
    "PNV 1666": PNVCourse(
        code="PNV 1666", name="Medical/Surgical Nursing Concepts & Clinical",
        credit_hours=6, contact_hours=150,
        lecture_hours=60, lab_hours=0, clinical_hours=90,
        earliest_semester=2,
        option_group="medsurg_option2",
    ),
    "PNV 1676": PNVCourse(
        code="PNV 1676", name="Alterations in Adult Health Concepts & Clinical",
        credit_hours=6, contact_hours=150,
        lecture_hours=60, lab_hours=0, clinical_hours=90,
        earliest_semester=2,
        option_group="medsurg_option2",
    ),
    "PNV 1682": PNVCourse(
        code="PNV 1682", name="Adult Health Nursing Concepts & Clinical",
        credit_hours=12, contact_hours=300,
        lecture_hours=120, lab_hours=0, clinical_hours=180,
        earliest_semester=2,
        option_group="medsurg_option3",
    ),
    "PNV 1714": PNVCourse(
        code="PNV 1714", name="Maternal-Child Nursing",
        credit_hours=4, contact_hours=70,
        lecture_hours=55, lab_hours=0, clinical_hours=15,
        earliest_semester=3,
    ),
    "PNV 1728": PNVCourse(
        code="PNV 1728", name="Specialty Areas in Nursing",
        credit_hours=8, contact_hours=140,
        lecture_hours=110, lab_hours=0, clinical_hours=30,
        earliest_semester=3,
        option_group="specialty_combined",
    ),
    "PNV 1814": PNVCourse(
        code="PNV 1814", name="Mental Health Nursing",
        credit_hours=4, contact_hours=70,
        lecture_hours=55, lab_hours=0, clinical_hours=15,
        earliest_semester=3,
    ),
    "PNV 1914": PNVCourse(
        code="PNV 1914", name="Nursing Transition",
        credit_hours=4, contact_hours=90,
        lecture_hours=45, lab_hours=0, clinical_hours=45,
        earliest_semester=3,
    ),
}

# PNV codes recognized by the current framework.
VALID_PNV_CODES: frozenset[str] = frozenset(MS_PN_COURSES.keys())

# Official program totals from the framework.
TOTAL_SEMESTER_HOURS = 44
TOTAL_CLOCK_HOURS = 980

# Older transcripts may need framework-era crosswalks.
COURSE_CROSSWALK_2012_TO_2024: dict[str, str] = {
    # POC behavior: accept current PNV codes across eras. Add era-specific
    # validation when historical transcript coverage matters.
}

# BIO substitutions for PNV 1213.
VALID_BIO_SUBSTITUTIONS = {
    "BIO 2514": "Anatomy & Physiology I Lecture and Lab",
    "BIO 2524": "Anatomy & Physiology II Lecture and Lab",
}
