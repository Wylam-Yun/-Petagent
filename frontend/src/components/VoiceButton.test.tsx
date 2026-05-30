import { act } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { VoiceButton } from "./VoiceButton";
import type { VoiceChatResponse } from "../pet/types";

const voiceResponse: VoiceChatResponse = {
  reply: "辛苦啦。豆豆陪你缓一下。",
  mood: "concerned",
  face_type: "concerned",
  animation: "tilt",
  vibration: "light",
  voice_url: null,
  audio_job_id: "aud-test",
  user_text: "我今天好累",
  audio_understanding: {
    user_text: "我今天好累",
    detected_emotion: "tired",
    tone_notes: "语气低",
    non_verbal: "叹气",
    confidence: 0.82
  },
  pet_state: {
    name: "豆豆",
    mood: "concerned",
    energy: 72,
    intimacy: 41,
    hunger: 30,
    cleanliness: 85,
    loneliness: 31,
    sleepiness: 15
  },
  runtime: { event_id: "evt-voice", skills_used: [] }
};

function recorderFactory(blob = new Blob(["voice"], { type: "audio/webm" })) {
  return vi.fn().mockResolvedValue({
    stop: vi.fn().mockResolvedValue(blob),
    cancel: vi.fn(),
    finished: Promise.resolve(blob)
  });
}

describe("VoiceButton", () => {
  test("tap starts recording, second tap uploads, then waits for voice", async () => {
    const onPhaseChange = vi.fn();
    const onVoiceResponse = vi.fn();
    const uploadVoice = vi.fn().mockResolvedValue(voiceResponse);

    render(
      <VoiceButton
        disabled={false}
        phase="idle"
        recorderFactory={recorderFactory()}
        thinkingMode={false}
        uploadVoice={uploadVoice}
        onError={vi.fn()}
        onPhaseChange={onPhaseChange}
        onVoiceResponse={onVoiceResponse}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "点一下说话" }));
    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("listening"));

    fireEvent.click(screen.getByRole("button", { name: "点一下发送" }));

    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("thinking"));
    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("waiting_voice"));
    expect(uploadVoice).toHaveBeenCalledTimes(1);
    expect(uploadVoice).toHaveBeenCalledWith(expect.any(Blob), { thinkingMode: false });
    expect(onVoiceResponse).toHaveBeenCalledWith(voiceResponse);
  });

  test("structured ASR failure shows error without applying voice response", async () => {
    const onError = vi.fn();
    const onPhaseChange = vi.fn();
    const onVoiceResponse = vi.fn();
    const uploadVoice = vi.fn().mockResolvedValue({
      ...voiceResponse,
      ok: false,
      reply: "",
      audio_job_id: null,
      error_class: "asr_empty",
      user_text: "",
      voice_route: {
        requested: "auto",
        selected: "fast_reply",
        thinking_mode: false,
        asr_provider: "mock_asr",
        asr_error_code: "asr_empty",
        brain_provider: "mock_fast_llm",
        fallback_reason: "asr_empty",
        timings_ms: {}
      }
    });

    render(
      <VoiceButton
        disabled={false}
        phase="idle"
        recorderFactory={recorderFactory()}
        thinkingMode={false}
        uploadVoice={uploadVoice}
        onError={onError}
        onPhaseChange={onPhaseChange}
        onVoiceResponse={onVoiceResponse}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "点一下说话" }));
    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("listening"));
    fireEvent.click(screen.getByRole("button", { name: "点一下发送" }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("没识别到有效语音。"));
    expect(onVoiceResponse).not.toHaveBeenCalled();
    expect(onPhaseChange).toHaveBeenCalledWith("error");
    expect(onPhaseChange).not.toHaveBeenCalledWith("waiting_voice");
  });

  test("tap during upload locally cancels the pending response without posting again", async () => {
    let resolveUpload: (value: VoiceChatResponse) => void = () => undefined;
    const uploadPromise = new Promise<VoiceChatResponse>((resolve) => {
      resolveUpload = resolve;
    });
    const uploadVoice = vi.fn().mockReturnValue(uploadPromise);
    const createRecorder = recorderFactory();

    render(
      <VoiceButton
        disabled={false}
        phase="idle"
        recorderFactory={createRecorder}
        thinkingMode={true}
        uploadVoice={uploadVoice}
        onError={vi.fn()}
        onPhaseChange={vi.fn()}
        onVoiceResponse={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "点一下说话" }));
    await waitFor(() => expect(createRecorder).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "点一下发送" }));
    await waitFor(() => expect(uploadVoice).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "取消发送" }));
    resolveUpload(voiceResponse);

    await act(async () => {
      await Promise.resolve();
    });

    expect(createRecorder).toHaveBeenCalledTimes(1);
    expect(uploadVoice).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "点一下说话" })).toBeInTheDocument();
  });

  test("cancel button discards active recording", async () => {
    const session = {
      stop: vi.fn().mockResolvedValue(new Blob(["voice"], { type: "audio/webm" })),
      cancel: vi.fn(),
      finished: Promise.resolve(new Blob(["voice"], { type: "audio/webm" }))
    };
    const createRecorder = vi.fn().mockResolvedValue(session);
    const uploadVoice = vi.fn();
    const onError = vi.fn();
    const onPhaseChange = vi.fn();

    render(
      <VoiceButton
        disabled={false}
        phase="idle"
        recorderFactory={createRecorder}
        thinkingMode={false}
        uploadVoice={uploadVoice}
        onError={onError}
        onPhaseChange={onPhaseChange}
        onVoiceResponse={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "点一下说话" }));
    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("listening"));
    fireEvent.click(screen.getByRole("button", { name: "取消录音" }));

    expect(uploadVoice).not.toHaveBeenCalled();
    expect(session.cancel).toHaveBeenCalled();
    expect(onPhaseChange).toHaveBeenCalledWith("idle");
  });

  test("tap during playback phases interrupts before recording", async () => {
    const onInterrupt = vi.fn();
    const onPhaseChange = vi.fn();
    const createRecorder = recorderFactory();

    render(
      <VoiceButton
        disabled={false}
        phase="speaking"
        recorderFactory={createRecorder}
        thinkingMode={false}
        uploadVoice={vi.fn()}
        onError={vi.fn()}
        onInterrupt={onInterrupt}
        onPhaseChange={onPhaseChange}
        onVoiceResponse={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "打断并说话" }));

    expect(onInterrupt).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(createRecorder).toHaveBeenCalledTimes(1));
    expect(onPhaseChange).toHaveBeenCalledWith("listening");
  });

  test("shows a recoverable message when voice upload times out", async () => {
    const onError = vi.fn();
    render(
      <VoiceButton
        disabled={false}
        phase="idle"
        recorderFactory={recorderFactory()}
        thinkingMode={false}
        uploadVoice={vi.fn().mockRejectedValue(new Error("request timeout"))}
        onError={onError}
        onPhaseChange={vi.fn()}
        onVoiceResponse={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "点一下说话" }));
    await waitFor(() => screen.getByRole("button", { name: "点一下发送" }));
    fireEvent.click(screen.getByRole("button", { name: "点一下发送" }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("豆豆还在路上卡住了，再点一下试试。"));
  });
});
