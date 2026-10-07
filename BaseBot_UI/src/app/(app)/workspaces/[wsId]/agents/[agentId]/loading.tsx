import { Skeleton } from "@/components/ui/skeleton";

export default function AgentLoading() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading agent" className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <Skeleton width={200} height={28} />
        <Skeleton width={320} height={16} />
      </div>
      <Skeleton variant="card" height={220} />
    </div>
  );
}
