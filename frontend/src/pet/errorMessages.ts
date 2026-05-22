/**
 * Maps backend error_class to user-friendly bubble text and mood.
 * Used when API responses include an error_class field.
 */

const ERROR_BUBBLE_MAP: Record<string, { text: string; mood: "tired" | "concerned" }> = {
  provider_auth_failed: {
    text: "Momo 连不上脑子了，主人检查一下配置？",
    mood: "concerned",
  },
  provider_timeout: {
    text: "Momo 想太久了，网络可能不太给力。",
    mood: "tired",
  },
  provider_unavailable: {
    text: "Momo 的脑子暂时休息了，等一下再试试。",
    mood: "tired",
  },
  provider_quota: {
    text: "Momo 今天想太多啦，额度用完了。",
    mood: "tired",
  },
  provider_bad_response: {
    text: "Momo 收到了奇怪的信号，再试一次？",
    mood: "concerned",
  },
  provider_network_error: {
    text: "Momo 的网络断了一下，等会儿再试试。",
    mood: "concerned",
  },
  server_busy: {
    text: "Momo 忙不过来啦，稍等一下再试。",
    mood: "tired",
  },
  shutting_down: {
    text: "Momo 要休息一下，等会儿再来找我。",
    mood: "tired",
  },
};

const DEFAULT_ERROR = {
  text: "Momo 刚刚没接稳，但还在这儿。",
  mood: "concerned" as const,
};

export function getErrorBubble(
  errorClass: string | null | undefined
): { text: string; mood: "tired" | "concerned" } {
  if (!errorClass) return DEFAULT_ERROR;
  return ERROR_BUBBLE_MAP[errorClass] ?? DEFAULT_ERROR;
}
