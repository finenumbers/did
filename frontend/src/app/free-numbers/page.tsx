import { NumbersTable } from "@/components/numbers/NumbersTable";

export default function FreeNumbersPage() {
  return (
    <>
      <h1>Свободные номера</h1>
      <NumbersTable kind="free" />
    </>
  );
}
