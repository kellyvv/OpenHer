export interface WorkspacePanelState {
  engine: boolean;
  demo: boolean;
  showcase: boolean;
}

export function countOpenWorkspacePanels(state: WorkspacePanelState): number {
  return Number(state.engine) + Number(state.showcase);
}

export function buildWorkspaceClassName(state: WorkspacePanelState): string {
  const count = countOpenWorkspacePanels(state);
  return ["conversation-workspace", count > 0 ? "workspace-open" : "", count > 0 ? `panels-${count}` : ""]
    .filter(Boolean)
    .join(" ");
}

export function buildChatShellClassName(): string {
  return "chat-shell chat-shell-local-scroll";
}
