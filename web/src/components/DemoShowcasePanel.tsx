import { DRIVE_CONFIG, SIGNAL_CONFIG, DEMO_MEMORIES } from "../demo/catalog";
import type { DemoSnapshot, EngineDebugState, Persona } from "../types/openher";

interface DemoShowcasePanelProps {
  open: boolean;
  mode: number;
  persona: Persona | null;
  debugState: EngineDebugState | null;
  snapshot: DemoSnapshot | null;
  injectedMemoryKeys: string[];
  onModeChange: (mode: number) => void;
  onClose: () => void;
}

const modeLabels = ["人格对比", "记忆注入", "压力来源", "时间关系"];

export function DemoShowcasePanel({
  open,
  mode,
  persona,
  debugState,
  snapshot,
  injectedMemoryKeys,
  onModeChange,
  onClose,
}: DemoShowcasePanelProps) {
  if (!open) return null;

  const relationshipDepth = debugState?.relationship?.depth ?? 0;
  const monologue = debugState?.monologue || "";
  const monologueEmptyText = debugState ? "本轮模型未返回内心独白，等待下一次调试输出。" : "等待发送一条开启调试的消息。";
  const temp = snapshot?.temperature ?? debugState?.temperature ?? 0;

  return (
    <aside className="showcase-panel" aria-label="Demo 展示面板">
      <header className="showcase-header">
        <div>
          <strong>{persona?.name_zh || persona?.name || "OpenHer"}</strong>
          <p>{modeLabels[mode - 1]}</p>
        </div>
        <nav aria-label="展示模式">
          {[1, 2, 3, 4].map((item) => (
            <button className={mode === item ? "mode-dot mode-dot-active" : "mode-dot"} type="button" key={item} onClick={() => onModeChange(item)}>
              {item}
            </button>
          ))}
        </nav>
        <button className="panel-close" type="button" onClick={onClose} aria-label="关闭展示面板">
          ×
        </button>
      </header>

      <section className="relationship-row">
        <span>亲密度</span>
        <i>
          <b style={{ width: `${clamp01(relationshipDepth) * 100}%` }} />
        </i>
        <em>{relationshipDepth.toFixed(2)}</em>
      </section>

      <section className="monologue-card">
        <span>内心独白</span>
        <p>{monologue ? `「${monologue}」` : monologueEmptyText}</p>
      </section>

      <div className="showcase-body">
        {mode === 1 && <SignalsView signals={debugState?.signals || {}} />}
        {mode === 2 && <MemoryView injectedMemoryKeys={injectedMemoryKeys} monologue={monologue} />}
        {mode === 3 && <EmotionView snapshot={snapshot} />}
        {mode === 4 && <TimeView snapshot={snapshot} />}
      </div>

      <section className="temperature-footer">
        <span>情绪压力</span>
        <i>
          <b style={{ width: `${clamp01(temp) * 100}%` }} />
        </i>
        <em>{temp.toFixed(3)}</em>
      </section>
    </aside>
  );
}

function SignalsView({ signals }: { signals: Record<string, number> }) {
  return (
    <section className="showcase-mode">
      <h3>行为信号</h3>
      <p>她从你的话里读出了什么</p>
      <div className="signal-list">
        {SIGNAL_CONFIG.map((signal) => {
          const value = signals[signal.key] ?? 0;
          return (
            <label key={signal.key}>
              <span>{signal.label}</span>
              <i>
                <b style={{ width: `${clamp01(value) * 100}%`, background: signal.color }} />
              </i>
              <em>{value.toFixed(2)}</em>
            </label>
          );
        })}
      </div>
    </section>
  );
}

function MemoryView({ injectedMemoryKeys, monologue }: { injectedMemoryKeys: string[]; monologue: string }) {
  return (
    <section className="showcase-mode">
      <h3>EverMemOS · 记忆</h3>
      <p>注入的记忆会融入她的回复</p>
      <div className="memory-pills">
        {DEMO_MEMORIES.map((memory) => {
          const injected = injectedMemoryKeys.some((item) => item.includes(memory.key)) || monologue.includes(memory.key);
          return (
            <div className={injected ? "memory-pill memory-pill-on" : "memory-pill"} key={memory.key}>
              <strong>{memory.icon}</strong>
              <span>{memory.label}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EmotionView({ snapshot }: { snapshot: DemoSnapshot | null }) {
  const frust = snapshot?.frustration || {};
  const temp = snapshot?.temperature ?? 0;
  return (
    <section className="showcase-mode">
      <h3>压力来源</h3>
      <p>各维度不满足值，越高越容易爆发</p>
      <div className="emotion-bars">
        {DRIVE_CONFIG.map((drive) => {
          const value = frust[drive.key] ?? 0;
          return (
            <label key={drive.key}>
              <span>{drive.icon} {drive.label}</span>
              <i>
                <b style={{ width: `${Math.min(value / 3, 1) * 100}%` }} />
              </i>
              <em>{value.toFixed(1)}</em>
            </label>
          );
        })}
      </div>
      <p className="status-label">{temp > 0.25 ? "临界爆发" : temp > 0.12 ? "挫败积累中" : "情绪稳定"}</p>
    </section>
  );
}

function TimeView({ snapshot }: { snapshot: DemoSnapshot | null }) {
  const connection = snapshot?.drive_state?.connection ?? 0;
  return (
    <section className="showcase-mode">
      <h3>想念指数</h3>
      <p>越高越想主动找你说话</p>
      <div className="miss-index">
        <i>
          <b style={{ width: `${clamp01(connection) * 100}%` }} />
        </i>
        <strong>{connection.toFixed(2)}</strong>
      </div>
      {connection < 0.2 && <p className="status-label">她即将主动发消息...</p>}
    </section>
  );
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value || 0));
}
