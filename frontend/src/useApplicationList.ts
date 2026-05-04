import { useCallback, useEffect, useRef, useState } from "react";
import { listApplications } from "./api";
import type { Application } from "./types";

type UseApplicationListOptions = {
  statuses: string[];
  limit?: number;
  pollMs?: number | null;
  hiddenPollMs?: number | null;
  enabled?: boolean;
};

export function useApplicationList({
  statuses,
  limit,
  pollMs = null,
  hiddenPollMs = null,
  enabled = true,
}: UseApplicationListOptions) {
  const [apps, setApps] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const timeoutRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const statusKey = statuses.join(",");

  const clearTimer = useCallback(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      clearTimer();
      inFlightRef.current = false;
      setApps([]);
      setError(null);
      return;
    }

    let cancelled = false;
    const currentStatuses = statusKey ? statusKey.split(",") : [];

    const nextPollMs = () => (document.hidden ? hiddenPollMs : pollMs);

    const scheduleNext = () => {
      clearTimer();
      const delay = nextPollMs();
      if (!delay || delay <= 0) return;
      timeoutRef.current = window.setTimeout(() => {
        void load();
      }, delay);
    };

    const load = async () => {
      if (cancelled || inFlightRef.current) return;
      inFlightRef.current = true;
      const requestId = ++requestIdRef.current;
      try {
        const items = await listApplications({ statuses: currentStatuses, limit });
        if (!cancelled && requestId === requestIdRef.current) {
          setApps(items);
          setError(null);
        }
      } catch (err: unknown) {
        if (!cancelled && requestId === requestIdRef.current) {
          setError(err instanceof Error ? err.message : "Unable to load applications");
        }
      } finally {
        inFlightRef.current = false;
        if (!cancelled) scheduleNext();
      }
    };

    const refreshNow = () => {
      clearTimer();
      void load();
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        scheduleNext();
        return;
      }
      refreshNow();
    };

    const handleFocus = () => {
      if (document.hidden) return;
      refreshNow();
    };

    void load();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleFocus);

    return () => {
      cancelled = true;
      requestIdRef.current += 1;
      inFlightRef.current = false;
      clearTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleFocus);
    };
  }, [clearTimer, enabled, hiddenPollMs, limit, pollMs, statusKey]);

  const reload = useCallback(() => {
    const currentStatuses = statusKey ? statusKey.split(",") : [];
    requestIdRef.current += 1;
    clearTimer();
    inFlightRef.current = false;
    setError(null);
    return listApplications({ statuses: currentStatuses, limit })
      .then((items) => {
        setApps(items);
        return items;
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : "Unable to load applications";
        setError(message);
        throw err;
      });
  }, [clearTimer, limit, statusKey]);

  return { apps, error, reload, setApps };
}
