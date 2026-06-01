import type { EngineStatus } from "../types/openher";

interface EngineStatusPanelProps {
  status: EngineStatus | null;
  debugMode: boolean;
}

function pct(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return "0%";
  return `${Math.max(0, Math.min(100, Math.round(value * 100)))}%`;
}

export function EngineStatusPanel({ status, debugMode }: EngineStatusPanelProps) {
  const valence = status?.relationship?.valence ?? 0;
  const reward = status?.last_reward ?? 0;
  const temperature = status?.temperature ?? 0;
  const memories = status?.personal_memories ?? 0;
  const drives = Object.entries(status?.drive_state || {}).slice(0, debugMode ? 5 : 3);

  return (
    <aside className="frequency-panel" aria-label="情绪频率">
      <div className="frequency-line" aria-hidden="true">
        <span style={{ transform: `translateY(${Math.round((1 - temperature) * 74)}px)` }} />
      </div>
      <p>FREQ</p>
      <strong>{status?.dominant_drive || "tuning"}</strong>
      <dl>
        <div>
          <dt>VAL</dt>
          <dd>{valence.toFixed(2)}</dd>
        </div>
        <div>
          <dt>RWD</dt>
          <dd>{reward.toFixed(2)}</dd>
        </div>
        <div>
          <dt>TEMP</dt>
          <dd>{temperature.toFixed(2)}</dd>
        </div>
        <div>
          <dt>MEM</dt>
          <dd>{memories}</dd>
        </div>
      </dl>
      {debugMode && (
        <div className="drive-bars">
          {drives.map(([name, value]) => (
            <label key={name}>
              <span>{name}</span>
              <i>
                <b style={{ width: pct(value) }} />
              </i>
            </label>
          ))}
        </div>
      )}
    </aside>
  );
}
