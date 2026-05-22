import { useEffect, useState } from "react";

export type ClientConfig = {
  audio_wait_ms: number;
  audio_progressive: Record<string, string>;
  pet_name: string;
};

const DEFAULT_CONFIG: ClientConfig = {
  audio_wait_ms: 90_000,
  audio_progressive: {
    "0": "Momo 准备声音…",
    "5000": "Momo 有点慢，再等一下…",
    "30000": "声音可能要再等一会儿…",
  },
  pet_name: "Momo",
};

export function useClientConfig(): ClientConfig {
  const [config, setConfig] = useState<ClientConfig>(DEFAULT_CONFIG);

  useEffect(() => {
    let alive = true;
    fetch("/api/runtime/client-config")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (alive && data) {
          setConfig({
            audio_wait_ms: data.audio_wait_ms ?? DEFAULT_CONFIG.audio_wait_ms,
            audio_progressive: data.audio_progressive ?? DEFAULT_CONFIG.audio_progressive,
            pet_name: data.pet_name ?? DEFAULT_CONFIG.pet_name,
          });
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  return config;
}
