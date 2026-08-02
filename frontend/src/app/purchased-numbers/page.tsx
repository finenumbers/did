import { NumbersTable } from "@/components/numbers/NumbersTable";

export default function PurchasedNumbersPage() {
  return (
    <>
      <h1>Купленные номера</h1>
      <NumbersTable kind="purchased" />
    </>
  );
}
