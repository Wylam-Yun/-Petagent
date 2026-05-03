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

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["voice"], { type: "audio/webm" }) });
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

  test("prefers wav recording when Web Audio is available", async () => {
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
      mediaRecorderCtor: FakeMediaRecorder as unknown as typeof MediaRecorder
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

  test("uses a valid wav sample rate when old WebView reports zero", async () => {
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
      audioContextCtor: FakeZeroRateAudioContext as unknown as typeof AudioContext
    });
    processor!.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array([0.2, 0.1, -0.1, -0.2])
      }
    } as unknown as AudioProcessingEvent);

    now.mockReturnValue(MIN_RECORDING_MS + 1);
    const blob = await session.stop();
    const view = new DataView(await readBlob(blob));

    expect(view.getUint32(24, true)).toBe(48000);
    expect(view.getUint32(28, true)).toBe(96000);
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
