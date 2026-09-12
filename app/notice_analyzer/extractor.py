"""
Notice Information Extractor - Production-Grade
===============================================

Extracts key information from FBR notices:
- Notice ID/Reference number
- Issue date
- Response deadline
- Tax year(s) involved
- Section references (legal)
- Tax amount demanded
- Penalty amount
- Total amount payable
- Taxpayer NTN
- Taxpayer name
- FBR office/Commissioner
- Bank account for payment

Uses regex patterns to extract structured info.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ExtractedInfo:
    """All extracted notice information."""
    notice_id: Optional[str] = None
    reference_number: Optional[str] = None
    issue_date: Optional[str] = None
    deadline: Optional[str] = None
    deadline_days: Optional[int] = None

    taxpayer_name: Optional[str] = None
    taxpayer_ntn: Optional[str] = None
    taxpayer_cnic: Optional[str] = None

    fbr_office: Optional[str] = None
    commissioner_name: Optional[str] = None

    tax_years: list[str] = field(default_factory=list)
    sections_cited: list[str] = field(default_factory=list)

    tax_amount: Optional[float] = None
    penalty_amount: Optional[float] = None
    total_demanded: Optional[float] = None

    bank_account: Optional[str] = None

    raw_text: str = ""
    extraction_quality: float = 0.0  # 0-1
    notes: list[str] = field(default_factory=list)


class NoticeExtractor:
    """Production-grade notice info extractor."""

    # Regex patterns
    PATTERNS = {
        "ntn": [
            r"NTN[:\s]*(\d{5,8}-\d)",
            r"NTN[:\s]*(\d{7,8})",
            r"N\.T\.N[:\s]*(\d{7,8})",
            r"National Tax No[.:]*\s*(\d{5,8}-\d)",
            r"National Tax No[.:]*\s*(\d{7,8})",
        ],
        "cnic": [
            r"CNIC[:\s]*(\d{5}-?\d{7}-?\d{1})",
            r"CNIC No[.:]*\s*(\d{5}-?\d{7}-?\d{1})",
            r"(\d{5}-\d{7}-\d)",
        ],
        "notice_id": [
            r"Notice No[.:]*\s*([A-Z0-9/-]+)",
            r"Reference No[.:]*\s*([A-Z0-9/-]+)",
            r"Letter No[.:]*\s*([A-Z0-9/-]+)",
        ],
        "date": [
            r"(?:dated|dated:|date of issue)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
            r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        ],
        "section": [
            r"Section\s+(\d+\w?(?:\(\d+\))?(?:\(\w+\))?)",
            r"u/s\s+(\d+\w?(?:\(\d+\))?)",
            r"under\s+section\s+(\d+\w?(?:\(\d+\))?)",
        ],
        "tax_year": [
            r"Tax\s+Year\s+(\d{4})",
            r"T\.\s*Y\.?\s*(\d{4})",
            r"(\d{4})\s+(?:assessment|return)",
        ],
        "rupees": [
            r"(?:PKR|Rs\.?|Rupees)\s*([\d,]+(?:\.\d+)?)",
            r"amount\s+of\s+(?:PKR|Rs\.?)\s*([\d,]+(?:\.\d+)?)",
        ],
    }

    MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Parse various date formats."""
        if not date_str:
            return None
        date_str = date_str.strip()

        # Try DD-MM-YYYY
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Try "Day Month Year"
        match = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_str)
        if match:
            day, month, year = match.groups()
            month_num = NoticeExtractor.MONTHS.get(month.lower())
            if month_num:
                try:
                    return datetime(int(year), month_num, int(day))
                except ValueError:
                    return None
        return None

    @staticmethod
    def _parse_amount(amount_str: str) -> Optional[float]:
        """Parse amount with commas."""
        if not amount_str:
            return None
        try:
            return float(amount_str.replace(",", "").replace(" ", ""))
        except ValueError:
            return None

    @staticmethod
    def _extract_pattern(text: str, patterns: list[str]) -> Optional[str]:
        """Extract using multiple patterns."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _extract_all_patterns(text: str, patterns: list[str]) -> list[str]:
        """Extract all matches using patterns."""
        results = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            results.extend(matches)
        # Deduplicate
        return list(dict.fromkeys(results))

    @staticmethod
    def extract(text: str) -> ExtractedInfo:
        """Extract all information from notice text."""
        if not text:
            return ExtractedInfo(extraction_quality=0.0)

        info = ExtractedInfo(raw_text=text[:2000])  # Keep first 2000 chars
        notes = []
        fields_found = 0
        total_fields = 10  # Track how many fields we found

        # NTN
        ntn = NoticeExtractor._extract_pattern(text, NoticeExtractor.PATTERNS["ntn"])
        if ntn:
            info.taxpayer_ntn = ntn
            fields_found += 1

        # CNIC
        cnic = NoticeExtractor._extract_pattern(text, NoticeExtractor.PATTERNS["cnic"])
        if cnic:
            info.taxpayer_cnic = cnic
            fields_found += 1

        # Notice ID
        notice_id = NoticeExtractor._extract_pattern(text, NoticeExtractor.PATTERNS["notice_id"])
        if notice_id:
            info.notice_id = notice_id
            info.reference_number = notice_id
            fields_found += 1

        # Issue date
        date_str = NoticeExtractor._extract_pattern(text, NoticeExtractor.PATTERNS["date"])
        if date_str:
            parsed = NoticeExtractor._parse_date(date_str)
            if parsed:
                info.issue_date = parsed.strftime("%Y-%m-%d")
                fields_found += 1
                # Calculate default deadline (30 days from issue)
                deadline = parsed + timedelta(days=30)
                info.deadline = deadline.strftime("%Y-%m-%d")
                info.deadline_days = 30
            else:
                info.issue_date = date_str

        # Tax years
        tax_years = NoticeExtractor._extract_all_patterns(text, NoticeExtractor.PATTERNS["tax_year"])
        info.tax_years = tax_years[:5]  # Max 5
        if tax_years:
            fields_found += 1

        # Sections cited
        sections = NoticeExtractor._extract_all_patterns(text, NoticeExtractor.PATTERNS["section"])
        info.sections_cited = sections[:10]  # Max 10
        if sections:
            fields_found += 1
            notes.append(f"Cited {len(sections)} legal sections")

        # Tax/penalty/total amounts
        amounts = NoticeExtractor._extract_all_patterns(text, NoticeExtractor.PATTERNS["rupees"])
        parsed_amounts = [NoticeExtractor._parse_amount(a) for a in amounts]
        parsed_amounts = [a for a in parsed_amounts if a is not None and a > 0]

        if parsed_amounts:
            # Heuristic: largest amount is usually total
            info.total_demanded = max(parsed_amounts) if parsed_amounts else None
            # Try to identify specific amounts
            if len(parsed_amounts) >= 2:
                # Sort descending
                sorted_amounts = sorted(parsed_amounts, reverse=True)
                info.total_demanded = sorted_amounts[0]
                # Look for "penalty" context
                penalty_match = re.search(
                    r"penalty[:\s]+(?:PKR|Rs\.?)?\s*([\d,]+(?:\.\d+)?)",
                    text,
                    re.IGNORECASE
                )
                if penalty_match:
                    info.penalty_amount = NoticeExtractor._parse_amount(penalty_match.group(1))

                # Look for "tax" context
                tax_match = re.search(
                    r"tax[:\s]+(?:PKR|Rs\.?)?\s*([\d,]+(?:\.\d+)?)",
                    text,
                    re.IGNORECASE
                )
                if tax_match:
                    info.tax_amount = NoticeExtractor._parse_amount(tax_match.group(1))

            fields_found += 1
            notes.append(f"Found {len(parsed_amounts)} monetary references")

        # Quality score
        info.extraction_quality = round(fields_found / total_fields, 2)

        if fields_found == 0:
            notes.append("No structured info extracted - text may need OCR")

        info.notes = notes
        return info
