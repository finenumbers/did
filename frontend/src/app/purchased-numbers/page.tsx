import { NumbersTable } from "@/components/numbers/NumbersTable";

export default function PurchasedNumbersPage() {
  return (
    <div className="numbers-page">
      <NumbersTable kind="purchased" />
    </div>
  );
}
