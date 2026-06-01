import { useEffect, useState } from "react";
import { mediaUrl } from "../api/openherClient";
import type { Persona } from "../types/openher";

interface AwakeningViewProps {
  baseUrl: string;
  persona: Persona;
  onComplete: () => void;
}

export function AwakeningView({ baseUrl, persona, onComplete }: AwakeningViewProps) {
  const [videoFailed, setVideoFailed] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(onComplete, persona.has_awakening_video && !videoFailed ? 5200 : 2600);
    return () => window.clearTimeout(timer);
  }, [onComplete, persona.has_awakening_video, videoFailed]);

  return (
    <section className="awakening-shell" aria-label="唤醒角色">
      {persona.has_awakening_video && !videoFailed ? (
        <video
          className="awakening-media"
          src={mediaUrl(baseUrl, persona.persona_id, "awakening")}
          autoPlay
          muted
          playsInline
          onEnded={onComplete}
          onError={() => setVideoFailed(true)}
        />
      ) : (
        <img className="awakening-media" src={mediaUrl(baseUrl, persona.persona_id, "front")} alt={persona.name_zh || persona.name} />
      )}
      <div className="awakening-overlay">
        <p className="mono-label">INITIALIZING PERSONA</p>
        <h1>{persona.name_zh || persona.name}</h1>
        <div className="boot-lines" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <p>神经权重同步中</p>
      </div>
    </section>
  );
}
