/** One point of the prediction history: how much ink was down, and the AI's ranked guesses (class indexes, best first). */
export interface RankPoint { ink: number; order: number[] }

/**
 * The fraction of the final ink at which the AI's #1 guess became `labelIdx` and then stayed that way until the end.
 * Returns null when the AI's final #1 guess is not the label (it never got it, or lost it again).
 * Based on the predictions that were actually run while the user drew, so it is exact for those moments and coarse between them.
 */
export function recognisedAt(history: RankPoint[], labelIdx: number, finalInk: number): number | null {
  if (!history.length || finalInk <= 0 || labelIdx < 0) return null;
  let i = history.length;
  while (i > 0 && history[i - 1]!.order[0] === labelIdx) i--;
  if (i === history.length) return null;
  return Math.min(1, history[i]!.ink / finalInk);
}
