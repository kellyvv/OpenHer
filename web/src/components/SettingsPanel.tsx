import { useEffect, useMemo, useState } from "react";
import { fetchStatus } from "../api/openherClient";
import type { Persona, StatusResponse } from "../types/openher";

interface SettingsPanelProps {
  open: boolean;
  baseUrl: string;
  isConnected: boolean;
  debugMode: boolean;
  showOnlyReadyPersonas: boolean;
  clientId: string;
  personas: Persona[];
  selectedPersona: Persona | null;
  onClose: () => void;
  onSaveBaseUrl: (value: string) => void;
  onToggleDebug: (value: boolean) => void;
  onOpenEnginePanel: () => void;
  onOpenDemoBar: () => void;
  onOpenShowcase: () => void;
  onToggleShowOnlyReady: (value: boolean) => void;
}

function personaName(persona: Persona | null): string {
  if (!persona) return "未选择";
  return persona.name_zh || persona.name;
}

export function SettingsPanel({
  open,
  baseUrl,
  isConnected,
  debugMode,
  showOnlyReadyPersonas,
  clientId,
  personas,
  selectedPersona,
  onClose,
  onSaveBaseUrl,
  onToggleDebug,
  onOpenEnginePanel,
  onOpenDemoBar,
  onOpenShowcase,
  onToggleShowOnlyReady,
}: SettingsPanelProps) {
  const [draft, setDraft] = useState(baseUrl);
  const [testState, setTestState] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [serverInfo, setServerInfo] = useState<StatusResponse | null>(null);
  const readyCount = useMemo(() => personas.filter((persona) => persona.has_front).length, [personas]);

  useEffect(() => {
    if (open) {
      setDraft(baseUrl);
      setTestState("idle");
    }
  }, [baseUrl, open]);

  if (!open) return null;

  const testConnection = async () => {
    setTestState("testing");
    try {
      const info = await fetchStatus(draft);
      setServerInfo(info);
      setTestState("ok");
    } catch {
      setServerInfo(null);
      setTestState("fail");
    }
  };

  return (
    <div className="settings-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="settings-panel settings-form" aria-label="设置" onMouseDown={(event) => event.stopPropagation()}>
        <header className="settings-titlebar">
          <div>
            <p>OpenHer</p>
            <h2>设置</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭设置">
            ×
          </button>
        </header>

        <section className="settings-section" aria-labelledby="backend-settings">
          <h3 id="backend-settings">后端服务器</h3>
          <div className="connection-card">
            <span className={`connection-dot ${isConnected ? "connection-dot-on" : ""}`} />
            <div>
              <strong>{isConnected ? "已连接" : "未连接"}</strong>
              <p>{baseUrl}</p>
            </div>
          </div>

          <label className="field-label">
            URL
            <input value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} />
          </label>

          <div className="settings-actions">
            <button className="settings-save" type="button" onClick={() => onSaveBaseUrl(draft)}>
              保存并重连
            </button>
            <button className="settings-secondary" type="button" onClick={testConnection} disabled={testState === "testing"}>
              {testState === "testing" ? "测试中" : "测试连接"}
            </button>
          </div>

          {testState !== "idle" && (
            <p className={`test-result test-${testState}`}>
              {testState === "ok" && serverInfo
                ? `${serverInfo.name} ${serverInfo.version} · ${serverInfo.engine} · ${serverInfo.personas.length} 个角色`
                : testState === "fail"
                  ? "无法连接到该后端地址"
                  : "正在检查后端状态"}
            </p>
          )}
        </section>

        <section className="settings-section" aria-labelledby="display-settings">
          <h3 id="display-settings">展示</h3>
          <label className="setting-toggle">
            <input
              type="checkbox"
              checked={showOnlyReadyPersonas}
              onChange={(event) => onToggleShowOnlyReady(event.target.checked)}
            />
            <span>
              <strong>仅显示已就绪角色</strong>
              <small>开启后，只展示带有唤醒展柜图的角色。当前 {readyCount}/{personas.length} 个角色就绪。</small>
            </span>
          </label>
        </section>

        <section className="settings-section" aria-labelledby="developer-settings">
          <h3 id="developer-settings">开发者</h3>
          <label className="setting-toggle">
            <input type="checkbox" checked={debugMode} onChange={(event) => onToggleDebug(event.target.checked)} />
            <span>
              <strong>开发者模式</strong>
              <small>聊天请求会携带 debug=true，并在对话页显示驱动力条。</small>
            </span>
          </label>
          <div className="developer-actions">
            <button className="settings-secondary" type="button" onClick={onOpenEnginePanel}>
              人格引擎
            </button>
            <button className="settings-secondary" type="button" onClick={onOpenDemoBar}>
              演示控制
            </button>
            <button className="settings-secondary" type="button" onClick={onOpenShowcase}>
              展示面板
            </button>
          </div>
        </section>

        <section className="settings-section" aria-labelledby="session-settings">
          <h3 id="session-settings">当前会话</h3>
          <dl className="settings-meta">
            <div>
              <dt>当前角色</dt>
              <dd>{personaName(selectedPersona)}</dd>
            </div>
            <div>
              <dt>角色总数</dt>
              <dd>{personas.length}</dd>
            </div>
            <div>
              <dt>client_id</dt>
              <dd>{clientId}</dd>
            </div>
          </dl>
        </section>
      </section>
    </div>
  );
}
