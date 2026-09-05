import type { Evidence } from "../api";

interface Props {
  targetPreview: string;
  targetId: string;
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

function shortLabel(id: string): string {
  // ids look like "7_288600912-garden-city-telegram-Mar-21-1974-p-1.jpg"
  const parts = id.split("-");
  const namePart = id.split("_")[1] ?? id;
  const words = namePart.split("-").filter((w) => isNaN(Number(w)));
  const name = words.slice(0, 3).join(" ");
  return name || parts[0];
}

function threadColor(similarity: number): string {
  if (similarity >= 0.85) return "var(--thread-red)";
  if (similarity >= 0.6) return "var(--thread-amber)";
  return "rgba(217, 201, 138, 0.35)";
}

export default function CaseBoard({ targetPreview, targetId, evidence, modelAvailable }: Props) {
  const count = evidence.length;

  return (
    <div className="board">
      <svg className="board-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
        {evidence.map((e, i) => {
          const pos = positionFor(i, count);
          return (
            <line
              key={e.id}
              x1={CENTER.x}
              y1={CENTER.y}
              x2={pos.x}
              y2={pos.y}
              stroke={threadColor(e.similarity)}
              strokeWidth={0.35}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      <div className="pin-card target-card" style={{ left: `${CENTER.x}%`, top: `${CENTER.y}%` }}>
        <div className="pin" />
        <div className="card-label typewriter">TARGET</div>
        <div className="card-id mono">{shortLabel(targetId)}</div>
        <p className="card-preview">{targetPreview}</p>
      </div>

      {evidence.map((e, i) => {
        const pos = positionFor(i, count);
        return (
          <div
            key={e.id}
            className="pin-card duplicate-card"
            style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
          >
            <div className="pin pin-small" />
            <div className="card-id mono">{shortLabel(e.id)}</div>
            <div className="card-stat">
              <span className="stat-label">similarity</span>
              <span className="stat-value">{(e.similarity * 100).toFixed(0)}%</span>
            </div>
            <div className="card-stat">
              <span className="stat-label">AI-text score</span>
              <span className="stat-value">
                {modelAvailable && e.score !== null ? `${(e.score * 100).toFixed(0)}%` : "pending"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
