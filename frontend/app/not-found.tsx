import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-5">
      <div className="max-w-md text-center">
        <p className="font-display text-6xl font-semibold text-pine/20">404</p>
        <h1 className="mt-2 font-display text-2xl font-semibold text-pine">
          Page not found
        </h1>
        <p className="mt-2 text-sm text-ink-muted">
          That link may be out of date, or the record may have been moved.
        </p>
        <div className="mt-6">
          <Link href="/dashboard">
            <Button>Back to dashboard</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
