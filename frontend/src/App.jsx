import React, { useEffect, useRef, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const SESSION_ID = "s-" + Math.random().toString(36).slice(2, 12);
const LANGS = [
  ["auto", "Auto-detect"],
  ["en", "English"],
  ["hi", "हिन्दी"],
  ["or", "ଓଡ଼ିଆ"],
];
const SUGGESTED = [
  "Who is eligible for PM-KISAN?",
  "How many days of work can I get under MGNREGA?",
  "What documents are required for PMAY-G?",
];
const NEEDS = [
  ["farming", "Farming support"],
  ["housing", "Housing"],
  ["health", "Health coverage"],
  ["cooking_fuel", "Cooking fuel (LPG)"],
  ["employment", "Wage employment"],
];

async function api(path, options) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let msg = "Something went wrong. Please try again.";
    if (res.status === 429) msg = "Too many requests. Please wait a minute.";
    throw new Error(msg);
  }
  return res.json();
}

function SourceCard({ s }) {
  return (
    <div className="source">
      <span className="badge">{s.id}</span>
      <div>
        <strong>{s.document}</strong>
        <div className="muted">
          Page {s.page}
          {s.section ? ` · ${s.section}` : ""}
        </div>
        {s.source_url && (
          <a href={s.source_url} target="_blank" rel="noreferrer">
            Open official source ↗
          </a>
        )}
      </div>
    </div>
  );
}

function MessageBubble({ m, onAsk }) {
  return (
    <div className={`msg ${m.role}`}>
      <div className={`bubble ${m.status === "not_found" || m.status === "error" ? "warn" : ""}`}>
        {m.text}
      </div>
      {m.sources?.length > 0 && (
        <div className="sources">
          <div className="muted small">Sources</div>
          {m.sources.map((s) => (
            <SourceCard key={s.id} s={s} />
          ))}
        </div>
      )}
      {m.followUps?.length > 0 && (
        <div className="chips">
          {m.followUps.map((q) => (
            <button key={q} className="chip" onClick={() => onAsk(q)}>
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SuggestedQuestions({ onAsk }) {
  return (
    <div className="chips">
      {SUGGESTED.map((q) => (
        <button key={q} className="chip" onClick={() => onAsk(q)}>
          {q}
        </button>
      ))}
    </div>
  );
}

function LanguageSelector({ value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Answer language">
      {LANGS.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}

function SchemeCard({ s, onAsk }) {
  return (
    <div className="card">
      <span className="tag">{s.category}</span>
      <h3>{s.name}</h3>
      <p className="muted">{s.summary}</p>
      <button className="link" onClick={() => onAsk(`What is ${s.name}?`)}>
        Ask about this scheme →
      </button>
    </div>
  );
}

function ChatWindow({ messages, loading, onAsk }) {
  const end = useRef(null);
     useEffect(() => {
     end.current?.scrollIntoView({ behavior: "smooth" });
   }, [messages, loading]);
  return (
    <div className="chat">
      {messages.length === 0 && (
        <div className="empty">
          <p>Ask about eligibility, benefits, documents or how to apply.</p>
          <SuggestedQuestions onAsk={onAsk} />
        </div>
      )}
      {messages.map((m, i) => (
        <MessageBubble key={i} m={m} onAsk={onAsk} />
      ))}
      {loading && <div className="msg assistant"><div className="bubble muted">Searching documents…</div></div>}
      <div ref={end} />
    </div>
  );
}

function RecommendationForm() {
  const [needs, setNeeds] = useState([]);
  const [occupation, setOccupation] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const toggle = (n) => setNeeds((p) => (p.includes(n) ? p.filter((x) => x !== n) : [...p, n]));
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setResult(
        await api("/api/recommendations", {
          method: "POST",
          body: JSON.stringify({ needs, occupation: occupation || null }),
        })
      );
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="panel">
      <h2>Find schemes for you</h2>
      <form onSubmit={submit}>
        <div className="chips">
          {NEEDS.map(([v, l]) => (
            <label key={v} className={`chip check ${needs.includes(v) ? "on" : ""}`}>
              <input type="checkbox" checked={needs.includes(v)} onChange={() => toggle(v)} /> {l}
            </label>
          ))}
        </div>
        <select value={occupation} onChange={(e) => setOccupation(e.target.value)}>
          <option value="">Occupation (optional)</option>
          <option value="farmer">Farmer</option>
          <option value="daily_wage">Daily wage worker</option>
          <option value="homemaker">Homemaker</option>
          <option value="unemployed">Looking for work</option>
        </select>
        <button className="primary" type="submit">
          Show suggestions
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className="results">
          {result.results.length === 0 && <p className="muted">Pick at least one need or occupation.</p>}
          {result.results.map((r) => (
            <div className="card" key={r.scheme_id}>
              <h3>{r.name}</h3>
              <p className="muted">Suggested because {r.reasons.join(" and ")}.</p>
              <a href={r.official_url} target="_blank" rel="noreferrer">
                Official website ↗
              </a>
            </div>
          ))}
          <p className="muted small">{result.disclaimer}</p>
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [lang, setLang] = useState("auto");
  const [loading, setLoading] = useState(false);
  const [schemes, setSchemes] = useState([]);
  const [category, setCategory] = useState("All");
  const [tab, setTab] = useState("chat");

  useEffect(() => {
    api("/api/schemes").then(setSchemes).catch(() => {});
  }, []);

  const ask = async (q) => {
    const question = (q ?? input).trim();
    if (!question || loading) return;
    setTab("chat");
    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }]);
    setLoading(true);
    try {
      const r = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          question,
          session_id: SESSION_ID,
          language: lang === "auto" ? null : lang,
        }),
      });
      setMessages((m) => [
        ...m,
        { role: "assistant", text: r.answer, sources: r.sources, followUps: r.follow_ups, status: r.status },
      ]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", text: err.message, status: "error" }]);
    } finally {
      setLoading(false);
    }
  };

  const categories = ["All", ...new Set(schemes.map((s) => s.category))];
  const shown = schemes.filter((s) => category === "All" || s.category === category);

  return (
    <div className="app">
      <header>
        <div>
          <h1>🌾 Rural Scheme Advisor</h1>
          <p className="muted">Understand government schemes using official documents.</p>
        </div>
        <LanguageSelector value={lang} onChange={setLang} />
      </header>

      <nav className="tabs">
        <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
          Ask
        </button>
        <button className={tab === "explore" ? "active" : ""} onClick={() => setTab("explore")}>
          Explore schemes
        </button>
        <button className={tab === "recommend" ? "active" : ""} onClick={() => setTab("recommend")}>
          Find for me
        </button>
      </nav>

      {tab === "chat" && (
        <>
          <ChatWindow messages={messages} loading={loading} onAsk={ask} />
          <form
            className="inputbar"
            onSubmit={(e) => {
              e.preventDefault();
              ask();
            }}
          >
            <input
              value={input}
              maxLength={500}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about a government scheme…"
            />
            <button className="primary" disabled={loading || !input.trim()}>
              Send
            </button>
          </form>
        </>
      )}

      {tab === "explore" && (
        <section className="panel">
          <div className="chips">
            {categories.map((c) => (
              <button key={c} className={`chip ${c === category ? "on" : ""}`} onClick={() => setCategory(c)}>
                {c}
              </button>
            ))}
          </div>
          <div className="grid">
            {shown.map((s) => (
              <SchemeCard key={s.id} s={s} onAsk={ask} />
            ))}
          </div>
          {schemes.length === 0 && <p className="muted">Could not load schemes. Is the backend running?</p>}
        </section>
      )}

      {tab === "recommend" && <RecommendationForm />}

      <footer className="muted small">
        Answers come from indexed official documents and may not reflect the latest rules. Always confirm on the
        official scheme portal or at your local office.
      </footer>
    </div>
  );
}
