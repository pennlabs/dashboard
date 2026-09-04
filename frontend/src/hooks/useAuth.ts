import { useQuery } from "@tanstack/react-query"

import * as api from "../api"

/**
 * Who is signed in, and may they use the dashboard?
 *
 * No `refetchInterval`: sign-in state only changes via a full page navigation
 * through Platform, which remounts the app anyway. `retry: false` because a
 * failure here means the API is unreachable -- retrying just delays the error.
 */
export const useAuth = () =>
  useQuery({
    queryKey: ["me"],
    queryFn: api.getMe,
    retry: false,
    staleTime: Infinity,
  })
