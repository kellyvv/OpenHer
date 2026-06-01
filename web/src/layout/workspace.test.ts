import { describe, expect, test } from "vitest";
import { buildChatShellClassName, buildWorkspaceClassName, countOpenWorkspacePanels } from "./workspace";

describe("workspace layout helpers", () => {
  test("counts only persistent side panels independently of chat", () => {
    expect(countOpenWorkspacePanels({ engine: true, demo: true, showcase: true })).toBe(2);
    expect(countOpenWorkspacePanels({ engine: false, demo: true, showcase: false })).toBe(0);
  });

  test("marks the conversation workspace as open when any panel is visible", () => {
    expect(buildWorkspaceClassName({ engine: true, demo: true, showcase: true })).toBe(
      "conversation-workspace workspace-open panels-2",
    );
    expect(buildWorkspaceClassName({ engine: false, demo: false, showcase: false })).toBe("conversation-workspace");
  });

  test("marks chat shell as locally scrollable", () => {
    expect(buildChatShellClassName()).toBe("chat-shell chat-shell-local-scroll");
  });
});
