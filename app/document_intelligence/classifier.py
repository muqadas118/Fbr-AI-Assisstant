"""
Document Classifier - Production-Grade
======================================

Classifies documents into categories:
- Tax returns (ITR, Sales Tax, FED)
- Invoices (sales, purchase, services)
- Receipts (POS, e-receipts)
- Certificates (Form 16A, 16B, salary)
- Bank statements
- Property documents
- Vehicle documents
- Contracts/Agreements
- Notices/Orders
- Audit reports
- Financial statements
- General correspondence
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DocumentType(str, Enum):
    """Specific document types."""
    # Tax Returns
    INCOME_TAX_RETURN = "income_tax_return"
    SALES_TAX_RETURN = "sales_tax_return"
    FED_EXCISE_RETURN = "fed_excise_return"
    WEALTH_STATEMENT = "wealth_statement"
    WHT_STATEMENT = "wht_statement"

    # Invoices
    SALES_INVOICE = "sales_invoice"
    PURCHASE_INVOICE = "purchase_invoice"
    SERVICE_INVOICE = "service_invoice"
    PROFORMA_INVOICE = "proforma_invoice"
    E_INVOICE = "e_invoice"

    # Receipts
    CASH_RECEIPT = "cash_receipt"
    POS_RECEIPT = "pos_receipt"
    E_RECEIPT = "e_receipt"
    BANK_RECEIPT = "bank_receipt"

    # Certificates
    FORM_16A = "form_16a"  # Salary certificate
    FORM_16B = "form_16b"  # WHT certificate
    SALARY_CERTIFICATE = "salary_certificate"
    TDS_CERTIFICATE = "tds_certificate"
    TAX_EXEMPTION_CERT = "tax_exemption_cert"
    NTN_CERTIFICATE = "ntn_certificate"
    PRC_CERTIFICATE = "prc_certificate"  # Provincial Revenue Certificate

    # Banking
    BANK_STATEMENT = "bank_statement"
    BANK_LETTER = "bank_letter"
    ACCOUNT_OPENING = "account_opening"
    CHEQUE = "cheque"

    # Property
    SALE_DEED = "sale_deed"
    ALLOTMENT_LETTER = "allotment_letter"
    POSSESSION_LETTER = "possession_letter"
    PROPERTY_TAX_RECEIPT = "property_tax_receipt"
    RENT_AGREEMENT = "rent_agreement"

    # Vehicle
    VEHICLE_REGISTRATION = "vehicle_registration"
    VEHICLE_TRANSFER = "vehicle_transfer"
    VEHICLE_INSURANCE = "vehicle_insurance"

    # Legal
    CONTRACT = "contract"
    AGREEMENT = "agreement"
    POWER_OF_ATTORNEY = "power_of_attorney"
    AFFIDAVIT = "affidavit"

    # FBR Communications
    FBR_NOTICE = "fbr_notice"
    FBR_ORDER = "fbr_order"
    FBR_INTIMATION = "fbr_intimation"
    FBR_CORRESPONDENCE = "fbr_correspondence"

    # Audit
    AUDIT_REPORT = "audit_report"
    AUDIT_QUERY = "audit_query"
    TAX_AUDIT_REPORT = "tax_audit_report"

    # Financial
    PROFIT_LOSS = "profit_loss"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    GENERAL_LEDGER = "general_ledger"

    # Other
    ID_DOCUMENT = "id_document"  # CNIC, passport
    UTILITY_BILL = "utility_bill"
    SALARY_SLIP = "salary_slip"
    LEAVE_LETTER = "leave_letter"
    UNKNOWN = "unknown"


class DocumentCategory(str, Enum):
    """Higher-level document categories."""
    TAX_RETURN = "tax_return"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    CERTIFICATE = "certificate"
    BANKING = "banking"
    PROPERTY = "property"
    VEHICLE = "vehicle"
    LEGAL = "legal"
    FBR_DOCUMENT = "fbr_document"
    AUDIT = "audit"
    FINANCIAL = "financial"
    IDENTITY = "identity"
    OTHER = "other"


# Mapping from type to category
TYPE_TO_CATEGORY = {
    DocumentType.INCOME_TAX_RETURN: DocumentCategory.TAX_RETURN,
    DocumentType.SALES_TAX_RETURN: DocumentCategory.TAX_RETURN,
    DocumentType.FED_EXCISE_RETURN: DocumentCategory.TAX_RETURN,
    DocumentType.WEALTH_STATEMENT: DocumentCategory.TAX_RETURN,
    DocumentType.WHT_STATEMENT: DocumentCategory.TAX_RETURN,
    DocumentType.SALES_INVOICE: DocumentCategory.INVOICE,
    DocumentType.PURCHASE_INVOICE: DocumentCategory.INVOICE,
    DocumentType.SERVICE_INVOICE: DocumentCategory.INVOICE,
    DocumentType.PROFORMA_INVOICE: DocumentCategory.INVOICE,
    DocumentType.E_INVOICE: DocumentCategory.INVOICE,
    DocumentType.CASH_RECEIPT: DocumentCategory.RECEIPT,
    DocumentType.POS_RECEIPT: DocumentCategory.RECEIPT,
    DocumentType.E_RECEIPT: DocumentCategory.RECEIPT,
    DocumentType.BANK_RECEIPT: DocumentCategory.RECEIPT,
    DocumentType.FORM_16A: DocumentCategory.CERTIFICATE,
    DocumentType.FORM_16B: DocumentCategory.CERTIFICATE,
    DocumentType.SALARY_CERTIFICATE: DocumentCategory.CERTIFICATE,
    DocumentType.TDS_CERTIFICATE: DocumentCategory.CERTIFICATE,
    DocumentType.TAX_EXEMPTION_CERT: DocumentCategory.CERTIFICATE,
    DocumentType.NTN_CERTIFICATE: DocumentCategory.CERTIFICATE,
    DocumentType.PRC_CERTIFICATE: DocumentCategory.CERTIFICATE,
    DocumentType.BANK_STATEMENT: DocumentCategory.BANKING,
    DocumentType.BANK_LETTER: DocumentCategory.BANKING,
    DocumentType.ACCOUNT_OPENING: DocumentCategory.BANKING,
    DocumentType.CHEQUE: DocumentCategory.BANKING,
    DocumentType.SALE_DEED: DocumentCategory.PROPERTY,
    DocumentType.ALLOTMENT_LETTER: DocumentCategory.PROPERTY,
    DocumentType.POSSESSION_LETTER: DocumentCategory.PROPERTY,
    DocumentType.PROPERTY_TAX_RECEIPT: DocumentCategory.PROPERTY,
    DocumentType.RENT_AGREEMENT: DocumentCategory.PROPERTY,
    DocumentType.VEHICLE_REGISTRATION: DocumentCategory.VEHICLE,
    DocumentType.VEHICLE_TRANSFER: DocumentCategory.VEHICLE,
    DocumentType.VEHICLE_INSURANCE: DocumentCategory.VEHICLE,
    DocumentType.CONTRACT: DocumentCategory.LEGAL,
    DocumentType.AGREEMENT: DocumentCategory.LEGAL,
    DocumentType.POWER_OF_ATTORNEY: DocumentCategory.LEGAL,
    DocumentType.AFFIDAVIT: DocumentCategory.LEGAL,
    DocumentType.FBR_NOTICE: DocumentCategory.FBR_DOCUMENT,
    DocumentType.FBR_ORDER: DocumentCategory.FBR_DOCUMENT,
    DocumentType.FBR_INTIMATION: DocumentCategory.FBR_DOCUMENT,
    DocumentType.FBR_CORRESPONDENCE: DocumentCategory.FBR_DOCUMENT,
    DocumentType.AUDIT_REPORT: DocumentCategory.AUDIT,
    DocumentType.AUDIT_QUERY: DocumentCategory.AUDIT,
    DocumentType.TAX_AUDIT_REPORT: DocumentCategory.AUDIT,
    DocumentType.PROFIT_LOSS: DocumentCategory.FINANCIAL,
    DocumentType.BALANCE_SHEET: DocumentCategory.FINANCIAL,
    DocumentType.CASH_FLOW: DocumentCategory.FINANCIAL,
    DocumentType.GENERAL_LEDGER: DocumentCategory.FINANCIAL,
    DocumentType.ID_DOCUMENT: DocumentCategory.IDENTITY,
    DocumentType.UTILITY_BILL: DocumentCategory.OTHER,
    DocumentType.SALARY_SLIP: DocumentCategory.OTHER,
    DocumentType.LEAVE_LETTER: DocumentCategory.OTHER,
}


@dataclass
class ClassificationResult:
    """Result of document classification."""
    document_type: DocumentType
    category: DocumentCategory
    confidence: float
    matched_signals: list[str] = field(default_factory=list)
    secondary_types: list[tuple[DocumentType, float]] = field(default_factory=list)


# Classification signals: (doc_type, [keyword/phrase patterns])
CLASSIFICATION_SIGNALS = {
    DocumentType.INCOME_TAX_RETURN: [
        ("income tax return", 10),
        ("annual return statement", 8),
        ("salary details", 3),
        ("tax computation", 5),
        ("wealth reconciliation", 6),
        ("ITR", 4),
    ],
    DocumentType.SALES_TAX_RETURN: [
        ("sales tax return", 10),
        ("STR", 4),
        ("output tax", 6),
        ("input tax", 6),
        ("federal excise", 5),
    ],
    DocumentType.FORM_16A: [
        ("form 16a", 10),
        ("certificate of salary", 8),
        ("annual salary statement", 6),
        ("salary certificate", 8),
    ],
    DocumentType.FORM_16B: [
        ("form 16b", 10),
        ("withholding tax certificate", 9),
        ("wht certificate", 8),
        ("tax deduction at source", 7),
    ],
    DocumentType.SALARY_CERTIFICATE: [
        ("salary certificate", 8),
        ("employment certificate", 6),
        ("income certificate", 5),
        ("gross salary", 4),
    ],
    DocumentType.BANK_STATEMENT: [
        ("bank statement", 10),
        ("account statement", 8),
        ("transaction history", 7),
        ("opening balance", 5),
        ("closing balance", 5),
    ],
    DocumentType.SALES_INVOICE: [
        ("sales invoice", 10),
        ("tax invoice", 9),
        ("invoice number", 6),
        ("invoice date", 5),
        ("buyer", 3),
        ("seller", 3),
        ("gst", 4),
    ],
    DocumentType.PURCHASE_INVOICE: [
        ("purchase invoice", 10),
        ("vendor invoice", 8),
        ("supplier invoice", 8),
        ("purchase order", 5),
    ],
    DocumentType.CASH_RECEIPT: [
        ("cash receipt", 10),
        ("payment receipt", 7),
        ("received with thanks", 5),
        ("acknowledgment", 4),
    ],
    DocumentType.POS_RECEIPT: [
        ("pos receipt", 10),
        ("point of sale", 8),
        ("terminal", 4),
        ("approval code", 6),
    ],
    DocumentType.SALE_DEED: [
        ("sale deed", 10),
        ("conveyance deed", 9),
        ("transfer deed", 7),
        ("property transfer", 6),
    ],
    DocumentType.RENT_AGREEMENT: [
        ("rent agreement", 10),
        ("tenancy agreement", 9),
        ("lease agreement", 7),
        ("monthly rent", 4),
    ],
    DocumentType.VEHICLE_REGISTRATION: [
        ("vehicle registration", 10),
        ("registration certificate", 9),
        ("motor vehicle", 6),
        ("chassis number", 6),
        ("engine number", 5),
    ],
    DocumentType.FBR_NOTICE: [
        ("show cause notice", 10),
        ("notice under section", 8),
        ("income tax ordinance", 5),
        ("demand notice", 8),
        ("you are hereby", 4),
    ],
    DocumentType.FBR_ORDER: [
        ("assessment order", 10),
        ("appellate order", 9),
        ("tax authority", 4),
        ("determination of income", 6),
    ],
    DocumentType.CONTRACT: [
        ("contract", 8),
        ("agreement", 7),
        ("party of the first part", 6),
        ("whereas", 4),
        ("hereby agree", 5),
    ],
    DocumentType.AUDIT_REPORT: [
        ("audit report", 10),
        ("auditor's report", 9),
        ("true and fair view", 8),
        ("opinion", 3),
    ],
    DocumentType.PROFIT_LOSS: [
        ("profit and loss", 10),
        ("income statement", 8),
        ("statement of profit", 9),
        ("gross profit", 5),
        ("net profit", 5),
    ],
    DocumentType.BALANCE_SHEET: [
        ("balance sheet", 10),
        ("statement of financial position", 9),
        ("total assets", 5),
        ("total liabilities", 5),
    ],
    DocumentType.SALARY_SLIP: [
        ("salary slip", 10),
        ("payslip", 8),
        ("net pay", 4),
        ("earnings", 3),
        ("deductions", 3),
    ],
    DocumentType.NTN_CERTIFICATE: [
        ("NTN certificate", 10),
        ("national tax number", 8),
        ("taxpayer registration", 7),
    ],
    DocumentType.ID_DOCUMENT: [
        ("CNIC", 8),
        ("computerized national identity", 9),
        ("identity card", 6),
        ("passport", 5),
        ("date of birth", 3),
    ],
}


class DocumentClassifier:
    """Classify documents based on content signals."""

    @staticmethod
    def classify(text: str, filename: Optional[str] = None) -> ClassificationResult:
        """
        Classify document based on text content and optional filename.
        """
        if not text or len(text.strip()) < 5:
            return ClassificationResult(
                document_type=DocumentType.UNKNOWN,
                category=DocumentCategory.OTHER,
                confidence=0.0,
                matched_signals=[],
            )

        text_lower = text.lower()
        scores: dict[DocumentType, float] = {}
        matched_signals_per_type: dict[DocumentType, list[str]] = {}

        # Score based on content signals
        for doc_type, signals in CLASSIFICATION_SIGNALS.items():
            type_score = 0.0
            type_signals = []
            for pattern, weight in signals:
                if pattern.lower() in text_lower:
                    type_score += weight
                    type_signals.append(pattern)
            if type_score > 0:
                scores[doc_type] = type_score
                matched_signals_per_type[doc_type] = type_signals

        # Boost based on filename
        if filename:
            fn_lower = filename.lower()
            for doc_type, signals in CLASSIFICATION_SIGNALS.items():
                for pattern, weight in signals:
                    if pattern.lower().replace(" ", "") in fn_lower.replace(" ", ""):
                        scores[doc_type] = scores.get(doc_type, 0) + weight * 0.5

        # If no signals, return UNKNOWN
        if not scores:
            return ClassificationResult(
                document_type=DocumentType.UNKNOWN,
                category=DocumentCategory.OTHER,
                confidence=0.0,
                matched_signals=[],
            )

        # Sort by score
        sorted_types = sorted(scores.items(), key=lambda x: -x[1])
        best_type, best_score = sorted_types[0]

        # Calculate confidence (normalize to 0-1)
        # Max possible score is 10+8+6+5+4+3+3 = 39
        max_possible = 40
        confidence = min(best_score / max_possible, 1.0)

        # Get category
        category = TYPE_TO_CATEGORY.get(best_type, DocumentCategory.OTHER)

        # Secondary types
        secondary = [(t, s) for t, s in sorted_types[1:4] if s > 5]

        return ClassificationResult(
            document_type=best_type,
            category=category,
            confidence=round(confidence, 3),
            matched_signals=matched_signals_per_type.get(best_type, []),
            secondary_types=secondary,
        )

    @staticmethod
    def classify_by_filename(filename: str) -> Optional[DocumentType]:
        """Quick classification based on filename only."""
        if not filename:
            return None
        fn_lower = filename.lower()

        # Common filename patterns
        if "invoice" in fn_lower or "inv" in fn_lower:
            return DocumentType.SALES_INVOICE
        if "receipt" in fn_lower:
            return DocumentType.CASH_RECEIPT
        if "salary" in fn_lower or "payslip" in fn_lower:
            return DocumentType.SALARY_SLIP
        if "itr" in fn_lower or ("income" in fn_lower and "return" in fn_lower):
            return DocumentType.INCOME_TAX_RETURN
        if "16a" in fn_lower:
            return DocumentType.FORM_16A
        if "16b" in fn_lower:
            return DocumentType.FORM_16B
        if "bank" in fn_lower and "statement" in fn_lower:
            return DocumentType.BANK_STATEMENT
        if "notice" in fn_lower:
            return DocumentType.FBR_NOTICE
        if "order" in fn_lower:
            return DocumentType.FBR_ORDER
        if "audit" in fn_lower:
            return DocumentType.AUDIT_REPORT
        if "balance" in fn_lower or "pl" in fn_lower or "pnl" in fn_lower:
            return DocumentType.PROFIT_LOSS
        if "contract" in fn_lower or "agreement" in fn_lower:
            return DocumentType.CONTRACT

        return None
