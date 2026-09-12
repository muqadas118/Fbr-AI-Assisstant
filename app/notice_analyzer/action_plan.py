"""
Action Plan Generator - Production-Grade
=======================================

Generates step-by-step action plans for FBR notices based on type.

Each notice type has a specific action plan:
- What to do first
- Documents to gather
- Where to file response
- Common mistakes to avoid
- Professional help needed (yes/no)
- Time required
"""

from dataclasses import dataclass, field
from typing import Optional

from app.notice_analyzer.classifier import NoticeType


@dataclass
class ActionStep:
    """Single action step in the plan."""
    step_number: int
    title: str
    description: str
    documents_needed: list[str] = field(default_factory=list)
    estimated_hours: float = 1.0
    priority: str = "medium"  # critical, high, medium, low


@dataclass
class ActionPlan:
    """Complete action plan for a notice."""
    notice_type: str
    summary: str
    total_steps: int
    estimated_total_hours: float
    requires_professional_help: bool
    requires_payment: bool
    steps: list[ActionStep] = field(default_factory=list)
    common_mistakes: list[str] = field(default_factory=list)
    helpful_tips: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


# Each step is: (title, description, documents, hours, priority)
ACTION_PLANS = {
    NoticeType.SHOW_CAUSE_114: {
        "summary": "Show Cause Notice u/s 114(3) - You must explain why no proceedings should be initiated",
        "requires_professional": True,
        "requires_payment": False,
        "steps": [
            ("Read the notice carefully",
             "Understand exactly what FBR is asking. Note the sections cited and the specific allegation.",
             ["Notice copy", "Highlighter"],
             0.5,
             "critical"),
            ("Gather all relevant documents",
             "Collect invoices, bank statements, return copies, and any document supporting your position.",
             ["Tax returns", "Bank statements", "Invoices/receipts", "Books of accounts"],
             2.0,
             "critical"),
            ("Draft written response/explanation",
             "Write a detailed response addressing each point raised. Be factual and concise.",
             ["Drafting paper", "Word processor"],
             4.0,
             "critical"),
            ("Attach supporting evidence",
             "Attach copies (not originals) of all documents. Label each as Annex-A, B, C...",
             ["Evidence documents"],
             2.0,
             "high"),
            ("File response before deadline",
             "Submit to the office mentioned in notice. Get receipt/diary number as proof.",
             ["Response letter", "Copies of notice"],
             1.0,
             "critical"),
            ("Retain copies of everything",
             "Keep complete copies of your response and submission receipt.",
             [],
             0.5,
             "high"),
        ],
        "common_mistakes": [
            "Ignoring the notice (automatic adverse order)",
            "Submitting vague or emotional response",
            "Not attaching evidence",
            "Missing the deadline",
            "Filing at wrong office",
        ],
        "tips": [
            "Take professional tax consultant's help",
            "Use clear headings and numbered paragraphs",
            "Reference specific sections/laws in your favor",
            "Be polite and professional in tone",
            "If facts are complex, request extension in writing",
        ],
        "references": [
            "Income Tax Ordinance 2001, Section 114",
            "FBR Income Tax Rules 2002",
        ],
    },

    NoticeType.SHOW_CAUSE_122: {
        "summary": "Show Cause Notice u/s 122(1) - Serious allegation of concealment of income",
        "requires_professional": True,
        "requires_payment": False,
        "steps": [
            ("Understand the allegation",
             "Note what additional income/transaction FBR claims you concealed.",
             ["Notice copy"],
             0.5,
             "critical"),
            ("Compare with your return",
             "Review your filed return vs FBR's claim. Identify the difference and reason.",
             ["Filed return", "FBR notice", "Books of accounts"],
             2.0,
             "critical"),
            ("Engage tax lawyer/consultant",
             "Section 122 cases can lead to heavy penalties. Professional help is critical.",
             [],
             1.0,
             "critical"),
            ("Compile evidence",
             "Gather all evidence showing why the addition is incorrect or why you have proper explanation.",
             ["Bank statements", "Contracts", "Invoices", "Correspondence"],
             4.0,
             "critical"),
            ("Draft detailed reply",
             "Address each allegation point-by-point with legal references and evidence.",
             ["Drafting tools"],
             8.0,
             "critical"),
            ("Attend hearing if scheduled",
             "Appear personally or through representative on hearing date.",
             ["Authority letter", "ID proof"],
             4.0,
             "critical"),
        ],
        "common_mistakes": [
            "Treating as simple mistake",
            "Not hiring professional",
            "Admitting without verification",
            "Missing hearing date",
            "Not requesting documents from FBR (if needed)",
        ],
        "tips": [
            "Don't ignore - can lead to ex-parte order",
            "Request copies of FBR's evidence (if any)",
            "Cite Supreme Court / High Court judgments if applicable",
            "Maintain professional tone throughout",
        ],
        "references": [
            "Income Tax Ordinance 2001, Section 122",
            "Case law on Section 122 concealment",
        ],
    },

    NoticeType.ASSESSMENT_122: {
        "summary": "Final Assessment Order u/s 122(4) - Demand raised after hearing",
        "requires_professional": True,
        "requires_payment": True,
        "steps": [
            ("Review the order carefully",
             "Understand what tax, penalty, and default surcharge has been added.",
             ["Order copy"],
             1.0,
             "critical"),
            ("Check appeal time limit",
             "30 days from order date to file appeal to Commissioner (Appeals).",
             ["Calendar"],
             0.5,
             "critical"),
            ("Decide: Pay or Appeal",
             "If order is correct, pay within 30 days. If incorrect, file appeal.",
             [],
             1.0,
             "critical"),
            ("If appealing: File Form-31",
             "Submit appeal memorandum with required documents and fee.",
             ["Appeal memo", "Form-31", "Order copy", "Evidence"],
             4.0,
             "critical"),
            ("If paying: Use PSID/online",
             "Pay via FBR's e-payment system to get credit in your account.",
             ["Online banking"],
             0.5,
             "high"),
        ],
        "common_mistakes": [
            "Missing 30-day appeal deadline",
            "Paying without contesting if order is wrong",
            "Not keeping proof of payment",
        ],
        "tips": [
            "Even if you want to pay, file appeal to protect interest",
            "Alternative Dispute Resolution (ADR) is also an option",
            "Keep all receipts for tax credits",
        ],
        "references": [
            "Income Tax Ordinance 2001, Section 122(4)",
            "Section 127 - Appeals",
        ],
    },

    NoticeType.DEMAND_137: {
        "summary": "Demand Notice u/s 137 - Pay the demanded amount",
        "requires_professional": False,
        "requires_payment": True,
        "steps": [
            ("Verify the demand amount",
             "Cross-check with your filed return and payments made.",
             ["Return copy", "Payment receipts"],
             1.0,
             "critical"),
            ("Check the demand is valid",
             "Demand must be based on an order. Verify the parent order.",
             ["Order reference"],
             1.0,
             "high"),
            ("Pay the demand (if valid)",
             "Use FBR's e-payment system. Get PSID/CRN as proof.",
             ["Online banking"],
             0.5,
             "high"),
            ("File appeal (if demand wrong)",
             "30 days to appeal against the underlying order.",
             ["Appeal form"],
             3.0,
             "high"),
        ],
        "common_mistakes": [
            "Paying without verification",
            "Missing appeal deadline on parent order",
        ],
        "tips": [
            "Always demand copy of underlying order",
            "Pay partially if you disagree, then appeal for rest",
        ],
        "references": ["Income Tax Ordinance 2001, Section 137"],
    },

    NoticeType.PENALTY_182: {
        "summary": "Penalty Notice u/s 182 - Penalty for non-compliance",
        "requires_professional": True,
        "requires_payment": True,
        "steps": [
            ("Identify the default",
             "Understand which specific non-compliance triggered the penalty.",
             ["Notice copy"],
             0.5,
             "critical"),
            ("Gather mitigating evidence",
             "Collect evidence showing genuine reasons, if any.",
             ["Evidence"],
             2.0,
             "high"),
            ("File written response",
             "Explain circumstances and request waiver/reduction.",
             ["Response letter"],
             2.0,
             "critical"),
            ("Appeal if penalty is excessive",
             "Section 182 penalties are appealable.",
             ["Appeal memo"],
             3.0,
             "high"),
        ],
        "common_mistakes": [
            "Not responding at all",
            "Paying excessive penalty without appeal",
        ],
        "tips": [
            "FBR has discretion to waive penalty for good cause",
            "Courts have set guidelines on penalty quantum",
        ],
        "references": ["Income Tax Ordinance 2001, Section 182"],
    },

    NoticeType.AUDIT_214C: {
        "summary": "Audit Notice u/s 214C - You are selected for audit",
        "requires_professional": True,
        "requires_payment": False,
        "steps": [
            ("Read selection criteria",
             "Understand why you were selected (random, risk-based, etc.)",
             ["Notice copy"],
             0.5,
             "high"),
            ("Engage tax professional",
             "Audit requires thorough document review - hire experienced consultant.",
             [],
             1.0,
             "critical"),
            ("Compile all records",
             "Books of accounts, vouchers, bank statements, contracts, etc.",
             ["Books", "Vouchers", "Bank statements", "Returns"],
             8.0,
             "critical"),
            ("Attend audit proceedings",
             "Cooperate fully. Provide documents on time.",
             ["All records"],
             16.0,
             "critical"),
            ("Respond to audit observations",
             "Address each finding with proper evidence.",
             ["Response memo"],
             8.0,
             "high"),
        ],
        "common_mistakes": [
            "Not taking audit seriously",
            "Hiding documents from auditor",
            "Missing submission deadlines",
        ],
        "tips": [
            "Organize documents in logical order before audit",
            "Use audit checklist provided by FBR",
            "Take consultant's help to avoid errors",
        ],
        "references": ["Income Tax Ordinance 2001, Section 214C"],
    },
}


# Generic plan for types without specific templates
GENERIC_PLAN = {
    "summary": "FBR Notice - Standard response procedure applies",
    "requires_professional": False,
    "requires_payment": False,
    "steps": [
        ("Read and understand the notice",
         "Note all sections, dates, and demands mentioned.",
         ["Notice copy"],
         0.5,
         "critical"),
        ("Gather relevant documents",
         "Compile all documents related to the notice.",
         [],
         2.0,
         "high"),
        ("Verify the notice is genuine",
         "Cross-check with FBR records if possible.",
         ["IRIS access"],
         0.5,
         "high"),
        ("Consult tax professional",
         "For complex notices, professional help is recommended.",
         [],
         1.0,
         "medium"),
        ("Draft response",
         "Write clear, factual response with evidence.",
         [],
         3.0,
         "high"),
        ("File response before deadline",
         "Submit with proper receipt.",
         ["Response letter", "Copies"],
         0.5,
         "critical"),
    ],
    "common_mistakes": [
        "Ignoring the notice",
        "Missing the deadline",
        "Not keeping copies",
    ],
    "tips": [
        "Always respond within the timeframe",
        "Take professional help if amount is significant",
    ],
    "references": ["Income Tax Ordinance 2001"],
}


class ActionPlanGenerator:
    """Generates action plans for notices."""

    @staticmethod
    def generate(notice_type: NoticeType) -> ActionPlan:
        """Generate action plan for given notice type."""
        template = ACTION_PLANS.get(notice_type, GENERIC_PLAN)

        # Build steps
        steps = []
        total_hours = 0.0
        for i, (title, desc, docs, hours, priority) in enumerate(template["steps"], 1):
            steps.append(ActionStep(
                step_number=i,
                title=title,
                description=desc,
                documents_needed=docs,
                estimated_hours=hours,
                priority=priority,
            ))
            total_hours += hours

        return ActionPlan(
            notice_type=notice_type.value,
            summary=template["summary"],
            total_steps=len(steps),
            estimated_total_hours=round(total_hours, 1),
            requires_professional_help=template["requires_professional"],
            requires_payment=template["requires_payment"],
            steps=steps,
            common_mistakes=template["common_mistakes"],
            helpful_tips=template["tips"],
            references=template["references"],
        )

    @staticmethod
    def format_plan(plan: ActionPlan) -> str:
        """Format action plan as human-readable string."""
        lines = [
            f"=== Action Plan ===",
            f"Notice Type: {plan.notice_type}",
            f"",
            f"Summary: {plan.summary}",
            f"",
            f"Total Steps: {plan.total_steps}",
            f"Estimated Time: {plan.estimated_total_hours} hours",
            f"Professional Help Needed: {'Yes' if plan.requires_professional_help else 'No'}",
            f"Payment Required: {'Yes' if plan.requires_payment else 'No'}",
            f"",
            f"--- Step-by-Step Action Plan ---",
        ]

        for step in plan.steps:
            priority_icon = {
                "critical": "[!]",
                "high": "[H]",
                "medium": "[M]",
                "low": "[L]",
            }.get(step.priority, "[?]")

            lines.append(f"\n{priority_icon} Step {step.step_number}: {step.title}")
            lines.append(f"  {step.description}")
            lines.append(f"  Estimated time: {step.estimated_hours} hours")
            if step.documents_needed:
                lines.append(f"  Documents needed: {', '.join(step.documents_needed)}")

        lines.append(f"\n--- Common Mistakes to Avoid ---")
        for mistake in plan.common_mistakes:
            lines.append(f"  ✗ {mistake}")

        lines.append(f"\n--- Helpful Tips ---")
        for tip in plan.helpful_tips:
            lines.append(f"  💡 {tip}")

        lines.append(f"\n--- Legal References ---")
        for ref in plan.references:
            lines.append(f"  📄 {ref}")

        return "\n".join(lines)
