// Rough token estimation without calling an API.
// Arabic ≈ 2 chars/token, Latin ≈ 4 chars/token; +4 overhead per message.

export function estimateTokens(text: string): number {
  const arabicCount = (text.match(/[؀-ۿݐ-ݿ]/g) ?? []).length;
  const otherCount = text.length - arabicCount;
  return Math.max(1, Math.ceil(arabicCount / 2 + otherCount / 4) + 4);
}

export function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}
