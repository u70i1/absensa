import { useEffect, useState } from "react";
import { formatDate } from "../utils/formatDate";

/**
 * Hook for live date and time
 *
 * @export
 * @returns {{ date: str; time: str; }}
 */
export function useLiveDate() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const time = now.toLocaleTimeString("en-US", {
    // change locale (e.g. id-ID)
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  const date = formatDate(now);

  return { date, time };
}
