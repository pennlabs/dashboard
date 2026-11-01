import { useQuery } from "@tanstack/react-query"

import * as api from "../api"

/**
 * No `refetchInterval`, unlike the live pages: a window is a fixed stretch of
 * history, so asking again would return the same answer. `retry: false` because
 * a failure here means the window was refused or AWS access is missing, and
 * neither is fixed by trying again a second later.
 */
export const useDatabaseInsights = (start: string, end: string) =>
  useQuery({
    queryKey: ["database-insights", start, end],
    queryFn: () => api.getDatabaseInsights(start, end),
    retry: false,
    staleTime: Infinity,
    enabled: Boolean(start && end),
  })
