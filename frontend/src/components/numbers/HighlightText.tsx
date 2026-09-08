import type { HighlightSpan } from "@/components/numbers/prefixHighlight";

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function HighlightText({
  text,
  query,
}: {
  text: string;
  query?: string;
}) {
  const q = query?.trim();
  if (!q || text === "—") {
    return <>{text}</>;
  }

  const parts = text.split(new RegExp(`(${escapeRegExp(q)})`, "gi"));
  if (parts.length === 1) {
    return <>{text}</>;
  }

  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === q.toLowerCase() ? (
          <mark key={i} className="search-hit">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

export function HighlightRange({
  text,
  span,
}: {
  text: string;
  span: HighlightSpan | null;
}) {
  if (!span || text === "—" || span.start >= span.end) {
    return <>{text}</>;
  }
  const start = Math.max(0, span.start);
  const end = Math.min(text.length, span.end);
  if (start >= end) {
    return <>{text}</>;
  }
  return (
    <>
      {text.slice(0, start)}
      <mark className="search-hit">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  );
}
