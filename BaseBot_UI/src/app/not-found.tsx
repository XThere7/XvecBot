import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh items-center justify-center px-5">
      <div className="w-full max-w-md text-center">
        <p className="font-mono text-xs text-tertiary">404</p>
        <h1 className="mt-2 text-2xl text-primary">Page not found</h1>
        <p className="mt-2 text-sm leading-5 text-secondary">
          That URL does not exist. Check the link, or go back to your dashboard.
        </p>
        <Button asChild variant="primary" className="mt-6">
          <Link href="/dashboard">Go to dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
