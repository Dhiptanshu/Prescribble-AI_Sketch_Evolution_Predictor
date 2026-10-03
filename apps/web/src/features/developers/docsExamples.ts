// The code shown in the developer docs. The request and response below are REAL: the response was captured from the live model,
// and an API test fails if the documented example ever stops matching what the API returns.
export const EXAMPLE_REQUEST = { strokes: [[[20, 200], [128, 40], [236, 200], [20, 200]]], top_k: 3 };

export const EXAMPLE_RESPONSE = {
  model: "v1",
  ink: 602.1,
  predictions: [
    { label: "pizza", probability: 0.72533 },
    { label: "star", probability: 0.2596 },
    { label: "house", probability: 0.01092 },
  ],
  inference_ms: 4.93,
};

const body = JSON.stringify(EXAMPLE_REQUEST);

export const snippets = (origin: string) => ({
  curl: `curl ${origin}/api/v1/predict \\
  -H "Authorization: Bearer $PRESCRIBBLE_KEY" \\
  -H "Content-Type: application/json" \\
  -d '${body}'`,

  python: `import os, requests

r = requests.post(
    "${origin}/api/v1/predict",
    headers={"Authorization": f"Bearer {os.environ['PRESCRIBBLE_KEY']}"},
    json=${body},
    timeout=10,
)
r.raise_for_status()
for guess in r.json()["predictions"]:
    print(guess["label"], guess["probability"])`,

  node: `// Node 18+ (server side only: secret keys must never reach a browser)
const res = await fetch("${origin}/api/v1/predict", {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.PRESCRIBBLE_KEY}\`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(${body}),
});
if (!res.ok) throw new Error((await res.json()).error.message);
console.log((await res.json()).predictions);`,
});

export const widgetSnippet = (origin: string) => `<div id="sketch"></div>
<script src="${origin}/widget/prescribble-widget.js"></script>
<script>
  Prescribble.mount("#sketch", {
    size: 360,
    onGuess: ({ top5 }) => console.log(top5[0].label, top5[0].probability),
  });
</script>`;

export const elementSnippet = (origin: string) => `<script src="${origin}/widget/prescribble-widget.js"></script>
<prescribble-canvas size="320" theme="auto"></prescribble-canvas>
<script>
  document.querySelector("prescribble-canvas")
    .addEventListener("guess", (e) => console.log(e.detail.top5[0]));
</script>`;

export const ERRORS: { status: number; code: string; meaning: string }[] = [
  { status: 401, code: "invalid_api_key", meaning: "The key is missing, malformed or revoked." },
  { status: 403, code: "browser_not_allowed", meaning: "The request came from a web page (it carried an Origin header). Secret keys are for servers; use the widget in pages." },
  { status: 422, code: "validation_error", meaning: "The body is not valid: coordinates must be 0 to 255, strokes need at least one point, top_k must be 1 to 10." },
  { status: 422, code: "too_complex", meaning: "The drawing has more strokes or points than the limits above." },
  { status: 429, code: "rate_limited", meaning: "Too many requests in a minute. Wait for the number of seconds in the Retry-After header." },
  { status: 429, code: "quota_exceeded", meaning: "The key used its requests for today. It resets at midnight UTC (see Retry-After)." },
  { status: 503, code: "model_unavailable", meaning: "The server could not load the model. Try again shortly." },
];
