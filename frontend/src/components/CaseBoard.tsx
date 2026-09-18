import { motion } from "framer-motion";
import type { Evidence } from "../api";

interface Props {
  targetPreview: string;
  targetLabel: string;
  evidence: Evidence[];
  modelAvailable: boolean;
}

// Layout is done entirely in a 0-100 percentage space shared by the SVG
// (viewBox="0 0 100 100", preserveAspectRatio="none") and the card divs, so
// connection lines line up with card centers regardless of the board's
// actual pixel aspect ratio.
const CENTER = { x: 50, y: 50 };
const RX = 40;
const RY = 36;

function positionFor(index: number, count: number) {
  const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
  return {
    x: CENTER.x + RX * Math.cos(angle),
    y: CENTER.y + RY * Math.sin(angle),
  };
}

function labelFor(e: Evidence): string {
  if (e.title) return e.title.slice(0, 60);
  if (e.domain) return e.domain;
  try {
    return new URL(e.id).hostname;
  } catch {
    return e.id.slice(0, 40);
  }
}

function threadColor(similarity: number): string {
  if (similarity >= 0.85) return "var(--thread-red)";
  if (similarity >= 0.6) return "var(--thread-amber)";
  return "rgba(217, 201, 138, 0.35)";
}

export default function CaseBoard({ targetPreview, targetLabel, evidence, modelAvailable }: Props) {
  const count = evidence.length;

  return (
    <div className="board">
      <svg className="board-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
        {evidence.map((e, i) => {
          const pos = positionFor(i, count);
          return (
            <motion.line
              key={e.id}
              x1={CENTER.x}
              y1={CENTER.y}
              initial={{ x2: CENTER.x, y2: CENTER.y, opacity: 0 }}
              animate={{ x2: pos.x, y2: pos.y, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.15 + i * 0.08, ease: "easeOut" }}
              stroke={threadColor(e.similarity)}
              strokeWidth={0.35}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      <motion.div
        className="pin-card target-card"
        style={{ left: `${CENTER.x}%`, top: `${CENTER.y}%` }}
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
      >
        <div className="pin" />
        <div className="card-label typewriter">TARGET</div>
        <div className="card-id mono">{targetLabel}</div>
        <p className="card-preview">{targetPreview}</p>
      </motion.div>

      {evidence.map((e, i) => {
        const pos = positionFor(i, count);
        return (
          <motion.a
            key={e.id}
            className="pin-card duplicate-card"
            href={e.id.startsWith("http") ? e.id : undefined}
            target="_blank"
            rel="noreferrer"
            style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.35, delay: 0.2 + i * 0.08, type: "spring", stiffness: 260, damping: 20 }}
            whileHover={{ scale: 1.05 }}
          >
            <div className="pin pin-small" />
            <div className="card-id mono">{labelFor(e)}</div>
            <div className="card-stat">
              <span className="stat-label">similarity</span>
              <span className="stat-value">{(e.similarity * 100).toFixed(0)}%</span>
            </div>
            <div className="card-stat">
              <span className="stat-label">AI-text score</span>
              <span className="stat-value">
                {modelAvailable && e.score !== null ? `${((e.score ?? 0) * 100).toFixed(0)}%` : "pending"}
              </span>
            </div>
          </motion.a>
        );
      })}
    </div>
  );
}
