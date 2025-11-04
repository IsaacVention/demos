import React, { useEffect, useRef, useState } from "react";
import { client } from "./client";
// adjust the path to wherever your ES messages live
import {
  StateChangeEvent,
  SMTriggerResponse,
} from "./gen/es/proto/app_pb";

type AppState = StateChangeEvent | null;

function App() {
  const [appState, setAppState] = useState<AppState>(null);
  const [events, setEvents] = useState<Array<{ ts: number; label: string }>>(
    []
  );
  const [error, setError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // 2) auto-subscribe to MachineState stream
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    setIsStreaming(true);

    (async () => {
      try {
        // stream returns Empty right now – we use it as a signal
        for await (const stateChange of client.state_change(
          {},
          { signal: controller.signal }
        )) {
          setAppState(stateChange);
          setEvents((prev) => [
            {
              ts: Date.now(),
              label: `State → ${stateChange.newState} (triggered by ${stateChange.trigger})`,
            },
            ...prev,
          ]);
        }
      } catch (err: any) {
        if (err.name === "AbortError") {
          console.log("stream aborted");
        } else {
          console.error("MachineState stream error:", err);
          setError("Stream error — check console.");
        }
      } finally {
        setIsStreaming(false);
      }
    })();

    return () => {
      controller.abort();
      setIsStreaming(false);
    };
  }, []);

  // 3) actions (start / reset / to_ready-as-stop)
  async function handleStart() {
    setError(null);
    try {
      const res: SMTriggerResponse = await client.start({});
      pushEvent(`start → ${res.newState}`);
    } catch (err) {
      console.error("start failed", err);
      setError("start failed");
    }
  }

  async function handleReset() {
    setError(null);
    try {
      const res: SMTriggerResponse = await client.reset({});
      pushEvent(`reset → ${res.newState}`);
    } catch (err) {
      console.error("reset failed", err);
      setError("reset failed");
    }
  }

  // we don't actually have "stop" in the proto, so let's map to to_ready()
  async function handleStop() {
    setError(null);
    try {
      // connect-es will camelCase "to_ready" → "toReady"
      const res: SMTriggerResponse = await (client as any).toReady({});
      pushEvent(`toReady → ${res.newState}`);
    } catch (err) {
      console.error("toReady failed", err);
      setError("stop failed");
    }
  }

  function pushEvent(label: string) {
    setEvents((prev) => [{ ts: Date.now(), label }, ...prev].slice(0, 50));
  }

  return (
    <div
      style={{
        padding: "2rem",
        fontFamily: "system-ui, sans-serif",
        maxWidth: "780px",
        margin: "0 auto",
        display: "grid",
        gap: "1.5rem",
      }}
    >
      <header>
        <h1>🧠 Vention IPC Demo (SM)</h1>
        <p style={{ color: "#666" }}>
          Connected to <code>VentionAppService</code>. Stream:{" "}
          <code>MachineState</code>.
        </p>
      </header>

      {/* Current State */}
      <section
        style={{
          background: "#f5f5f5",
          borderRadius: 12,
          padding: "1rem 1.5rem",
        }}
      >
        <h2 style={{ marginBottom: "0.75rem" }}>Current application state</h2>
        {appState ? (
          <div>
            <p>
              <strong>state:</strong>{" "}
              <code>{appState.newState ?? "(unknown)"}</code>
            </p>
            <p>
              <strong>time_remaining:</strong>{" "}
              {appState.timeRemaining ?? "—"}
            </p>
          </div>
        ) : (
          <p style={{ color: "#999" }}>Loading…</p>
        )}
      </section>

      {/* Controls */}
      <section
        style={{
          background: "#fff",
          border: "1px solid #eee",
          borderRadius: 12,
          padding: "1rem 1.5rem",
        }}
      >
        <h2 style={{ marginBottom: "0.75rem" }}>Controls</h2>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button onClick={handleStart}>▶ start</button>
          <button onClick={handleStop}>⏸ stop (to_ready)</button>
          <button onClick={handleReset}>⟲ reset</button>
        </div>
        <p style={{ marginTop: "0.5rem", fontSize: 12, color: "#888" }}>
          Stream: {isStreaming ? "listening…" : "not listening"}
        </p>
      </section>

      {/* Event log */}
      <section
        style={{
          background: "#090909",
          borderRadius: 12,
          padding: "1rem 1.5rem",
          color: "#fff",
        }}
      >
        <h2 style={{ marginBottom: "0.75rem" }}>Stream events</h2>
        <div
          style={{
            maxHeight: 240,
            overflowY: "auto",
            fontFamily: "ui-monospace, SFMono-Regular, SFMono-Regular",
            fontSize: 13,
          }}
        >
          {events.length === 0 ? (
            <p style={{ color: "#bbb" }}>
              {isStreaming ? "Waiting for events…" : "No events yet."}
            </p>
          ) : (
            events.map((e, i) => (
              <div
                key={i}
                style={{ padding: "0.25rem 0", borderBottom: "1px solid #222" }}
              >
                <span style={{ opacity: 0.5 }}>
                  {new Date(e.ts).toLocaleTimeString()}
                </span>{" "}
                — {e.label}
              </div>
            ))
          )}
        </div>
      </section>

      {error && (
        <p style={{ color: "red", fontWeight: 600 }}>⚠ {error}</p>
      )}
    </div>
  );
}

export default App;
