/**
 * Shared rich-text renderer for LLM / deterministic-tool output.
 *
 * Converts a plain-text answer into React nodes: **bold**, *italic*,
 * `code`, [links](url), "- " / numbered bullets, markdown tables
 * (| a | b | rows), and "---" horizontal rules. Everything else is
 * escaped — we never trust raw HTML from model output.
 */

import type { ReactNode } from "react";

function renderInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re =
    /\*\*([^*]+)\*\*|\*([^*\n]+)\*|`([^`\n]+)`|\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const key = `${keyBase}-i${i}`;
    if (m[1] !== undefined) {
      nodes.push(
        <strong key={key} className="rt__b">
          {m[1]}
        </strong>,
      );
    } else if (m[2] !== undefined) {
      nodes.push(
        <em key={key} className="rt__i">
          {m[2]}
        </em>,
      );
    } else if (m[3] !== undefined) {
      nodes.push(
        <code key={key} className="rt__code">
          {m[3]}
        </code>,
      );
    } else if (m[4] !== undefined && m[5] !== undefined) {
      nodes.push(
        <a key={key} className="rt__link" href={m[5]} target="_blank" rel="noreferrer noopener">
          {m[4]}
        </a>,
      );
    }
    last = m.index + m[0].length;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/** Parse consecutive "| a | b |" lines into (header, rows), skipping the
 * |---|---| separator row. */
function parseTable(rows: string[]): { header: string[]; body: string[][] } | null {
  if (rows.length === 0) return null;
  const cells = (r: string) =>
    r
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());
  const header = cells(rows[0]);
  if (header.length === 0) return null;
  const body = rows
    .slice(1)
    .filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(r))
    .map(cells);
  return { header, body };
}

/**
 * Block-level renderer: paragraphs, bullets, markdown tables and
 * horizontal rules — ChatGPT-style, never showing literal markdown
 * characters (pipes, asterisks, dashes rules).
 */
export function renderBlocks(text: string): ReactNode[] {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let para: string[] = [];
  let bullets: { text: string; num: number | null }[] = [];
  let tableLines: string[] = [];
  let k = 0;

  const flushPara = () => {
    if (para.length > 0) {
      out.push(<p key={`p-${k++}`}>{renderInline(para.join(" "), `p${k}`)}</p>);
      para = [];
    }
  };
  const flushBullets = () => {
    if (bullets.length > 0) {
      const first = bullets[0];
      if (first.num !== null) {
        out.push(
          <ol key={`ol-${k++}`}>
            {bullets.map((b, i) => (
              <li key={`li-${i}`}>{renderInline(b.text, `ol${k}-${i}`)}</li>
            ))}
          </ol>,
        );
      } else {
        out.push(
          <ul key={`ul-${k++}`}>
            {bullets.map((b, i) => (
              <li key={`li-${i}`}>{renderInline(b.text, `ul${k}-${i}`)}</li>
            ))}
          </ul>,
        );
      }
      bullets = [];
    }
  };
  const flushTable = () => {
    if (tableLines.length > 0) {
      const t = parseTable(tableLines);
      if (t) {
        out.push(
          <div key={`tw-${k++}`} className="rt__table-wrap">
            <table className="rt__table">
              <thead>
                <tr>
                  {t.header.map((h, i) => (
                    <th key={`th-${i}`}>{renderInline(h, `th${k}-${i}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {t.body.map((row, ri) => (
                  <tr key={`tr-${ri}`}>
                    {row.map((c, ci) => (
                      <td key={`td-${ci}`}>{renderInline(c, `td${k}-${ri}-${ci}`)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        );
      } else {
        // Not parseable as a table — fall back to paragraphs.
        for (const l of tableLines) para.push(l.replace(/^\s*\|/, "").trim());
      }
      tableLines = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const bullet = line.match(/^\s*[-•*]\s+(.*)$/);
    const numbered = line.match(/^\s*(\d{1,2})[.)]\s+(.*)$/);
    if (/^\s*\|.*\|?\s*$/.test(line) && line.includes("|")) {
      flushPara();
      flushBullets();
      tableLines.push(line);
    } else if (/^\s*---+\s*$/.test(line)) {
      flushPara();
      flushBullets();
      flushTable();
      out.push(<hr key={`hr-${k++}`} className="rt__hr" />);
    } else if (bullet) {
      flushTable();
      flushPara();
      const prevNum = bullets.length > 0 ? bullets[bullets.length - 1].num : null;
      if (prevNum !== null) flushBullets();
      bullets.push({ text: bullet[1], num: null });
    } else if (numbered) {
      flushTable();
      flushPara();
      const prevNum = bullets.length > 0 ? bullets[bullets.length - 1].num : null;
      if (prevNum === null) flushBullets();
      bullets.push({ text: numbered[2], num: Number(numbered[1]) });
    } else if (line.trim() === "") {
      flushPara();
      flushBullets();
      flushTable();
    } else {
      flushTable();
      flushBullets();
      para.push(line.trim());
    }
  }
  flushPara();
  flushBullets();
  flushTable();
  return out;
}

/** Convenience: render a whole answer in one call. */
export function renderRich(text: string): ReactNode[] {
  return renderBlocks(text);
}
