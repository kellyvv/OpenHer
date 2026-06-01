import { DEMO_MEMORIES, DEMO_PERSONAS, DEMO_TEST_ACTIONS, DEMO_TIME_JUMPS, type DemoMemory } from "../demo/catalog";
import type { Persona } from "../types/openher";

interface DemoBarProps {
  selectedPersonaId: string | null;
  onSwitchPersona: (personaId: string) => void;
  onTimeJump: (hours: number) => void;
  onScenario: (scenarioId: string) => void;
  onSendMessage: (message: string) => void;
  onInjectMemory: (memory: DemoMemory) => void;
  onClose: () => void;
}

export function DemoBar({
  selectedPersonaId,
  onSwitchPersona,
  onTimeJump,
  onScenario,
  onSendMessage,
  onInjectMemory,
  onClose,
}: DemoBarProps) {
  const runAction = (actionId: string) => {
    const action = DEMO_TEST_ACTIONS.find((item) => item.id === actionId);
    if (!action) return;
    if (action.scenarioId) onScenario(action.scenarioId);
    if (action.burstMessages) {
      action.burstMessages.forEach((message, index) => {
        window.setTimeout(() => onSendMessage(message), index * 800);
      });
    }
    if (action.message) {
      window.setTimeout(() => onSendMessage(action.message || ""), action.scenarioId ? 500 : 0);
    }
  };

  return (
    <aside className="demo-bar" aria-label="Demo 操作条">
      <header>
        <div>
          <strong>演示</strong>
          <span>演示操作台</span>
        </div>
        <button className="panel-close" type="button" onClick={onClose} aria-label="关闭 Demo 控制条">
          ×
        </button>
      </header>

      <DemoRow label="人格">
        {DEMO_PERSONAS.map((persona) => (
          <button
            className={persona.id === selectedPersonaId ? "demo-pill demo-active" : "demo-pill"}
            type="button"
            key={persona.id}
            onClick={() => onSwitchPersona(persona.id)}
          >
            <span>{persona.name}</span>
            <small>{persona.mbti}</small>
          </button>
        ))}
      </DemoRow>

      <DemoRow label="时间">
        {DEMO_TIME_JUMPS.map((jump) => (
          <button className="demo-chip demo-blue" type="button" key={jump.hours} onClick={() => onTimeJump(jump.hours)}>
            {jump.label}
          </button>
        ))}
      </DemoRow>

      <DemoRow label="测试">
        <div className="demo-test-grid">
          {DEMO_TEST_ACTIONS.map((action) => (
            <button className={`demo-test demo-${action.tone}`} type="button" key={action.id} onClick={() => runAction(action.id)}>
              <span>{action.icon}</span>
              {action.label}
            </button>
          ))}
        </div>
      </DemoRow>

      <DemoRow label="记忆">
        {DEMO_MEMORIES.map((memory) => (
          <button className="demo-chip demo-purple" type="button" key={memory.key} onClick={() => onInjectMemory(memory)}>
            <span>{memory.icon}</span>
            {memory.label}
          </button>
        ))}
      </DemoRow>
    </aside>
  );
}

function DemoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="demo-row">
      <span>{label}</span>
      <div>{children}</div>
    </section>
  );
}
