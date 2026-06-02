import { describe, expect, test, vi } from "vitest";

import {
  MAX_RECORDING_MS,
  MIN_RECORDING_MS,
  RecordingTooShortError,
  assertRecordingDuration,
  createVoiceRecordingSession
} from "./audio";

class FakeMediaRecorder {
  static isTypeSupported() {
    return true;
  }

  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  state = "inactive";
  mimeType = "audio/webm;codecs=opus";

  constructor(_stream?: MediaStream, options?: MediaRecorderOptions) {
    this.mimeType = options?.mimeType || "audio/webm";
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

describe("audio recording helpers", () => {
  test("rejects recordings shorter than minimum duration", () => {
    expect(() => assertRecordingDuration(MIN_RECORDING_MS - 1)).toThrow(
      RecordingTooShortError
    );
    expect(() => assertRecordingDuration(MIN_RECORDING_MS)).not.toThrow();
  });

  test("auto-stops recording after max duration", async () => {
    vi.useFakeTimers();
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream)
    };

    const session = await createVoiceRecordingSession({
      mediaDevices,
      mediaRecorderCtor: FakeMediaRecorder as unknown as typeof MediaRecorder
    });
    const stopPromise = session.finished;

    vi.advanceTimersByTime(MAX_RECORDING_MS);

    await expect(stopPromise).resolves.toBeInstanceOf(Blob);
    vi.useRealTimers();
  });

  test("prefers MediaRecorder with raw browser audio when available", async () => {
    vi.useRealTimers();
    const now = vi.spyOn(Date, "now").mockReturnValue(0);
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream)
    };

    const session = await createVoiceRecordingSession({
      mediaDevices,
      mediaRecorderCtor: FakeMediaRecorder as unknown as typeof MediaRecorder
    });

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    const blob = await session.stop();

    expect(blob.type).toBe("audio/webm;codecs=opus");
    expect(mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        channelCount: 1
      }
    });
    now.mockRestore();
  });

  test("falls back to wav recording when MediaRecorder is unavailable", async () => {
    vi.useRealTimers();
    const now = vi.spyOn(Date, "now").mockReturnValue(0);
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream)
    };

    let processor: {
      onaudioprocess: ((event: AudioProcessingEvent) => void) | null;
      connect: () => void;
      disconnect: () => void;
    };
    class FakeAudioContext {
      sampleRate = 16_000;
      destination = {};
      createMediaStreamSource() {
        return { connect: vi.fn(), disconnect: vi.fn() };
      }
      createScriptProcessor() {
        processor = {
          onaudioprocess: null,
          connect: vi.fn(),
          disconnect: vi.fn()
        };
        return processor;
      }
      close = vi.fn();
    }

    const session = await createVoiceRecordingSession({
      mediaDevices,
      audioContextCtor: FakeAudioContext as unknown as typeof AudioContext,
      mediaRecorderCtor: undefined
    });
    processor!.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array([0, 0.5, -0.5, 0.25])
      }
    } as unknown as AudioProcessingEvent);

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    const blob = await session.stop();
    const bytes = await readBlob(blob);
    const header =
      new TextDecoder().decode(bytes.slice(0, 4)) +
      new TextDecoder().decode(bytes.slice(8, 12));

    expect(blob.type).toBe("audio/wav");
    expect(header).toBe("RIFFWAVE");
    now.mockRestore();
  });

  test("prefers wav recording on Chrome 55 WebView even when MediaRecorder exists", async () => {
    vi.useRealTimers();
    const now = vi.spyOn(Date, "now").mockReturnValue(0);
    const userAgent = vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (Linux; Android 6.0.1; NX531J) AppleWebKit/537.36 "
        + "(KHTML, like Gecko) Version/4.0 Chrome/55.0.2883.91 Mobile Safari/537.36"
    );
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream)
    };

    let processor: {
      onaudioprocess: ((event: AudioProcessingEvent) => void) | null;
      connect: () => void;
      disconnect: () => void;
    };
    class FakeAudioContext {
      sampleRate = 16_000;
      destination = {};
      createMediaStreamSource() {
        return { connect: vi.fn(), disconnect: vi.fn() };
      }
      createScriptProcessor() {
        processor = {
          onaudioprocess: null,
          connect: vi.fn(),
          disconnect: vi.fn()
        };
        return processor;
      }
      close = vi.fn();
    }

    const session = await createVoiceRecordingSession({
      mediaDevices,
      audioContextCtor: FakeAudioContext as unknown as typeof AudioContext,
      mediaRecorderCtor: FakeMediaRecorder as unknown as typeof MediaRecorder
    });
    processor!.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array([0, 0.25, -0.25])
      }
    } as unknown as AudioProcessingEvent);

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    const blob = await session.stop();

    expect(blob.type).toBe("audio/wav");
    userAgent.mockRestore();
    now.mockRestore();
  });

  test("keeps MediaRecorder on non-WebView Chrome 55", async () => {
    vi.useRealTimers();
    const now = vi.spyOn(Date, "now").mockReturnValue(0);
    const userAgent = vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (Linux; Android 6.0.1; NX531J) AppleWebKit/537.36 "
        + "(KHTML, like Gecko) Chrome/55.0.2883.91 Mobile Safari/537.36"
    );
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream)
    };

    const session = await createVoiceRecordingSession({
      mediaDevices,
      mediaRecorderCtor: FakeMediaRecorder as unknown as typeof MediaRecorder
    });

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    const blob = await session.stop();

    expect(blob.type).toBe("audio/webm;codecs=opus");
    userAgent.mockRestore();
    now.mockRestore();
  });

  test("encodes wav recordings at the ASR sample rate", async () => {
    vi.useRealTimers();
    const now = vi.spyOn(Date, "now").mockReturnValue(0);
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream)
    };

    let processor: {
      onaudioprocess: ((event: AudioProcessingEvent) => void) | null;
      connect: () => void;
      disconnect: () => void;
    };
    class FakeZeroRateAudioContext {
      sampleRate = 0;
      destination = {};
      createMediaStreamSource() {
        return { connect: vi.fn(), disconnect: vi.fn() };
      }
      createScriptProcessor() {
        processor = {
          onaudioprocess: null,
          connect: vi.fn(),
          disconnect: vi.fn()
        };
        return processor;
      }
      close = vi.fn();
    }

    const session = await createVoiceRecordingSession({
      mediaDevices,
      audioContextCtor: FakeZeroRateAudioContext as unknown as typeof AudioContext,
      mediaRecorderCtor: undefined
    });
    processor!.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array([0.2, 0.1, -0.1, -0.2])
      }
    } as unknown as AudioProcessingEvent);

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    const blob = await session.stop();
    const view = new DataView(await readBlob(blob));

    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint32(28, true)).toBe(32000);
    now.mockRestore();
  });

  test("downsamples WebView 48k wav recordings before upload", async () => {
    vi.useRealTimers();
    const now = vi.spyOn(Date, "now").mockReturnValue(0);
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream)
    };

    let processor: {
      onaudioprocess: ((event: AudioProcessingEvent) => void) | null;
      connect: () => void;
      disconnect: () => void;
    };
    class FakeAudioContext {
      sampleRate = 48_000;
      destination = {};
      createMediaStreamSource() {
        return { connect: vi.fn(), disconnect: vi.fn() };
      }
      createScriptProcessor() {
        processor = {
          onaudioprocess: null,
          connect: vi.fn(),
          disconnect: vi.fn()
        };
        return processor;
      }
      close = vi.fn();
    }

    const session = await createVoiceRecordingSession({
      mediaDevices,
      audioContextCtor: FakeAudioContext as unknown as typeof AudioContext,
      mediaRecorderCtor: undefined
    });
    processor!.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array(48_000).fill(0.2)
      }
    } as unknown as AudioProcessingEvent);

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    const view = new DataView(await readBlob(await session.stop()));

    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint32(40, true)).toBe(16000 * 2);
    now.mockRestore();
  });

  test("uses legacy navigator getUserMedia when mediaDevices is missing", async () => {
    vi.useRealTimers();
    const now = vi.spyOn(Date, "now").mockReturnValue(0);
    const stream = {
      getTracks: () => [{ stop: vi.fn() }]
    } as unknown as MediaStream;
    const legacyGetUserMedia = vi.fn(
      (
        _constraints: MediaStreamConstraints,
        success: (stream: MediaStream) => void
      ) => success(stream)
    );
    const originalMediaDevices = navigator.mediaDevices;
    const originalGetUserMedia = (
      navigator as Navigator & {
        webkitGetUserMedia?: typeof legacyGetUserMedia;
      }
    ).webkitGetUserMedia;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: undefined
    });
    Object.defineProperty(navigator, "webkitGetUserMedia", {
      configurable: true,
      value: legacyGetUserMedia
    });

    let processor: {
      onaudioprocess: ((event: AudioProcessingEvent) => void) | null;
      connect: () => void;
      disconnect: () => void;
    };
    class FakeAudioContext {
      sampleRate = 16_000;
      destination = {};
      createMediaStreamSource() {
        return { connect: vi.fn(), disconnect: vi.fn() };
      }
      createScriptProcessor() {
        processor = {
          onaudioprocess: null,
          connect: vi.fn(),
          disconnect: vi.fn()
        };
        return processor;
      }
      close = vi.fn();
    }

    const session = await createVoiceRecordingSession({
      audioContextCtor: FakeAudioContext as unknown as typeof AudioContext,
      mediaRecorderCtor: undefined
    });
    processor!.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array([0.2, 0.1])
      }
    } as unknown as AudioProcessingEvent);

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    await expect(session.stop()).resolves.toBeInstanceOf(Blob);
    expect(legacyGetUserMedia).toHaveBeenCalledWith(
      {
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1
        }
      },
      expect.any(Function),
      expect.any(Function)
    );

    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: originalMediaDevices
    });
    Object.defineProperty(navigator, "webkitGetUserMedia", {
      configurable: true,
      value: originalGetUserMedia
    });
    now.mockRestore();
  });
});

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}
