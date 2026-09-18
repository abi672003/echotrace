import { motion } from "framer-motion";

interface Props {
  modelAvailable: boolean;
  aggregatedScore?: number;
  singleInstanceScore?: number;
}

const THRESHOLD = 0.5;

export default function VerdictStamp({ modelAvailable, aggregatedScore, singleInstanceScore }: Props) {
  if (!modelAvailable) {
    return (
      <div className="stamp stamp-pending">
        <span className="stamp-title typewriter">EVIDENCE PENDING</span>
        <span className="stamp-sub">detector checkpoint not yet loaded</span>
      </div>
    );
  }

  const flagged = (aggregatedScore ?? 0) >= THRESHOLD;
  const singleFlagged = (singleInstanceScore ?? 0) >= THRESHOLD;
  const aggregationChangedVerdict = flagged !== singleFlagged;

  return (
    <motion.div
      className={`stamp ${flagged ? "stamp-flag" : "stamp-clear"}`}
      initial={{ opacity: 0, scale: 2.2, rotate: -22 }}
      animate={{ opacity: 1, scale: 1, rotate: -2 }}
      transition={{ duration: 0.45, ease: [0.2, 0.9, 0.3, 1] }}
    >
      <span className="stamp-title typewriter">
        {flagged ? "AI-REWORDED COPY" : "INDEPENDENT REPORTING"}
      </span>
      <span className="stamp-sub mono">
        aggregated {(100 * (aggregatedScore ?? 0)).toFixed(0)}% · single-instance{" "}
        {(100 * (singleInstanceScore ?? 0)).toFixed(0)}%
        {aggregationChangedVerdict ? " · aggregation changed the verdict" : ""}
      </span>
    </motion.div>
  );
}
