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
    <div className={`stamp ${flagged ? "stamp-flag" : "stamp-clear"}`}>
      <span className="stamp-title typewriter">
        {flagged ? "AI-REWORDED COPY" : "INDEPENDENT REPORTING"}
      </span>
      <span className="stamp-sub mono">
        aggregated {(100 * (aggregatedScore ?? 0)).toFixed(0)}% · single-instance{" "}
        {(100 * (singleInstanceScore ?? 0)).toFixed(0)}%
        {aggregationChangedVerdict ? " · aggregation changed the verdict" : ""}
      </span>
    </div>
  );
}
