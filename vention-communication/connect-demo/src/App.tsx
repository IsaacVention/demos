import React, { useRef, useState } from "react";
import { client } from "./client";

function App() {
  const [pingResponse, setPingResponse] = useState<string>("");
  const [heartbeatMessages, setHeartbeatMessages] = useState<number[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function handlePing() {
    try {
      setError(null);
      // send basic JS object — Connect runtime serializes automatically
      const res = await client.ping({ message: "Hello from browser" });
      // res is a plain JSON object from your JSON transport
      setPingResponse(res.message);
    } catch (err) {
      console.error("Ping error:", err);
      setError("Ping failed");
    }
  }

  async function startHeartbeat() {
    if (isStreaming) return;
    setError(null);
    setHeartbeatMessages([]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      // client.heartbeat returns an async iterator
      for await (const msg of client.heartbeat(
        {},
        { signal: controller.signal }
      )) {
        // Each msg is { value: "<number as string>" }
        const val = Number(msg.value);
        setHeartbeatMessages([val]);
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        console.log("Stream aborted");
      } else {
        console.error("Heartbeat stream error:", err);
        setError("Stream error — check console for details.");
      }
    } finally {
      setIsStreaming(false);
    }
  }

  function stopHeartbeat() {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }

  return (
    <div
      style={{
        padding: "2rem",
        fontFamily: "system-ui, sans-serif",
        maxWidth: "600px",
        margin: "0 auto",
      }}
    >
      <h1>🧩 ConnectRPC Demo</h1>

      {/* PING */}
      <section style={{ marginBottom: "2rem" }}>
        <h2>Ping</h2>
        <button onClick={handlePing}>Send Ping</button>
        {pingResponse && (
          <p style={{ color: "#4caf50" }}>Response: {pingResponse}</p>
        )}
      </section>

      {/* HEARTBEAT STREAM */}
      <section>
        <h2>Heartbeat Stream</h2>
        <div style={{ marginBottom: "1rem" }}>
          {!isStreaming ? (
            <button onClick={startHeartbeat}>▶ Start Stream</button>
          ) : (
            <button onClick={stopHeartbeat}>⏸ Stop Stream</button>
          )}
        </div>

        {error && <p style={{ color: "red" }}>{error}</p>}

        <div
          style={{
            background: "#f5f5f5",
            borderRadius: "8px",
            padding: "1rem",
            height: "200px",
            overflowY: "auto",
            fontFamily: "monospace",
          }}
        >
          {heartbeatMessages.length === 0 ? (
            <p style={{ color: "#999" }}>
              {isStreaming ? "Waiting for data..." : "No data yet"}
            </p>
          ) : (
            heartbeatMessages
              .slice()
              .reverse()
              .map((val, i) => (
                <div key={i}>
                  <strong>{heartbeatMessages.length - i}.</strong>{" "}
                  {val.toFixed(2)}
                </div>
              ))
          )}
        </div>
      </section>
    </div>
  );
}

export default App;
