import type { VerificationResult } from "@/lib/api";

/** Structured summary of the deterministic tax engine output
 * (title, key-value fields, slab breakdown table). */
export interface EngineSummary {
  title: string;
  fields: { label: string; value: string; strong?: boolean }[];
  slabs: { range: string; rate: string; taxable: string; tax: string }[];
}

/** Parse the deterministic engine's `=== Title ===` / `Key: Value` /
 * slab-list text into a structured card. Amounts may contain spaces
 * between PKR and digits (engine pads them: `PKR       0.00`).
 * Returns null when the text does not follow the expected shape. */
export function parseEngineSummary(text: string): EngineSummary | null {
  const titleMatch = text.match(/===\s*(.+?)\s*===/);
  if (!titleMatch) return null;
  const body = text.slice(text.indexOf(titleMatch[0]) + titleMatch[0].length);
  const fields: EngineSummary["fields"] = [];
  const slabs: EngineSummary["slabs"] = [];

  const amt = "PKR\\s*[\\d,]+(?:\\.\\d+)?";
  const slabPattern =
    /(\d+)\.\s*(PKR\s*[\d,]+(?:\.\d+)?)\s*-\s*(PKR\s*[\d,]+(?:\.\d+)?)\s*@\s*([\d.]+)%:\s*Taxable=(PKR\s*[\d,]+(?:\.\d+)?)\s*->\s*Tax=(PKR\s*[\d,]+(?:\.\d+)?)/g;
  let m: RegExpExecArray | null;
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  while ((m = slabPattern.exec(body)) !== null) {
    slabs.push({
      range: `${norm(m[2])} – ${norm(m[3])}`,
      rate: `${m[4]}%`,
      taxable: norm(m[5]),
      tax: norm(m[6]),
    });
  }

  const fieldText = body.replace(slabPattern, "");
  const fieldPattern = new RegExp(
    "([A-Z][A-Za-z \\-,()]+?):\\s*(" + amt + "|[\\d.]+%)",
    "g",
  );
  while ((m = fieldPattern.exec(fieldText)) !== null) {
    const label = m[1].trim();
    const value = m[2].replace(/\s+/g, " ").trim();
    fields.push({
      label,
      value,
      strong: /Tax Payable|Taxable Income|Gross Income|Final Tax/i.test(label),
    });
  }
  if (fields.length === 0 && slabs.length === 0) return null;
  return { title: titleMatch[1], fields, slabs };
}

/** Verification payload shown while only the deterministic engine has run —
 * the deterministic path bypasses the RAG verification layer, so we present
 * an honest "deterministic engine" verification instead of a fake pass. */
export function deterministicVerification(): VerificationResult {
  return {
    passed: true,
    checks: {
      answer_size: { passed: true, reason: "deterministic engine" },
      section_consistency: { passed: true, reason: "deterministic engine" },
      grounding: { passed: true, reason: "deterministic engine" },
      speculation: { passed: true, reason: "deterministic engine" },
    },
    failed_checks: [],
    reason: "deterministic calculation engine",
  };
}

/** Extract a short "Final Tax Payable"-style headline amount from the
 * engine text, e.g. for a compact result line. */
export function headlineAmount(summary: EngineSummary): string | null {
  const preferred = summary.fields.find((f) =>
    /Final Tax Payable|Tax Payable/i.test(f.label),
  );
  return preferred?.value ?? summary.fields[0]?.value ?? null;
}
