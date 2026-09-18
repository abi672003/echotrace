import { useState } from "react";
import { motion } from "framer-motion";
import * as api from "../api";
import type { InvestigateResult, ProgressEvent, Timespan } from "../api";
import VerdictStamp from "../components/VerdictStamp";
import CaseBoard from "../components/CaseBoard";
import ProgressTrail from "../components/ProgressTrail";
import Select from "../components/Select";

type Mode = "text" | "url";

export default function Investigate() {
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [k, setK] = useState("5");
  const [timespan, setTimespan] = useState<Timespan>("7d");

  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InvestigateResult | null>(null);
  const [targetPreview, setTargetPreview] = useState("");

  const canSubmit = mode === "text" ? text.trim().length > 40 : url.trim().length > 8;

  async function onInvestigate() {
    setLoading(true);
    setError(null);
    setResult(null);
    setProgress(null);
    setTargetPreview(mode === "text" ? text.slice(0, 220) : url);

    try {
      const args = mode === "text" ? { text, k: Number(k), timespan } : { url, k: Number(k), timespan };
      const res = await api.investigateStream(args, setProgress);
      setResult(res);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : "Investigation failed.");
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }

  const targetLabel = mode === "url" ? (() => {
    try {
      return new URL(url).hostname;
    } catch {
      return "TARGET";
    }
  })() : "PASTED TEXT";

  return (
    <div className="investigate-page">
      <motion.div
        className="investigate-form"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="mode-toggle">
          <button className={mode === "text" ? "mode-btn mode-btn-active" : "mode-btn"} onClick={() => setMode("text")}>
            Paste text
          </button>
          <button className={mode === "url" ? "mode-btn mode-btn-active" : "mode-btn"} onClick={() => setMode("url")}>
            Paste a URL
          </button>
        </div>

        {mode === "text" ? (
          <textarea
            className="investigate-textarea"
            placeholder="Paste the full article text you want to investigate…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
          />
        ) : (
          <input
            className="investigate-url-input"
            type="url"
            placeholder="https://example.com/news/story-headline"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        )}

        <div className="investigate-controls">
          <Select
            label="evidence count"
            value={k}
            onChange={setK}
            options={[
              { value: "3", label: "3 duplicates" },
              { value: "5", label: "5 duplicates" },
              { value: "10", label: "10 duplicates" },
            ]}
          />
          <Select
            label="search window"
            value={timespan}
            onChange={(v) => setTimespan(v as Timespan)}
            options={[
              { value: "24h", label: "Last 24 hours" },
              { value: "7d", label: "Last 7 days" },
              { value: "30d", label: "Last 30 days" },
            ]}
          />
          <button className="btn-primary" onClick={onInvestigate} disabled={!canSubmit || loading}>
            {loading ? "Investigating…" : "Investigate"}
          </button>
        </div>
      </motion.div>

      {loading && <ProgressTrail current={progress} />}
      {error && <p className="empty-state error">{error}</p>}

      {result && !loading && (
        <>
          <VerdictStamp
            modelAvailable={result.model_available}
            aggregatedScore={result.aggregated_score}
            singleInstanceScore={result.single_instance_score}
          />
          {!result.model_available && result.message && (
            <p className="empty-state">{result.message}</p>
          )}
          <CaseBoard
            targetLabel={targetLabel}
            targetPreview={targetPreview}
            evidence={result.evidence}
            modelAvailable={result.model_available}
          />
        </>
      )}

      {!result && !loading && !error && (
        <div className="empty-state typewriter">PASTE AN ARTICLE TO OPEN A CASE FILE</div>
      )}
    </div>
  );
}
