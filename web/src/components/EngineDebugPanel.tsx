import { DRIVE_CONFIG, SIGNAL_CONFIG } from "../demo/catalog";
import type { EngineDebugState } from "../types/openher";

interface EngineDebugPanelProps {
  open: boolean;
  debugState: EngineDebugState | null;
  onClose: () => void;
}

export function EngineDebugPanel({ open, debugState, onClose }: EngineDebugPanelProps) {
  if (!open) return null;
  const signals = debugState?.signals || {};
  const drives = debugState?.drive_state || {};
  const baselines = debugState?.drive_baseline || {};
  const frustration = typeof debugState?.frustration === "number" ? debugState.frustration : debugState?.total_frustration || 0;
  const temperature = debugState?.temperature || 0;
  const recalls = debugState?.style_recall || [];
  const hasSignals = Object.keys(signals).length > 0;
  const hasDrives = Object.keys(drives).length > 0;
  const hasDebug = Boolean(debugState);

  return (
    <aside className="engine-panel" aria-label="人格引擎调试面板">
      <header>
        <span className="engine-pulse" />
        <strong>人格引擎</strong>
        <em>t={debugState?.turn_count ?? 0}</em>
        <button className="panel-close" type="button" onClick={onClose} aria-label="关闭引擎面板">
          ×
        </button>
      </header>

      {!hasDebug && (
        <section className="engine-empty">
          <strong>等待引擎数据</strong>
          <p>打开面板会先尝试读取当前 demo 状态；完整的行为信号、内心独白和记忆召回，需要发送一次消息并开启开发者模式后由后端返回。</p>
        </section>
      )}

      <section className="network-preview" aria-label="神经网络预览">
        <div className="node-column">
          {(debugState?.input_vector || Array.from({ length: 8 }, () => 0)).slice(0, 8).map((value, index) => (
            <span key={index} style={{ opacity: 0.25 + Math.abs(value) * 0.7 }} />
          ))}
        </div>
        <div className="neural-lines" />
        <div className="node-column node-column-wide">
          {(debugState?.hidden_activations || Array.from({ length: 12 }, () => 0)).slice(0, 12).map((value, index) => (
            <span key={index} style={{ opacity: 0.25 + Math.abs(value) * 0.7 }} />
          ))}
        </div>
      </section>

      <DebugSection title="行为信号">
        {!hasSignals && <p className="debug-empty">等待一次带 debug=true 的对话...</p>}
        {SIGNAL_CONFIG.map((signal) => {
          const value = signals[signal.key] ?? 0;
          return <DebugBar key={signal.key} label={signal.label} value={value} color={signal.color} muted={!hasSignals} />;
        })}
      </DebugSection>

      <DebugSection title="内在驱力">
        {!hasDrives && <p className="debug-empty">等待后端返回当前驱力状态...</p>}
        {DRIVE_CONFIG.map((drive) => (
          <DebugBar
            key={drive.key}
            label={`${drive.icon} ${drive.label}`}
            value={drives[drive.key] ?? 0}
            baseline={baselines[drive.key]}
            color="#c77945"
            muted={!hasDrives}
          />
        ))}
      </DebugSection>

      <DebugSection title="挫败值 · 情绪噪声">
        <DebugBar label="挫败值" value={Math.min(frustration / 2, 1)} color="#d96140" text={frustration.toFixed(2)} muted={!hasDebug} />
        <DebugBar label="情绪温度" value={Math.min(temperature / 0.35, 1)} color="#8b80d8" text={temperature.toFixed(3)} muted={!hasDebug} />
      </DebugSection>

      <DebugSection title="感受 · 内心独白">
        <p className="debug-monologue">
          {debugState?.monologue || (debugState ? "本轮模型未返回内心独白，等待下一次调试输出。" : "等待一次对话后的引擎计算...")}
        </p>
      </DebugSection>

      <DebugSection title="风格记忆召回">
        {recalls.length === 0 ? (
          <p className="debug-empty">等待后端返回召回片段...</p>
        ) : (
          recalls.slice(0, 4).map((item) => (
            <p className="recall-row" key={`${item.text}-${item.distance}`}>
              <span>"{item.text}"</span>
              <em>d={item.distance.toFixed(2)}</em>
            </p>
          ))
        )}
      </DebugSection>
    </aside>
  );
}

function DebugSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="debug-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function DebugBar({
  label,
  value,
  color,
  baseline,
  text,
  muted,
}: {
  label: string;
  value: number;
  color: string;
  baseline?: number;
  text?: string;
  muted?: boolean;
}) {
  return (
    <label className={muted ? "debug-bar debug-bar-muted" : "debug-bar"}>
      <span>{label}</span>
      <i>
        <b style={{ width: `${clamp01(value) * 100}%`, background: color }} />
        {baseline !== undefined && <em style={{ left: `${clamp01(baseline) * 100}%` }} />}
      </i>
      <strong>{text || value.toFixed(2)}</strong>
    </label>
  );
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value || 0));
}
