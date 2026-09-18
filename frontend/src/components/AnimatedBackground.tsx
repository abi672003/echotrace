import { motion } from "framer-motion";

/**
 * Subtle, slow-drifting glow behind the cork-board texture (index.css's
 * `body` background). Pure decoration — pointer-events disabled, low
 * opacity, no reduced-motion violation risk since the drift is gentle and
 * `prefers-reduced-motion` disables it entirely via CSS below.
 */
export default function AnimatedBackground() {
  return (
    <div className="animated-bg" aria-hidden="true">
      <motion.div
        className="bg-glow bg-glow-amber"
        animate={{ x: [0, 60, -20, 0], y: [0, -40, 30, 0] }}
        transition={{ duration: 38, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="bg-glow bg-glow-red"
        animate={{ x: [0, -50, 40, 0], y: [0, 50, -30, 0] }}
        transition={{ duration: 46, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
