export type Mood =
  | "idle"
  | "happy"
  | "sad"
  | "sleepy"
  | "tired"
  | "angry"
  | "shy"
  | "thinking"
  | "concerned"
  | "excited"
  | "lonely";

export type AnimationName =
  | "breathing"
  | "bounce"
  | "droop"
  | "slowBlink"
  | "shake"
  | "wiggle"
  | "blink"
  | "tilt"
  | "jump"
  | "small";

export type PetEventType =
  | "pet_head"
  | "poke_face"
  | "hug"
  | "pet_pat"
  | "praise_momo"
  | "feed_momo"
  | "stay_with_me"
  | "comfort_me"
  | "encourage_me"
  | "listen_to_me"
  | "tuck_in"
  | "clean_face"
  | "quiet_company"
  | "take_a_break"
  | "play_with_momo"
  | "debug_happy"
  | "debug_sleepy"
  | "debug_angry";

export type InteractionDefinition = {
  event_id: PetEventType;
  label: string;
  group: "pet_care" | "emotional_companion" | "debug" | string;
  default_mood: Mood;
  default_animation: AnimationName;
  state_semantics: Record<string, string>;
};

export type StateAffect = {
  interaction_tone: string;
  pet_effort: string;
  emotional_effect: string;
  reason: string;
};

export type PetUIPhase =
  | "idle"
  | "listening"
  | "thinking"
  | "waiting_voice"
  | "speaking"
  | "audio_error"
  | "error";
export type VoiceMode = "fast" | "thinking";

export type PetState = {
  schema_version?: string;
  name: string;
  mood: Mood;
  energy: number;
  intimacy: number;
  hunger: number;
  cleanliness: number;
  loneliness: number;
  sleepiness: number;
  mode?: string;
  last_interaction_at?: string;
  updated_at?: string;
};

export type BehaviorStep = {
  action: string;
  slot?: string;
  duration_ms?: number;
};

export type PetResponse = {
  schema_version?: string;
  reply: string;
  mood: Mood;
  face_type: Mood;
  animation: AnimationName;
  vibration: "none" | "light" | "medium";
  voice_url: string | null;
  audio_job_id?: string | null;
  state_affect?: StateAffect;
  pet_state: PetState;
  runtime: {
    event_id: string;
    skills_used: unknown[];
  };
  action?: string;
  route?: string;
  memory_ack_hint?: string;
  behavior_intent?: string;
  behavior_plan?: BehaviorStep[];
  voice_style?: string;
};

export type AudioJob = {
  job_id: string;
  status: "pending" | "ready" | "failed" | "expired" | "superseded" | "failed_runtime_restart" | "failed_shutdown";
  voice_url: string | null;
  error: string | null;
  error_class?: string | null;
  created_at: string;
  updated_at: string;
};

export type DeviceStatePayload = {
  battery: number | null;
  is_charging: boolean | null;
};

export type ProactiveResponse =
  | ({ active: true } & PetResponse)
  | { active: false };

export type AudioUnderstanding = {
  user_text: string;
  detected_emotion:
    | "calm"
    | "tired"
    | "happy"
    | "sad"
    | "angry"
    | "anxious"
    | "uncertain";
  tone_notes: string;
  non_verbal: string;
  confidence: number;
};

export type VoiceChatResponse = PetResponse & {
  user_text: string;
  audio_understanding: AudioUnderstanding;
  voice_route?: VoiceRouteInfo;
  error_class?: string | null;
  activation?: {
    type: "wake" | "exit";
    active: boolean;
    session_id: string | null;
  };
};

export type TextChatResponse = PetResponse & {
  user_text: string;
  text_route: {
    selected: "fast" | "slow";
    thinking_mode: boolean;
    brain_provider: string;
    timings_ms: Record<string, number>;
  };
  error_class?: string | null;
  activation?: {
    type: "wake" | "exit";
    active: boolean;
    session_id: string | null;
  };
};

export type VoiceRouteInfo = {
  requested: "auto" | "fast" | "slow";
  selected: "fast" | "slow" | "fallback";
  thinking_mode: boolean;
  asr_provider: string;
  brain_provider: string;
  fallback_reason: string;
  timings_ms: Record<string, number>;
};

export type ActivationResponse = PetResponse & {
  active: boolean;
  session_id: string | null;
};
