import { NumbersTable } from "@/components/numbers/NumbersTable";

export default function FreeNumbersPage() {
  return (
    <div className="numbers-page">
      <NumbersTable kind="free" />
    </div>
  );
}
