"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A long staleTime matters on a flaky connection — 60 s per the spec.
        staleTime: QUERY_STALE_TIME_MS,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          const status = (error as { status?: number }).status;
          // Never retry a definitive 4xx; always retry a transient 5xx/network.
          if (typeof status === "number" && status >= 400 && status < 500) {
            return false;
          }
          return failureCount < 2;
        },
      },
      mutations: { retry: false },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(makeQueryClient);

  return (
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      <Toaster />
    </QueryClientProvider>
  );
}