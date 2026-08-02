import { certaintyTitle, displayValue, isUncertain } from "@/lib/certainty";

export function CertaintyCell({
  value,
  verification,
}: {
  value: string | number | boolean | null | undefined;
  verification?: string;
}) {
  const text = displayValue(value, verification);
  if (!verification || verification === "documentation_verified") {
    return <span>{text}</span>;
  }
  const cls = isUncertain(verification) ? "certainty" : "";
  const unresolved = verification === "unresolved" || verification === "missing";
  return (
    <span
      className={`${cls}${unresolved ? " unresolved" : ""}`}
      title={certaintyTitle(verification)}
    >
      {text}
    </span>
  );
}

export function CertaintyLegend() {
  return (
    <div className="legend">
      Обычный текст — documentation_verified. Пунктир/подсказка — example_confirmed или
      derived. «—» — unresolved/missing. Не трактуйте example-confirmed как гарантированный факт.
    </div>
  );
}
