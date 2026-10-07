import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading page"
      className="flex flex-col gap-6"
    >
      <Skeleton width={220} height={28} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} variant="card" />
        ))}
      </div>
      <Skeleton variant="card" height={180} />
    </div>
  );
}
