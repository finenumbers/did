import { certaintyTitle, displayValue, isUncertain } from "@/lib/certainty";
import { HighlightText } from "@/components/numbers/HighlightText";

export function CertaintyCell({
  value,
  verification,
  highlight,
}: {
  value: string | number | boolean | null | undefined;
  verification?: string;
  highlight?: string;
}) {
  const text = displayValue(value, verification);
  const content = <HighlightText text={text} query={highlight} />;

  if (!verification || verification === "documentation_verified") {
    return <span>{content}</span>;
  }
  const cls = isUncertain(verification) ? "certainty" : "";
  const unresolved = verification === "unresolved" || verification === "missing";
  return (
    <span
      className={`${cls}${unresolved ? " unresolved" : ""}`}
      title={certaintyTitle(verification)}
    >
      {content}
    </span>
  );
}
