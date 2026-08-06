import { useState } from "react";
import { guessLogoUrl } from "../lib/logo";

export function CompanyLogo({ ticker, company, size = 32 }: { ticker: string; company: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const dimension = `${size}px`;

  if (failed) {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded-xl bg-black/[0.04] font-mono font-bold text-[#15171c] dark:bg-white/[0.06] dark:text-[#e7e8ea]"
        style={{ width: dimension, height: dimension, fontSize: size * 0.34 }}
      >
        {ticker.slice(0, 4)}
      </div>
    );
  }

  return (
    <img
      src={guessLogoUrl(company)}
      alt=""
      width={size}
      height={size}
      className="shrink-0 rounded-xl border border-black/[0.06] bg-white object-contain p-1 dark:border-white/[0.08]"
      style={{ width: dimension, height: dimension }}
      onError={() => setFailed(true)}
      loading="lazy"
    />
  );
}
