// @ts-nocheck
"use client";

import { Button } from "@/components/ui/button";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export function LoadMoreStudiesButton() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const currentLimit = Number(searchParams?.get("k") ?? "10");
  const nextLimit = currentLimit + 10;

  return (
    <div className="flex justify-center pt-4 pb-2">
      <Button
        variant="outline"
        onClick={() => {
          if (!pathname) {
            return;
          }
          const params = new URLSearchParams(searchParams?.toString() ?? "");
          params.set("k", String(nextLimit));
          const queryString = params.toString();
          router.push(queryString ? `${pathname}?${queryString}` : pathname);
        }}
        className="min-w-32"
      >
        Load More
      </Button>
    </div>
  );
}
