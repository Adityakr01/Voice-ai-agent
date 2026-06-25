import React from "react";
import { Mic, MicOff, Phone, PhoneOff } from "lucide-react";
import { TalkingAvatar } from "./components/TalkingAvatar";
import { ToolEventFeed } from "./components/ToolEventFeed";
import { CallSummaryPanel } from "./components/CallSummaryPanel";
import { useVoiceAgent } from "./hooks/useVoiceAgent";
import "./App.css";

export default function App() {
  const {
    agentState, toolEvents, summary, audioLevel,
    isConnected, connect, disconnect, clearSummary,
  } = useVoiceAgent();

  const handleToggle = async () => {
    if (isConnected) {
      await disconnect();
    } else {
      await connect();
    }
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-logo">
          <span className="logo-mark">M</span>
          <span className="logo-text">ykare</span>
          <span className="logo-badge">AI Voice</span>
        </div>
        <p className="header-tagline">Your 24/7 healthcare front desk</p>
      </header>

      {/* Main layout */}
      <main className="main">
        {/* Left: Avatar + controls */}
        <section className="panel panel-left">
          <TalkingAvatar state={agentState} audioLevel={audioLevel} />

          <div className="call-controls">
            <button
              className={`call-btn ${isConnected ? "call-btn-end" : "call-btn-start"}`}
              onClick={handleToggle}
              disabled={agentState === "connecting"}
            >
              {isConnected ? (
                <><PhoneOff size={20} /> End Call</>
              ) : agentState === "connecting" ? (
                <><Phone size={20} /> Connecting…</>
              ) : (
                <><Phone size={20} /> Start Call</>
              )}
            </button>

            {isConnected && (
              <div className="mic-indicator">
                <Mic size={14} className="mic-icon pulse" />
                <span>Mic active</span>
              </div>
            )}
          </div>

          {/* Quick capabilities list */}
          {!isConnected && agentState === "idle" && (
            <div className="capability-list">
              <p className="cap-title">I can help you</p>
              {[
                "📅 Book an appointment",
                "📋 View your bookings",
                "✏️ Reschedule a visit",
                "❌ Cancel an appointment",
              ].map(cap => (
                <span key={cap} className="cap-item">{cap}</span>
              ))}
            </div>
          )}
        </section>

        {/* Right: Live actions + transcript hint */}
        <section className="panel panel-right">
          <div className="panel-right-header">
            <h2>Live Session</h2>
            {isConnected && (
              <span className="live-badge">
                <span className="live-dot" />
                LIVE
              </span>
            )}
          </div>

          {!isConnected && agentState === "idle" && (
            <div className="idle-hint">
              <p>Press <strong>Start Call</strong> to begin speaking with your AI healthcare assistant.</p>
              <p className="idle-hint-sub">Your microphone will be activated automatically.</p>
            </div>
          )}

          <ToolEventFeed events={toolEvents} />

          {isConnected && toolEvents.length === 0 && (
            <div className="waiting-hint">
              <div className="waiting-dots">
                <span /><span /><span />
              </div>
              <p>Waiting for the call to begin…</p>
            </div>
          )}

          {/* Cost tracker (bonus) */}
          {toolEvents.length > 0 && (
            <div className="cost-tracker">
              <p className="cost-label">Estimated call cost</p>
              <p className="cost-value">
                ~${(toolEvents.length * 0.008 + 0.02).toFixed(3)}
                <span className="cost-note"> (STT + LLM + TTS)</span>
              </p>
            </div>
          )}
        </section>
      </main>

      {/* Call Summary overlay */}
      {summary && (
        <CallSummaryPanel summary={summary} onClose={clearSummary} />
      )}
    </div>
  );
}
