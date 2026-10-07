import { Skeleton } from "@/components/ui/skeleton";

export default function WorkspaceLoading() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading workspace" className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <Skeleton width={240} height={28} />
        <Skeleton width={360} height={16} />
      </div>
      <Skeleton height={172} className="rounded-md" />
      <Skeleton variant="table" rows={4} />
    </div>
  );
}
