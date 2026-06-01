import { mediaUrl } from "../api/openherClient";
import type { Persona } from "../types/openher";

interface DiscoveryViewProps {
  baseUrl: string;
  personas: Persona[];
  isConnected: boolean;
  error: string | null;
  showOnlyReadyPersonas: boolean;
  onSelect: (persona: Persona) => void;
  onOpenSettings: () => void;
}

function displayName(persona: Persona): string {
  return persona.name_zh || persona.name;
}

function tags(persona: Persona): string[] {
  return (persona.tags_zh && persona.tags_zh.length > 0 ? persona.tags_zh : persona.tags).slice(0, 3);
}

export function DiscoveryView({
  baseUrl,
  personas,
  isConnected,
  error,
  showOnlyReadyPersonas,
  onSelect,
  onOpenSettings,
}: DiscoveryViewProps) {
  const readyPersonas = personas.filter((persona) => persona.has_front);
  const visible = showOnlyReadyPersonas && readyPersonas.length > 0 ? readyPersonas : personas;

  return (
    <section className="discovery-shell" aria-label="角色发现">
      <header className="topbar">
        <img src="/assets/logo_header.png" alt="OpenHer" className="logo-mark" />
        <div className="topbar-actions">
          <span className={`presence ${isConnected ? "presence-on" : ""}`}>{isConnected ? "在线" : "离线"}</span>
          <button className="icon-button" type="button" onClick={onOpenSettings} aria-label="打开设置">
            ⚙
          </button>
        </div>
      </header>

      {error && <div className="inline-error">{error}</div>}

      <div className="persona-grid">
        {visible.map((persona) => (
          <article className="persona-card" key={persona.persona_id}>
            <img
              className="persona-card-image"
              src={persona.has_front ? mediaUrl(baseUrl, persona.persona_id, "front") : mediaUrl(baseUrl, persona.persona_id, "face")}
              alt={displayName(persona)}
              loading="lazy"
            />
            <div className="glass-reflection" aria-hidden="true" />
            <div className="persona-caption">
              <h1>{displayName(persona)}</h1>
              <p>{[persona.age, persona.mbti].filter(Boolean).join(" · ")}</p>
              <div className="tag-row">
                {tags(persona).map((tag) => (
                  <span key={tag}>#{tag}</span>
                ))}
              </div>
              <button className="awaken-button" type="button" onClick={() => onSelect(persona)}>
                唤醒
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
