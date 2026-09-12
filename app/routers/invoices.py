"""
Invoice Intelligence Router
===========================

FastAPI router for invoice processing operations.
Exposes InvoiceAPI as HTTP endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.invoice_intelligence import InvoiceAPI, get_invoice_api

logger = logging.getLogger("fbr_api.invoices")

router = APIRouter(prefix="/invoices", tags=["Invoice Intelligence"])


# =============================================================================
# Request Models
# =============================================================================

class InvoiceProcessRequest(BaseModel):
    """Request to process an invoice."""
    text: str = Field(
        ...,
        min_length=5,
        max_length=500000,
        description="Invoice text (extracted from PDF/image)"
    )
    invoice_id: Optional[str] = Field(
        default=None,
        description="Optional invoice reference"
    )


class InvoiceReconcileRequest(BaseModel):
    """Request to reconcile a period's invoices."""
    purchase_invoices: Optional[list[dict]] = Field(
        default=None,
        description="List of purchase invoice data"
    )
    sales_invoices: Optional[list[dict]] = Field(
        default=None,
        description="List of sales invoice data"
    )


# =============================================================================
# Response Models
# =============================================================================

class InvoiceIssueResponse(BaseModel):
    """Invoice validation issue."""
    field: str
    message: str
    severity: str


class InvoiceValidationResponse(BaseModel):
    """Invoice validation result."""
    is_valid: bool
    score: float
    errors: int
    warnings: int
    issues: list[InvoiceIssueResponse]


class InvoiceResponse(BaseModel):
    """Invoice data."""
    id: str
    number: Optional[str] = None
    date: Optional[str] = None
    type: str
    seller_ntn: Optional[str] = None
    buyer_ntn: Optional[str] = None
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float


class InvoiceProcessResponse(BaseModel):
    """Invoice processing response."""
    analysis_id: str
    invoice: InvoiceResponse
    validation: InvoiceValidationResponse
    is_duplicate: bool
    duplicate_of: Optional[str] = None
    itc_eligible: bool
    tax_impact: float
    summary: str
    duration_ms: float


class ReconciliationReportResponse(BaseModel):
    """Invoice reconciliation report."""
    total_invoices: int
    total_sales: float
    total_purchases: float
    total_output_tax: float
    total_input_tax: float
    net_payable: float
    vendor_count: int
    month_count: int
    confidence_score: float
    recommendations: list[str]


class InvoiceDashboardResponse(BaseModel):
    """Invoice dashboard data."""
    total_invoices: int
    sales_count: int
    purchases_count: int
    total_sales: float
    total_purchases: float
    total_output_tax: float
    total_input_tax: float
    net_payable: float
    payable_status: str


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/process", response_model=InvoiceProcessResponse)
async def process_invoice(request: InvoiceProcessRequest) -> InvoiceProcessResponse:
    """
    Process and validate a tax invoice.

    Extracts invoice data, validates format and NTN/STRN numbers,
    checks for duplicates, and determines ITC eligibility.
    """
    try:
        api = get_invoice_api()
        result = api.process_invoice(request.text, request.invoice_id)

        return InvoiceProcessResponse(
            analysis_id=result["analysis_id"],
            invoice=InvoiceResponse(**result["invoice"]),
            validation=InvoiceValidationResponse(
                is_valid=result["validation"]["is_valid"],
                score=result["validation"]["score"],
                errors=result["validation"]["errors"],
                warnings=result["validation"]["warnings"],
                issues=[
                    InvoiceIssueResponse(**i)
                    for i in result["validation"]["issues"]
                ],
            ),
            is_duplicate=result["is_duplicate"],
            duplicate_of=result["duplicate_of"],
            itc_eligible=result["itc_eligible"],
            tax_impact=result["tax_impact"],
            summary=result["summary"],
            duration_ms=result["duration_ms"],
        )
    except Exception as e:
        logger.exception("Error processing invoice")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process invoice"
        )


@router.post("/reconcile", response_model=ReconciliationReportResponse)
async def reconcile_period(
    request: InvoiceReconcileRequest,
) -> ReconciliationReportResponse:
    """
    Reconcile a period's sales and purchase invoices.

    Calculates output tax, input tax, and net tax payable.
    Generates ITC reconciliation report.
    """
    try:
        api = get_invoice_api()

        # Convert dicts to ExtractedInvoice if provided
        purchase_invoices = None
        sales_invoices = None

        if request.purchase_invoices:
            from app.invoice_intelligence.extractor import ExtractedInvoice
            purchase_invoices = [
                ExtractedInvoice(**inv) for inv in request.purchase_invoices
            ]
        if request.sales_invoices:
            from app.invoice_intelligence.extractor import ExtractedInvoice
            sales_invoices = [
                ExtractedInvoice(**inv) for inv in request.sales_invoices
            ]

        result = api.reconcile_period(purchase_invoices, sales_invoices)

        return ReconciliationReportResponse(**result)
    except Exception as e:
        logger.exception("Error reconciling invoices")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reconcile invoices"
        )


@router.get("/dashboard", response_model=InvoiceDashboardResponse)
async def get_invoice_dashboard() -> InvoiceDashboardResponse:
    """
    Get invoice dashboard summary.

    Returns aggregated invoice statistics.
    """
    try:
        api = get_invoice_api()
        result = api.get_dashboard()
        return InvoiceDashboardResponse(**result)
    except Exception as e:
        logger.exception("Error getting dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard"
        )


@router.get("/export")
async def export_invoices(
    format: str = "json",
) -> dict | str:
    """
    Export all stored invoices as JSON or CSV.

    Returns all processed invoices in the requested format.
    """
    try:
        api = get_invoice_api()
        return api.export_invoices(format)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Error exporting invoices")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export invoices"
        )
