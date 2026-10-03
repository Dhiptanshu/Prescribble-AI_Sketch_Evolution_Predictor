const dateFmt = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" });

export const formatDate = (iso: string) => dateFmt.format(new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z"));
export const percent = (x: number) => `${Math.round(x * 100)}%`;

/** One honest sentence about how early the AI got a labelled drawing. */
export function recognitionText(label: string | null, recognisedAt: number | null, aiGuess: string): string {
  if (!label) return `AI's final guess: ${aiGuess}`;
  if (recognisedAt != null) return `AI had it by ${percent(recognisedAt)} of the ink`;
  return aiGuess === label ? "AI named it only at the end" : `AI never got it (it said ${aiGuess})`;
}
