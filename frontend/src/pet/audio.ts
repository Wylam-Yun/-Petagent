export const MIN_RECORDING_MS = 300;
export const MAX_RECORDING_MS = 15_000;

export class RecordingTooShortError extends Error {
  constructor() {
    super("recording_too_short");
    this.name = "RecordingTooShortError";
  }
}

export class MicrophonePermissionError extends Error {
  constructor() {
    super("microphone_unavailable");
    this.name = "MicrophonePermissionError";
  }
}

export type VoiceRecordingSession = {
  stop: () => Promise<Blob>;
  cancel: () => void;
  finished: Promise<Blob>;
};

type RecordingOptions = {
  mediaDevices?: Pick<MediaDevices, "getUserMedia">;
  mediaRecorderCtor?: typeof MediaRecorder;
  audioContextCtor?: typeof AudioContext;
};

class UnsupportedWavRecorderError extends Error {
  constructor() {
    super("wav_recorder_unavailable");
    this.name = "UnsupportedWavRecorderError";
  }
}

export function assertRecordingDuration(durationMs: number) {
  if (durationMs < MIN_RECORDING_MS) {
    throw new RecordingTooShortError();
  }
}

export async function createVoiceRecordingSession(
  options: RecordingOptions = {}
): Promise<VoiceRecordingSession> {
  try {
    return await createWavRecordingSession(options);
  } catch (error) {
    if (error instanceof MicrophonePermissionError) {
      throw error;
    }
  }
  return createMediaRecorderSession(options);
}

async function createWavRecordingSession(
  options: RecordingOptions = {}
): Promise<VoiceRecordingSession> {
  const mediaDevices = options.mediaDevices ?? navigator.mediaDevices;
  const AudioContextCtor = options.audioContextCtor ?? getAudioContextCtor();
  if (!mediaDevices?.getUserMedia || !AudioContextCtor) {
    throw new UnsupportedWavRecorderError();
  }

  let stream: MediaStream;
  try {
    stream = await mediaDevices.getUserMedia({ audio: true });
  } catch {
    throw new MicrophonePermissionError();
  }

  let audioContext: AudioContext;
  try {
    audioContext = new AudioContextCtor();
  } catch {
    stopStream(stream);
    throw new UnsupportedWavRecorderError();
  }

  const chunks: Float32Array[] = [];
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const startedAt = Date.now();
  let stopped = false;
  let resolveFinished: (blob: Blob) => void = () => undefined;
  let rejectFinished: (error: Error) => void = () => undefined;

  const finished = new Promise<Blob>((resolve, reject) => {
    resolveFinished = resolve;
    rejectFinished = reject;
  });

  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(input));
  };
  source.connect(processor);
  processor.connect(audioContext.destination);

  const finish = () => {
    clearTimeout(maxTimer);
    processor.disconnect();
    source.disconnect();
    stopStream(stream);
    void audioContext.close?.();
    try {
      assertRecordingDuration(Date.now() - startedAt);
      resolveFinished(encodeWavBlob(chunks, audioContext.sampleRate));
    } catch (error) {
      rejectFinished(error as Error);
    }
  };

  const maxTimer = window.setTimeout(() => {
    if (!stopped) {
      stopped = true;
      finish();
    }
  }, MAX_RECORDING_MS);

  return {
    stop: () => {
      if (!stopped) {
        stopped = true;
        finish();
      }
      return finished;
    },
    cancel: () => {
      stopped = true;
      clearTimeout(maxTimer);
      processor.disconnect();
      source.disconnect();
      stopStream(stream);
      void audioContext.close?.();
    },
    finished
  };
}

async function createMediaRecorderSession(
  options: RecordingOptions = {}
): Promise<VoiceRecordingSession> {
  const mediaDevices = options.mediaDevices ?? navigator.mediaDevices;
  const MediaRecorderCtor = options.mediaRecorderCtor ?? window.MediaRecorder;
  if (!mediaDevices?.getUserMedia || !MediaRecorderCtor) {
    throw new MicrophonePermissionError();
  }

  let stream: MediaStream;
  try {
    stream = await mediaDevices.getUserMedia({ audio: true });
  } catch {
    throw new MicrophonePermissionError();
  }

  const chunks: Blob[] = [];
  const mimeType = selectMimeType(MediaRecorderCtor);
  const recorder = mimeType
    ? new MediaRecorderCtor(stream, { mimeType })
    : new MediaRecorderCtor(stream);
  const startedAt = Date.now();
  let stopped = false;
  let resolveFinished: (blob: Blob) => void = () => undefined;
  let rejectFinished: (error: Error) => void = () => undefined;

  const finished = new Promise<Blob>((resolve, reject) => {
    resolveFinished = resolve;
    rejectFinished = reject;
  });

  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      chunks.push(event.data);
    }
  };
  recorder.onstop = () => {
    clearTimeout(maxTimer);
    stopStream(stream);
    try {
      assertRecordingDuration(Date.now() - startedAt);
      resolveFinished(new Blob(chunks, { type: mimeType || "audio/webm" }));
    } catch (error) {
      rejectFinished(error as Error);
    }
  };

  const maxTimer = window.setTimeout(() => {
    if (!stopped && recorder.state !== "inactive") {
      stopped = true;
      recorder.stop();
    }
  }, MAX_RECORDING_MS);

  recorder.start();

  return {
    stop: () => {
      if (!stopped && recorder.state !== "inactive") {
        stopped = true;
        recorder.stop();
      }
      return finished;
    },
    cancel: () => {
      stopped = true;
      clearTimeout(maxTimer);
      stopStream(stream);
    },
    finished
  };
}

function selectMimeType(MediaRecorderCtor: typeof MediaRecorder): string {
  const candidates = ["audio/webm", "audio/mp4", "audio/wav"];
  return candidates.find((candidate) => MediaRecorderCtor.isTypeSupported(candidate)) ?? "";
}

function getAudioContextCtor(): typeof AudioContext | undefined {
  return window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext })
    .webkitAudioContext;
}

function stopStream(stream: MediaStream) {
  stream.getTracks().forEach((track) => track.stop());
}

function encodeWavBlob(chunks: Float32Array[], sampleRate: number): Blob {
  const sampleCount = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, sampleCount * 2, true);

  let offset = 44;
  chunks.forEach((chunk) => {
    for (let index = 0; index < chunk.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, chunk[index]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }
  });

  return new Blob([buffer], { type: "audio/wav" });
}

function writeString(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}
