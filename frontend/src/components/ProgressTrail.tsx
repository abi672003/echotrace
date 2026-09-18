import { motion, AnimatePresence } from "framer-motion";
import type { ProgressEvent } from "../api";

const STAGES: { key: ProgressEvent["stage"]; label: string }[] = [
  { key: "searching", label: "Searching the live web" },
  { key: "scoring", label: "Running the detector" },
  { key: "aggregating", label: "Combining evidence" },
];

interface Props {
  current: ProgressEvent | null;
}

/** Renders the SSE investigate stream's stage sequence as a live-updating
 * trail, so the multi-second live-search+detect pipeline reads as
 * progress, not a dead spinner. */
export default function ProgressTrail({ current }: Props) {
  if (!current) return null;
  const currentIndex = STAGES.findIndex((s) => s.key === current.stage);

  return (
    <div className="progress-trail typewriter">
      {STAGES.map((stage, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "pending";
        return (
          <div key={stage.key} className={`progress-step progress-step-${state}`}>
            <motion.span
              className="progress-dot"
              animate={state === "active" ? { scale: [1, 1.3, 1] } : {}}
              transition={{ duration: 1.1, repeat: state === "active" ? Infinity : 0 }}
            />
            <span>{stage.label}</span>
          </div>
        );
      })}
      <AnimatePresence mode="wait">
        <motion.p
          key={current.message}
          className="progress-message mono"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          {current.message}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}
