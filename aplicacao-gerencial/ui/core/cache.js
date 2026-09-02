const PREFIX = "gerencial.cache.";

export function readCache(key, maxAgeMs = 120000) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (!payload || Date.now() - Number(payload.savedAt || 0) > maxAgeMs) return null;
    return payload.value ?? null;
  } catch {
    return null;
  }
}

export function writeCache(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify({
      savedAt: Date.now(),
      value,
    }));
  } catch {
    // Cache is a speed boost only; storage errors should never block the app.
  }
}

export function removeCache(key) {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    // Ignore cache cleanup failures.
  }
}

export function removeCachePrefix(prefix) {
  try {
    const fullPrefix = PREFIX + prefix;
    Object.keys(localStorage)
      .filter((key) => key.startsWith(fullPrefix))
      .forEach((key) => localStorage.removeItem(key));
  } catch {
    // Ignore cache cleanup failures.
  }
}
