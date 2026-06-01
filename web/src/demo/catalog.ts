export interface DemoPersonaOption {
  id: string;
  name: string;
  mbti: string;
}

export interface DemoTimeJump {
  hours: number;
  label: string;
}

export interface DemoScenario {
  id: string;
  label: string;
  description: string;
}

export interface DemoMemory {
  icon: string;
  label: string;
  content: string;
  category: string;
  key: string;
}

export interface DemoTestAction {
  id: string;
  icon: string;
  label: string;
  tone: "danger" | "warning" | "cool" | "warm" | "neutral" | "memory";
  scenarioId?: string;
  message?: string;
  burstMessages?: string[];
}

export const DEMO_PERSONAS: DemoPersonaOption[] = [
  { id: "luna", name: "陆暖", mbti: "ENFP" },
  { id: "vivian", name: "顾霆微", mbti: "INTJ" },
  { id: "iris", name: "苏漫", mbti: "INFP" },
];

export const DEMO_TIME_JUMPS: DemoTimeJump[] = [
  { hours: 1, label: "+1h" },
  { hours: 4, label: "+4h" },
  { hours: 8, label: "+8h" },
  { hours: 24, label: "+24h" },
];

export const DEMO_SCENARIOS: DemoScenario[] = [
  { id: "about_to_snap", label: "压力测试", description: "挫败值接近相变阈值" },
  { id: "lonely", label: "孤独测试", description: "模拟长时间未互动" },
  { id: "deeply_bonded", label: "亲密对话", description: "模拟深度关系状态" },
  { id: "calm_reset", label: "正常对话", description: "清空挫败并回到基线" },
];

export const DEMO_TEST_ACTIONS: DemoTestAction[] = [
  {
    id: "pressure_test",
    icon: "!",
    label: "压力测试",
    tone: "danger",
    scenarioId: "about_to_snap",
    message: "今天项目被毙了，心情很差",
  },
  {
    id: "neglect_stimulus",
    icon: "...",
    label: "敷衍刺激",
    tone: "warning",
    burstMessages: ["嗯", "哦", "嗯嗯", "哦"],
  },
  {
    id: "lonely_test",
    icon: "8h",
    label: "孤独测试",
    tone: "cool",
    scenarioId: "lonely",
  },
  {
    id: "intimate_chat",
    icon: "♥",
    label: "亲密对话",
    tone: "warm",
    scenarioId: "deeply_bonded",
    message: "团子今天把我耳机线咬断了",
  },
  {
    id: "normal_chat",
    icon: "OK",
    label: "正常对话",
    tone: "neutral",
    scenarioId: "calm_reset",
    message: "今天没睡好，感觉很累",
  },
  {
    id: "memory_test",
    icon: "MEM",
    label: "记忆测试",
    tone: "memory",
    message: "今天没睡好，感觉很累",
  },
];

export const DEMO_MEMORIES: DemoMemory[] = [
  {
    icon: "☕",
    label: "美式不加糖",
    content: "用户喜欢喝美式咖啡，不加糖不加奶",
    category: "preference",
    key: "美式",
  },
  {
    icon: "猫",
    label: "猫叫团子",
    content: "用户养了一只橘猫，名字叫团子，3岁了",
    category: "fact",
    key: "团子",
  },
  {
    icon: "跑",
    label: "跑步爱好",
    content: "用户每天早上跑5公里，最近在备战马拉松",
    category: "fact",
    key: "跑步",
  },
];

export const SIGNAL_CONFIG = [
  { key: "warmth", label: "温暖", color: "#eb7359" },
  { key: "vulnerability", label: "脆弱", color: "#a675d1" },
  { key: "depth", label: "深度", color: "#478fb8" },
  { key: "playfulness", label: "活泼", color: "#f2b233" },
  { key: "directness", label: "直接", color: "#59b887" },
  { key: "curiosity", label: "好奇", color: "#8cc0e6" },
  { key: "defiance", label: "张力", color: "#d96140" },
  { key: "initiative", label: "主动", color: "#b89972" },
] as const;

export const DRIVE_CONFIG = [
  { key: "connection", icon: "联", label: "联结" },
  { key: "novelty", icon: "新", label: "新奇" },
  { key: "expression", icon: "言", label: "表达" },
  { key: "safety", icon: "安", label: "安全" },
  { key: "play", icon: "乐", label: "玩乐" },
] as const;

export function buildDemoTimeJumpPayload(hours: number) {
  return { type: "demo_time_jump", hours };
}

export function buildDemoScenarioPayload(scenarioId: string) {
  return { type: "demo_scenario", scenario_id: scenarioId };
}

export function buildDemoMemoryPayload(memory: DemoMemory, personaId: string, clientId: string) {
  return {
    type: "demo_inject_memory",
    content: memory.content,
    category: memory.category,
    persona_id: personaId,
    client_id: clientId,
  };
}
