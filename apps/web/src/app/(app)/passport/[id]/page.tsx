import { Suspense } from "react";
import PassportView from "./view";

export function generateStaticParams() {
  return [{ id: "P1" }, { id: "P2" }, { id: "P3" }];
}

async function Inner({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PassportView id={id} />;
}

export default function PassportPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-night" />}>
      <Inner params={params} />
    </Suspense>
  );
}
