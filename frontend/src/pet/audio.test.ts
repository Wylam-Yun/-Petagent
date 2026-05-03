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
});
