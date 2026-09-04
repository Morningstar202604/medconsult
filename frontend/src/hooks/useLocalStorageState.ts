import { useState, useCallback } from "react";

export function useLocalStorageState<T>(
  key: string,
  defaultValue: T,
  transform?: {
    read?: (raw: string | null) => T;
    write?: (value: T) => string;
  }
): [T, (value: T | ((prev: T) => T)) => void] {
  const read = useCallback((raw: string | null): T => {
    if (transform?.read) return transform.read(raw);
    try {
      return JSON.parse(raw ?? "") as T;
    } catch {
      return defaultValue;
    }
  }, [defaultValue, transform]);

  const write = useCallback((value: T): string => {
    if (transform?.write) return transform.write(value);
    return JSON.stringify(value);
  }, [transform]);

  const [value, setValue] = useState<T>(() => read(localStorage.getItem(key) ?? ""));

  const setStoredValue = useCallback((newValue: T | ((prev: T) => T)) => {
    setValue((prev) => {
      const next = typeof newValue === "function" ? (newValue as (prev: T) => T)(prev) : newValue;
      try {
        localStorage.setItem(key, write(next));
      } catch { /* ignore quota errors */ }
      return next;
    });
  }, [key, write]);

  return [value, setStoredValue];
}
