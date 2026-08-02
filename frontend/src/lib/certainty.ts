import type { FieldVerification } from "@/lib/types/api";

export function certaintyTitle(v?: string): string {
  switch (v) {
    case "documentation_verified":
      return "Подтверждено документацией провайдера";
    case "example_confirmed":
      return "Подтверждено только примером в документации провайдера";
    case "derived":
      return "Вычислено системой, не напрямую из docs";
    case "unresolved":
    case "missing":
      return "Нет подтверждённого значения в документации/данных";
    default:
      return "Неопределённая достоверность";
  }
}

export function isUncertain(v?: string): boolean {
  return v === "example_confirmed" || v === "derived" || v === "unresolved" || v === "missing";
}

export function displayValue(
  value: string | number | boolean | null | undefined,
  verification?: FieldVerification | string,
): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (verification === "unresolved" || verification === "missing") {
    return "—";
  }
  if (typeof value === "boolean") return value ? "да" : "нет";
  return String(value);
}
