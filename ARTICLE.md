# Weekend Creative Challenge: Meme Alchemist

**Tag:** `#creative-expression`

_Drop in a photo. Amazon Rekognition works out what's in it, Amazon Bedrock writes the joke, and you get a meme back in about four seconds._

> 📸 **[Insert `screenshots/thumbnail.png` here]**

---

## Vision & What the App Does

I wanted to build something that makes a stranger laugh within ten seconds of landing on it. No sign-up, no instructions, no tutorial. Drop in a photo, get a meme.

**Meme Alchemist** does exactly one thing, and the thing it does is specific to *your* photo. It isn't a template generator where your image gets pasted into a pre-made joke. It looks at what's actually in the picture and writes a caption about that. Upload your dog looking guilty on a wooden floor and you get a dog joke. Upload a screenshot of a dense engineering blog post and you get a joke about meetings that could have been emails. (That one's in the live gallery — I didn't plan it, the app just did it.)

The creative output is a classic two-line meme: white block capitals with a heavy black outline, stamped top and bottom, ready to download or share.

Three steps, a few seconds:

1. **It looks at your photo.** Amazon Rekognition returns labels — `Dog`, `Pet`, `Canine`, `Labrador Retriever`, `Wood`.
2. **It writes a joke.** Those labels go to Amazon Bedrock running Amazon Nova Lite, prompted for a two-line setup-and-punchline caption.
3. **It stamps the meme.** Pillow renders the caption onto the image in the lettering everyone recognises, and the result lands in S3 behind CloudFront.

There's an animated gallery of everything that's been brewed, a lightbox, and one-click download and copy-link buttons.

But the design goal I actually cared about wasn't the pipeline. It was this: **the app must never show a broken state.** That turned out to matter far more than I expected, and it's the real story of this build.

> 📸 **[Insert `screenshots/landing.png` here]**

---

## How I Built It

The stack is deliberately small: a React frontend on CloudFront, three Python Lambdas behind an HTTP API, and Terraform for all of it. I gave myself a rule up front — build the smallest version that is genuinely reliable, then stop. No auth, no accounts, no admin panel. Every feature I skipped is a feature that can't break during judging.

### Uploads bypass the API entirely

API Gateway caps payloads at 10 MB, and base64 encoding inflates a file by about a third — so an 8 MB phone photo wouldn't fit. Instead, the browser asks for a presigned S3 URL and PUTs the bytes straight to the bucket. The `generate` Lambda then works from the object key alone.

This keeps large images off API Gateway completely, and the request that does the real work is a few dozen bytes of JSON.

### Pillow on Lambda, without Docker

Pillow needs native binaries compiled for the Lambda runtime. The usual advice is to build it in a Docker container, but `pip` can fetch prebuilt manylinux wheels for a target platform directly:

```bash
pip install --platform manylinux2014_x86_64 --implementation cp \
            --python-version 3.12 --only-binary=:all: \
            --target build/python Pillow==11.3.0
```

That one command builds the layer identically on Windows, macOS or Linux with no Docker daemon running — which mattered, because Docker Desktop was installed on my machine but its daemon wasn't up. The build script then *verifies* that `PIL/*x86_64-linux-gnu.so` actually exists and refuses to continue if not, so a silently-wrong host build can never reach Lambda.

One licensing detail: Impact is the classic meme typeface but it's proprietary and can't be redistributed inside a deployment package. I used **Anton** (SIL Open Font License) instead — an open condensed grotesque with nearly identical presence.

### The challenge that shaped everything: Bedrock was throttled

Early in the build, my first real call to Bedrock came back:

```
ThrottlingException: Too many tokens per day, please wait before trying again.
```

My account had hit its **daily token quota** — across Nova Lite, Micro *and* Pro. This is worth being precise about, because it cost me time to work out: it is **not** a permissions problem. A permissions problem returns `AccessDeniedException` and is fixed in the Bedrock console. This was a quota that resets on a rolling 24-hour basis, and no amount of clicking "enable model access" would have helped.

If my whole app had hung off a single Bedrock call, my demo would have been a spinner and an error toast.

So captioning has two tiers, and the function that owns it makes exactly one promise: **it never raises because of a Bedrock problem.**

When Bedrock is throttled, denied, slow, or returns something unparseable, the app falls back to a local caption library keyed on the Rekognition labels — 13 themes (dog, cat, food, office, person, outdoors, vehicle, drink, sport…), each with hand-written captions. Because the fallback is keyed on the *labels*, the joke still responds to your actual photo instead of reading like a generic error message. There are three tiers:

1. **Theme match** — a label maps to a theme, you get that theme's joke.
2. **Generic template** — labels exist but none map, so the top label gets interpolated into a template.
3. **Mystery** — Rekognition found nothing, so you get a self-aware "the AI looked at this and quietly gave up" caption.

Selection is seeded with the meme's UUID, so the same image always produces the same joke rather than changing on every retry.

Here's the honest outcome: **the fallback path was the live path for this entire build, and it still is as I publish this.** All 11 memes in the live gallery were written by the local library. The app never showed an error once. When the quota resets, it switches back to Bedrock automatically — no redeploy, no config change.

Every fallback logs a structured `fallback_used` event with the reason, and the API returns `captionSource: "bedrock" | "fallback"` so the UI can be honest about which path ran. A silent fallback is a bug you discover months later.

I wrote tests for exactly this. The suite simulates a Bedrock throttle, a Rekognition outage, and both failing simultaneously, asserting each time that a valid, downloadable meme still comes back. **115 tests in total — 80 backend (pytest + moto), 35 frontend (Vitest).**

### A preflight script that runs before Terraform touches anything

`./scripts/preflight-check.sh` checks credentials, verifies the region actually offers Nova, and — the one that catches people — makes a **real `InvokeModel` call** to see whether model access is genuinely enabled. Listing a model does not mean you can invoke it.

Crucially, it treats the two failure modes differently. `AccessDeniedException` is a **blocking failure** that prints the exact console URL and steps. `ThrottlingException` is a **warning** that explicitly says deployment is safe, because the app handles it. Conflating those two would have sent me to the console to fix something that was never broken.

### The bug I only found by looking at the output

My first end-to-end test passed. Every assertion was green. Then I actually opened the generated meme, and the bottom caption was clipped by the edge of the image.

I'd calculated line height from the bounding box of the string `"AY"` — which has no descenders, so it measured short. Multi-line bottom captions ran off the frame. The fix was to use `font.getmetrics()` (ascent + descent) and to account for the stroke width in both wrapping and positioning.

The same look-at-it pass caught a second issue: Rekognition returned `Animal` with higher confidence than `Dog`, so a puppy photo got the generic animal joke when a dog joke was available. Broad themes now only win if nothing more specific matched. Both fixes have regression tests, including all-descender strings like `"GYQPJ"`.

> 📸 **[Insert `screenshots/gallery.png` here]**

---

## AWS Services Used / Architecture Overview

> 📸 **[Insert `screenshots/arch.png` here]**

The flow, end to end:

1. The browser loads the React app from **CloudFront**.
2. It asks **API Gateway** for an upload URL; the `presign` **Lambda** returns a presigned S3 URL.
3. The browser PUTs the image straight to the uploads bucket in **S3**.
4. It calls `POST /generate`. That Lambda reads the image, calls **Rekognition** for labels, sends those labels to **Bedrock** for a caption — falling back to the local library if Bedrock is unavailable — renders the meme with Pillow, writes it to S3 and records it in **DynamoDB**.
5. `GET /gallery` reads recent memes back from DynamoDB.
6. The finished meme is served through the same CloudFront distribution.

**Every AWS service used, and what it does:**

| Service | Role in this app |
|---|---|
| **Amazon S3** | Three private buckets: raw uploads (auto-expiring after 7 days), finished memes, and the built React app. |
| **AWS Lambda** | Three Python 3.12 functions — `presign` issues upload URLs, `generate` runs the whole pipeline, `gallery` lists recent memes. |
| **Amazon API Gateway** | HTTP API exposing the three routes, with CORS and a 10 req/s throttle so a stray script can't run up a bill. |
| **Amazon Rekognition** | `DetectLabels` identifies what's actually in the photo — this is what makes the joke about *your* image. |
| **Amazon Bedrock (Nova Lite)** | Turns those labels into a two-line meme caption, with retries and exponential backoff. |
| **Amazon DynamoDB** | One table recording every meme, with a constant-partition GSI so the gallery reads newest-first via a Query rather than a Scan. |
| **Amazon CloudFront** | A single distribution serving both the app and the memes from private buckets via Origin Access Control — so no bucket is ever public, and image URLs are same-origin (no CORS on download or share). |
| **Amazon CloudWatch Logs** | Structured JSON logs with request IDs, including the `fallback_used` event. |
| **AWS IAM** | One least-privilege role per Lambda — `presign` can only write under `uploads/`, `gallery` can only query the table. |

Everything is defined in Terraform. `./scripts/deploy.sh` builds the Pillow layer, applies the infrastructure, smoke-tests the API *before* building the frontend against it, then syncs and invalidates CloudFront. It's idempotent — a second run reports no drift.

On cost: uploads expire after 7 days, log retention is 14 days, CloudFront runs on `PriceClass_100`, and DynamoDB is on-demand. A weekend of demoing costs a few cents, and `./scripts/destroy.sh` takes it to zero.

---

## What I Learned

**A managed model is a dependency, and dependencies fail.** I had internalised this for databases and never really applied it to an LLM call. Hitting a daily token quota on day one turned an abstract "add a fallback someday" task into the thing that saved the project. Designing the degraded path *first* — and deciding a slightly less clever joke always beats an error screen — made every later decision easier.

**"Enabled" and "invokable" are different things.** `ListFoundationModels` will happily list models your account cannot call. Only a real `InvokeModel` tells you the truth. And distinguishing `AccessDeniedException` from `ThrottlingException` is the difference between "stop, go fix this in the console" and "carry on, the app handles it."

**Degrade, but be honest about it.** The temptation is to hide the fallback so the app looks smarter. Returning `captionSource` and showing a small note when the library wrote the caption costs nothing and makes the system debuggable.

**Green tests are not the same as a working product.** My clipped-caption bug passed every assertion I had, because I had asserted "a valid JPEG came back" and not "the text is inside the image." Opening the actual output found in five seconds what the test suite structurally could not. I now have pixel-level regression tests for it — but only because I looked.

**Cross-platform shell scripts punish assumptions.** Two bugs cost me real time and both were mine. The AWS CLI is a native Windows binary and cannot read a Git Bash `/tmp` path. And `grep -q` inside a pipeline under `set -o pipefail` reports a *successful* match as a failure — grep short-circuits on the first match, the writer dies of SIGPIPE, and pipefail propagates that. My preflight script confidently told me Nova wasn't available in `us-east-1`. It was. It had been all along.

**Rekognition's vocabulary is what makes the fallback feel intelligent.** Its labels are broad and predictable — real photos reliably produce `Dog`, `Person`, `Food`, `Computer`. That predictability is exactly what lets a static caption library still feel responsive to the image in front of it. The fallback isn't a lesser version of the AI path; it's a different way of being specific.

---

## Link to App or Repo

**🔗 Live app:** https://d2ruu5tx6ircv8.cloudfront.net

**💻 Source:** https://github.com/Naveen15github/Meme-Alchemist

The repo has everything: Terraform for the full stack, the three Lambdas, the React frontend, all 115 tests, and the scripts. `./scripts/preflight-check.sh` verifies your account can run it, `./scripts/bootstrap.sh` creates the state bucket, `./scripts/deploy.sh` stands the whole thing up, and `./scripts/destroy.sh` takes it back to zero cost.

Go make something silly with it. 🧪
