import { useState } from "react";
import type { SourceItem } from "@/lib/api";
import { Tag } from "./Tag";

interface SourceCitationProps {
  source: SourceItem;
  index?: number;
}

export function SourceCitation({ source, index }: SourceCitationProps) {
  const [expanded, setExpanded] = useState(false);

  const hasExtra =
    source.page_start != null ||
    source.page_end != null ||
    source.section != null ||
    source.section_reference != null ||
    source.section_number != null ||
    source.law_tag != null ||
    source.source_sha256 != null ||
    source.exact_match ||
    source.multi_law_candidate;

  return (
    <li className="source">
      <button
        type="button"
        className="source__row"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        data-testid="source-citation"
      >
        <span className="source__idx">{index != null ? index + 1 : ""}</span>
        <span className="source__main">
          <span className="source__doc">{source.source}</span>
          {source.page != null ? <span className="source__page">p. {source.page}</span> : null}
        </span>
        <span className="source__score">{(source.score * 100).toFixed(0)}%</span>
        <span className="source__chevron" aria-hidden>
          {expanded ? "—" : "+"}
        </span>
      </button>

      {expanded && hasExtra ? (
        <div className="source__detail">
          {source.section ? (
            <div className="source__line">
              <span className="source__k">Section</span>
              <span className="source__v">{source.section}</span>
            </div>
          ) : null}
          {source.section_reference ? (
            <div className="source__line">
              <span className="source__k">Reference</span>
              <span className="source__v">{source.section_reference}</span>
            </div>
          ) : null}
          {source.section_number ? (
            <div className="source__line">
              <span className="source__k">No.</span>
              <span className="source__v">{source.section_number}</span>
            </div>
          ) : null}
          {source.law_tag ? (
            <div className="source__line">
              <span className="source__k">Law</span>
              <span className="source__v">{source.law_tag}</span>
            </div>
          ) : null}
          {source.page_start != null && source.page_end != null ? (
            <div className="source__line">
              <span className="source__k">Pages</span>
              <span className="source__v">{source.page_start}–{source.page_end}</span>
            </div>
          ) : null}
          {source.source_sha256 ? (
            <div className="source__line">
              <span className="source__k">SHA-256</span>
              <span className="source__v source__hash">{source.source_sha256}</span>
            </div>
          ) : null}
          <div className="source__line">
            <span className="source__k">Exact</span>
            <span className="source__v">{source.exact_match ? "Yes" : "No"}</span>
          </div>
          {source.multi_law_candidate ? (
            <div className="source__line">
              <span className="source__k">Multi-law</span>
              <span className="source__v">Candidate</span>
            </div>
          ) : null}
          <div className="source__line">
            <span className="source__k">Semantic</span>
            <span className="source__v">{source.semantic_score.toFixed(3)}</span>
          </div>
          <div className="source__line">
            <span className="source__k">BM25</span>
            <span className="source__v">{source.bm25_score.toFixed(3)}</span>
          </div>
          <div className="source__tags">
            {source.exact_match ? <Tag variant="ok">Exact</Tag> : null}
            {source.multi_law_candidate ? <Tag variant="accent">Multi-law</Tag> : null}
          </div>
        </div>
      ) : null}
    </li>
  );
}

interface SourceListProps {
  sources: SourceItem[];
  testId?: string;
}

export function SourceList({ sources, testId }: SourceListProps) {
  if (!sources || sources.length === 0) {
    return <p className="state__body-text">No sources were returned for this answer.</p>;
  }
  return (
    <ul className="sources" data-testid={testId}>
      {sources.map((s, idx) => (
        <SourceCitation key={s.chunk_id || `${s.source}-${idx}`} source={s} index={idx} />
      ))}
    </ul>
  );
}