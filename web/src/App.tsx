import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchHistory, fetchPersonas, fetchStatus, getClientId, defaultBaseUrl, saveBaseUrl } from "./api/openherClient";
import { OpenHerSocket } from "./api/openherSocket";
import { AwakeningView } from "./components/AwakeningView";
import { ChatView } from "./components/ChatView";
import { DemoBar } from "./components/DemoBar";
import { DemoShowcasePanel } from "./components/DemoShowcasePanel";
import { DiscoveryView } from "./components/DiscoveryView";
import { EngineDebugPanel } from "./components/EngineDebugPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import {
  extractDemoSnapshot,
  extractEngineDebugState,
  mergeDemoSnapshotIntoDebugState,
  mergeEngineDebugState,
  mergeInjectedMemoryKeys,
} from "./demo/state";
import { buildWorkspaceClassName } from "./layout/workspace";
import {
  developerMode,
  saveDeveloperMode,
  saveSelectedPersonaId,
  saveShowOnlyReadyPersonas,
  selectedPersonaId,
  showOnlyReadyPersonas as readShowOnlyReadyPersonas,
} from "./state/local";
import type { AppPhase, ChatMessage, DemoSnapshot, EngineDebugState, EngineStatus, OpenHerEvent, Persona } from "./types/openher";

function toHistoryMessages(items: Awaited<ReturnType<typeof fetchHistory>>["messages"]): ChatMessage[] {
  return items.map((item) => ({
    id: `h_${item.id}`,
    role: item.role,
    content: item.content,
    modality: item.modality || "文字",
    imageUrl: item.role === "assistant" ? item.image_url : null,
    timestamp: item.created_at ? item.created_at * 1000 : Date.now(),
    sendStatus: "sent",
  }));
}

function audioUrlFromBase64(audio: string, format = "wav"): string {
  const byteCharacters = atob(audio);
  const byteNumbers = Array.from(byteCharacters, (char) => char.charCodeAt(0));
  const blob = new Blob([new Uint8Array(byteNumbers)], { type: `audio/${format === "mp3" ? "mpeg" : format}` });
  return URL.createObjectURL(blob);
}

export default function App() {
  const [baseUrl, setBaseUrl] = useState(defaultBaseUrl);
  const [clientId] = useState(getClientId);
  const [phase, setPhase] = useState<AppPhase>("discovery");
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(selectedPersonaId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isConnected, setConnected] = useState(false);
  const [isTyping, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [debugMode, setDebugMode] = useState(developerMode);
  const [showReadyOnly, setShowReadyOnly] = useState(readShowOnlyReadyPersonas);
  const [enginePanelOpen, setEnginePanelOpen] = useState(false);
  const [demoBarOpen, setDemoBarOpen] = useState(false);
  const [showcaseOpen, setShowcaseOpen] = useState(false);
  const [showcaseMode, setShowcaseMode] = useState(1);
  const [debugState, setDebugState] = useState<EngineDebugState | null>(null);
  const [demoSnapshot, setDemoSnapshot] = useState<DemoSnapshot | null>(null);
  const [injectedMemoryKeys, setInjectedMemoryKeys] = useState<string[]>([]);
  const [streaming, setStreaming] = useState("");
  const streamingRef = useRef("");
  const socketRef = useRef<OpenHerSocket | null>(null);

  const selectedPersona = useMemo(
    () => personas.find((persona) => persona.persona_id === selectedId) || null,
    [personas, selectedId],
  );
  const workspaceClassName = buildWorkspaceClassName({
    engine: enginePanelOpen,
    demo: false,
    showcase: showcaseOpen,
  });
  const effectiveDebugMode = debugMode || enginePanelOpen || showcaseOpen || demoBarOpen;

  const handleEvent = useCallback((event: OpenHerEvent) => {
    const eventPayload = event as unknown as Record<string, unknown>;

    if (event.type === "chat_start") {
      setTyping(true);
      setStreaming("");
      streamingRef.current = "";
      if (event.user_content) {
        setMessages((current) => {
          if (current.some((message) => message.role === "user" && message.content === event.user_content)) return current;
          return [
            ...current,
            {
              id: crypto.randomUUID(),
              role: "user",
              content: event.user_content || "",
              modality: "文字",
              timestamp: Date.now(),
              sendStatus: "sent",
            },
          ];
        });
      }
      return;
    }

    if (event.type === "chat_chunk") {
      setStreaming((current) => {
        const next = current + event.content;
        streamingRef.current = next;
        setMessages((messagesNow) => {
          const existing = messagesNow.findIndex((message) => message.id === "streaming_current");
          const streamingMessage: ChatMessage = {
            id: "streaming_current",
            role: "assistant",
            content: next,
            modality: "文字",
            timestamp: Date.now(),
          };
          if (existing >= 0) {
            const copy = [...messagesNow];
            copy[existing] = streamingMessage;
            return copy;
          }
          return [...messagesNow, streamingMessage];
        });
        return next;
      });
      return;
    }

    if (event.type === "chat_end") {
      setTyping(false);
      const finalStatus: EngineStatus = event;
      setStatus(finalStatus);
      const nextDebugState = extractEngineDebugState(eventPayload);
      if (nextDebugState) {
        setDebugState((current) => mergeEngineDebugState(current, nextDebugState));
        const nextSnapshot = extractDemoSnapshot(eventPayload);
        if (nextSnapshot) setDemoSnapshot(nextSnapshot);
        if (nextDebugState.monologue) {
          setInjectedMemoryKeys((current) => mergeInjectedMemoryKeys(current, nextDebugState.monologue || ""));
        }
      }
      setMessages((current) => {
        const existing = current.findIndex((message) => message.id === "streaming_current");
        const assistant: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: event.reply || streamingRef.current,
          modality: event.modality || "文字",
          imageUrl: event.image_url,
          timestamp: Date.now(),
          engineStatus: finalStatus,
          proactive: event.proactive,
        };
        if (existing >= 0) {
          const copy = [...current];
          copy[existing] = assistant;
          return copy;
        }
        return [...current, assistant];
      });
      setStreaming("");
      streamingRef.current = "";
      return;
    }

    if (event.type === "silence") {
      setTyping(false);
      setMessages((current) => current.filter((message) => message.id !== "streaming_current"));
      setStatus(event);
      return;
    }

    if (event.type === "proactive") {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: event.content,
          modality: event.modality || "文字",
          timestamp: Date.now(),
          proactive: true,
        },
      ]);
      return;
    }

    if (event.type === "tts_audio") {
      const url = audioUrlFromBase64(event.audio, event.format);
      setMessages((current) => {
        const copy = [...current];
        let index = -1;
        for (let i = copy.length - 1; i >= 0; i -= 1) {
          if (copy[i].role === "assistant") {
            index = i;
            break;
          }
        }
        if (index >= 0) copy[index] = { ...copy[index], audioUrl: url };
        return copy;
      });
      return;
    }

    if (event.type === "error") {
      setTyping(false);
      setError(event.content);
      return;
    }

    if (event.type === "demo_state") {
      const nextSnapshot = extractDemoSnapshot(eventPayload);
      if (nextSnapshot) {
        setDemoSnapshot(nextSnapshot);
        setDebugState((current) => mergeDemoSnapshotIntoDebugState(current, nextSnapshot));
      }
      return;
    }

    if (event.type === "demo_memory") {
      if (typeof event.content === "string") {
        setInjectedMemoryKeys((current) => mergeInjectedMemoryKeys(current, event.content || ""));
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setError(null);
      try {
        await fetchStatus(baseUrl);
        const list = await fetchPersonas(baseUrl);
        if (cancelled) return;
        setPersonas(list);
        const restored = selectedPersonaId();
        if (restored && list.some((persona) => persona.persona_id === restored)) {
          setSelectedId(restored);
          setPhase("conversation");
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : String(loadError));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [baseUrl]);

  useEffect(() => {
    const socket = new OpenHerSocket(baseUrl, clientId, {
      onOpen: () => {
        setConnected(true);
        setError(null);
      },
      onClose: () => setConnected(false),
      onError: (message) => {
        setConnected((connectedNow) => {
          if (!connectedNow) setError(message);
          return connectedNow;
        });
      },
      onEvent: handleEvent,
    });
    socket.connect();
    socketRef.current = socket;
    return () => socket.disconnect(false);
  }, [baseUrl, clientId, handleEvent]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    fetchHistory(baseUrl, selectedId, clientId)
      .then((history) => {
        if (!cancelled) setMessages(toHistoryMessages(history.messages));
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [baseUrl, clientId, selectedId]);

  const selectPersona = (persona: Persona) => {
    setSelectedId(persona.persona_id);
    saveSelectedPersonaId(persona.persona_id);
    setPhase("awakening");
    socketRef.current?.switchPersona(persona.persona_id);
  };

  const sendMessage = (content: string) => {
    if (!selectedId) return;
    const message: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      modality: "文字",
      timestamp: Date.now(),
      sendStatus: "sent",
    };
    setMessages((current) => [...current, message]);
    socketRef.current?.sendChat(content, selectedId, null, effectiveDebugMode);
  };

  const switchDemoPersona = (personaId: string) => {
    const persona = personas.find((item) => item.persona_id === personaId);
    if (persona) {
      setSelectedId(persona.persona_id);
      saveSelectedPersonaId(persona.persona_id);
      if (phase !== "conversation") setPhase("conversation");
    }
    socketRef.current?.switchPersona(personaId);
  };

  const enterConversationWorkspace = () => {
    setSettingsOpen(false);
    if (phase !== "conversation") {
      const targetId = selectedId || personas[0]?.persona_id;
      if (targetId) {
        setSelectedId(targetId);
        saveSelectedPersonaId(targetId);
        socketRef.current?.switchPersona(targetId);
        setPhase("conversation");
      }
    }
  };

  const openDeveloperPanel = () => {
    enterConversationWorkspace();
    setDebugMode(true);
    saveDeveloperMode(true);
    setEnginePanelOpen(true);
    socketRef.current?.sendDemoInject();
  };

  const openDemoBar = () => {
    enterConversationWorkspace();
    setDebugMode(true);
    saveDeveloperMode(true);
    setDemoBarOpen(true);
    socketRef.current?.sendDemoPresets();
  };

  const openShowcase = (mode = showcaseMode) => {
    enterConversationWorkspace();
    setDebugMode(true);
    saveDeveloperMode(true);
    setShowcaseMode(mode);
    setShowcaseOpen(true);
    socketRef.current?.sendDemoInject();
  };

  const updateBaseUrl = (value: string) => {
    setBaseUrl(saveBaseUrl(value));
  };

  const updateDebug = (value: boolean) => {
    setDebugMode(value);
    saveDeveloperMode(value);
  };

  return (
    <main className={`app app-${phase}`}>
      {phase === "discovery" && (
        <DiscoveryView
          baseUrl={baseUrl}
          personas={personas}
          isConnected={isConnected}
          error={error}
          showOnlyReadyPersonas={showReadyOnly}
          onSelect={selectPersona}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      )}

      {phase === "awakening" && selectedPersona && (
        <AwakeningView baseUrl={baseUrl} persona={selectedPersona} onComplete={() => setPhase("conversation")} />
      )}

      {phase === "conversation" && (
        <section className={workspaceClassName} aria-label="OpenHer 会话工作区">
          <ChatView
            baseUrl={baseUrl}
            persona={selectedPersona}
            messages={messages}
            isConnected={isConnected}
            isTyping={isTyping}
            status={status}
            debugMode={effectiveDebugMode}
            onOpenEnginePanel={openDeveloperPanel}
            onOpenDemoBar={openDemoBar}
            onOpenShowcase={() => openShowcase(3)}
            onSend={sendMessage}
            onTyping={(active) => socketRef.current?.sendTyping(active)}
            onBack={() => setPhase("discovery")}
            onOpenSettings={() => setSettingsOpen(true)}
          />

          {(enginePanelOpen || showcaseOpen) && (
            <aside className="insight-column" aria-label="引擎与情绪面板">
              <EngineDebugPanel open={enginePanelOpen} debugState={debugState} onClose={() => setEnginePanelOpen(false)} />
              <DemoShowcasePanel
                open={showcaseOpen}
                mode={showcaseMode}
                persona={selectedPersona}
                debugState={debugState}
                snapshot={demoSnapshot}
                injectedMemoryKeys={injectedMemoryKeys}
                onModeChange={setShowcaseMode}
                onClose={() => setShowcaseOpen(false)}
              />
            </aside>
          )}
        </section>
      )}

      {demoBarOpen && (
        <div className="demo-modal-backdrop" role="presentation" onMouseDown={() => setDemoBarOpen(false)}>
          <div className="demo-modal" onMouseDown={(event) => event.stopPropagation()}>
            <DemoBar
              selectedPersonaId={selectedId}
              onSwitchPersona={switchDemoPersona}
              onTimeJump={(hours) => socketRef.current?.sendDemoTimeJump(hours)}
              onScenario={(scenarioId) => {
                socketRef.current?.sendDemoScenario(scenarioId);
                if (scenarioId === "about_to_snap") openShowcase(3);
                if (scenarioId === "lonely") openShowcase(4);
              }}
              onSendMessage={sendMessage}
              onInjectMemory={(memory) => {
                if (!selectedId) return;
                setInjectedMemoryKeys((current) => mergeInjectedMemoryKeys(current, memory.content));
                socketRef.current?.sendDemoInjectMemory(memory, selectedId);
                openShowcase(2);
              }}
              onClose={() => setDemoBarOpen(false)}
            />
          </div>
        </div>
      )}

      <SettingsPanel
        open={settingsOpen}
        baseUrl={baseUrl}
        isConnected={isConnected}
        debugMode={debugMode}
        showOnlyReadyPersonas={showReadyOnly}
        clientId={clientId}
        personas={personas}
        selectedPersona={selectedPersona}
        onClose={() => setSettingsOpen(false)}
        onSaveBaseUrl={updateBaseUrl}
        onToggleDebug={updateDebug}
        onOpenEnginePanel={openDeveloperPanel}
        onOpenDemoBar={openDemoBar}
        onOpenShowcase={() => openShowcase()}
        onToggleShowOnlyReady={(value) => {
          setShowReadyOnly(value);
          saveShowOnlyReadyPersonas(value);
        }}
      />
    </main>
  );
}
