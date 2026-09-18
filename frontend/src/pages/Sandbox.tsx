import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "../api";
import type { SampleArticle } from "../api";

/**
 * Detector Sandbox: real M-DAIGT test-set samples with a genuine
 * human/machine label, blind until the detector runs. Live web articles
 * (the main Investigate flow) carry no ground-truth label of their own —
 * this is the only place the detector can be checked against a known
 * answer. Ports the Streamlit app's "Detector Test" tab.
 */
export default function Sandbox() {
  const [samples, setSamples] = useState<SampleArticle[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [result, setResult] = useState<{ score: number; label?: string } | null>(null);
  const [modelUnavailable, setModelUnavailable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function fetchSamples() {
    api
      .fetchMdaigtSamples(15, "test")
      .then(setSamples)
      .catch((e) => setError(e instanceof api.ApiError ? e.message : "Could not load samples."));
  }

  function loadSamples() {
    setError(null);
    setResult(null);
    setSelectedId(null);
    fetchSamples();
  }

  useEffect(fetchSamples, []);

  async function runDetector() {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const article = await api.fetchArticle(selectedId);
      const detected = await api.detect(article.text);
      if (!detected.model_available) {
        setModelUnavailable(true);
        return;
      }
      const trueLabel = samples.find((s) => s.id === selectedId)?.label;
      setResult({ score: detected.score ?? 0, label: trueLabel });
    } catch (e) {
      setError(e instanceof api.ApiError ? e.message : "Detection failed.");
    } finally {
      setLoading(false);
    }
  }

  const predictedLabel = result ? (result.score >= 0.5 ? "machine" : "human") : null;
  const correct = result && result.label ? predictedLabel === result.label : null;

  return (
    <div className="sandbox-page">
      <h2 className="typewriter">DETECTOR SANDBOX</h2>
      <p className="sandbox-copy">
        Real M-DAIGT test-set samples — a mix of genuine human-written and genuine AI-generated news
        text, held out during training. The label is revealed only after the detector runs, so this is
        a fair, blind check of the single-instance detector (no retrieval/aggregation here).
      </p>

      {modelUnavailable && (
        <p className="empty-state error">
          Detection scores unavailable — the fine-tuned RoBERTa checkpoint wasn't found on this
          deployment.
        </p>
      )}
      {error && <p className="empty-state error">{error}</p>}

      <div className="sandbox-controls">
        <button className="btn-secondary" onClick={loadSamples}>
          Get new samples
        </button>
      </div>

      <div className="sandbox-grid">
        {samples.map((s) => (
          <button
            key={s.id}
            className={`sandbox-sample ${selectedId === s.id ? "sandbox-sample-active" : ""}`}
            onClick={() => {
              setSelectedId(s.id);
              setResult(null);
            }}
          >
            {s.preview.slice(0, 100)}…
          </button>
        ))}
      </div>

      <button className="btn-primary" onClick={runDetector} disabled={!selectedId || loading}>
        {loading ? "Running detector…" : "Run detector"}
      </button>

      <AnimatePresence>
        {result && (
          <motion.div
            className={`sandbox-result ${correct === false ? "sandbox-result-wrong" : ""}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <p className="mono">
              detector score: <strong>{(result.score * 100).toFixed(1)}%</strong> machine-generated →
              predicted <strong>{predictedLabel}</strong>
            </p>
            {result.label && (
              <p className="mono">
                true label: <strong>{result.label}</strong> — {correct ? "correct ✓" : "incorrect ✗"}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
