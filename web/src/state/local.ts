export function selectedPersonaId(): string | null {
  return localStorage.getItem("openher.selectedPersonaId");
}

export function saveSelectedPersonaId(personaId: string): void {
  localStorage.setItem("openher.selectedPersonaId", personaId);
}

export function developerMode(): boolean {
  return localStorage.getItem("openher.developerMode") === "true";
}

export function saveDeveloperMode(value: boolean): void {
  localStorage.setItem("openher.developerMode", String(value));
}

export function showOnlyReadyPersonas(): boolean {
  const value = localStorage.getItem("openher.showOnlyReadyPersonas");
  return value === null ? true : value === "true";
}

export function saveShowOnlyReadyPersonas(value: boolean): void {
  localStorage.setItem("openher.showOnlyReadyPersonas", String(value));
}
