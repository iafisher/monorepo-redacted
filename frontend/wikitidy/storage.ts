declare const chrome: {
  storage: {
    local: {
      get: (
        keys: string[],
        callback: (result: Record<string, unknown>) => void,
      ) => void;
      set: (items: Record<string, unknown>, callback?: () => void) => void;
    };
  };
};

export type BackendChoice = "hard-coded" | "localhost" | "prod";

const STORAGE_KEY_BACKEND = "wikitidy-backend";
const STORAGE_KEY_STATUS = "wikitidy-status";

export async function loadBackend(): Promise<BackendChoice | null> {
  const value = await loadKey(STORAGE_KEY_BACKEND);
  if (value === "hard-coded" || value === "localhost" || value === "prod") {
    return value;
  }

  return null;
}

export function setBackend(choice: BackendChoice, callback?: () => void): void {
  setKey(STORAGE_KEY_BACKEND, choice, callback);
}

export function loadStatus(): Promise<string | null> {
  return loadKey(STORAGE_KEY_STATUS);
}

export function setStatus(value: string, callback?: () => void): void {
  setKey(STORAGE_KEY_STATUS, value, callback);
}

function loadKey(key: string): Promise<string | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get([key], (result) => {
      resolve(result[key] as string);
    });
  });
}

function setKey(key: string, value: string, callback?: () => void): void {
  chrome.storage.local.set({ [key]: value }, callback);
}
