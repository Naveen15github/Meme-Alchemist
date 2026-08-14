"""Caption generation: Amazon Bedrock (Nova) first, local library as fallback.

The contract this module guarantees to its caller is simple and absolute:
``build_caption`` always returns a usable two-line meme caption. It never
raises because of a Bedrock problem. If the model is throttled, slow, denied,
or returns something unusable, we fall back to a label-keyed local library and
report ``source="fallback"`` so the event is visible in CloudWatch.
"""
import json
import random
import re
import time

import boto3
from botocore.config import Config as BotoConfig

from common import config, obs

# --------------------------------------------------------------------------
# Local fallback library
# --------------------------------------------------------------------------
# Each theme maps Rekognition label names (lowercased) to a set of top/bottom
# caption pairs. Rekognition labels are broad and predictable, which is what
# makes this approach hold up: "Dog", "Food", "Person", "Computer" etc. show
# up constantly across real photos.

_THEMES: dict[str, dict] = {
    "dog": {
        "labels": {"dog", "puppy", "canine", "pet", "hound", "labrador retriever", "golden retriever"},
        "captions": [
            ("I HAVE NO IDEA", "WHAT I'M DOING"),
            ("THEY SAID SIT", "I CHOSE VIOLENCE"),
            ("WHO'S A GOOD BOY?", "IT'S ME. I ASKED."),
            ("I ATE THE HOMEWORK", "AND I'D DO IT AGAIN"),
        ],
    },
    "cat": {
        "labels": {"cat", "kitten", "feline", "manx", "tabby", "siamese"},
        "captions": [
            ("I KNOCKED IT OVER", "AND I FEEL NOTHING"),
            ("YOU WORK FOR ME NOW", "THIS IS NOT A NEGOTIATION"),
            ("3 AM: THE ZOOMIES", "MUST BE HONORED"),
            ("I SAT ON YOUR LAPTOP", "IT WAS WARM. CASE CLOSED."),
        ],
    },
    "food": {
        "labels": {"food", "pizza", "burger", "dessert", "cake", "meal", "dish", "bread",
                   "sandwich", "noodle", "pasta", "sushi", "fruit", "vegetable", "snack"},
        "captions": [
            ("I SAID I'D SHARE", "I LIED"),
            ("CALORIES DON'T COUNT", "IF NOBODY SEES YOU"),
            ("MY MEAL PREP PLAN", "SURVIVED 11 MINUTES"),
            ("THIS IS A SALAD", "IF YOU BELIEVE HARD ENOUGH"),
        ],
    },
    "office": {
        "labels": {"computer", "laptop", "desk", "office", "monitor", "screen", "keyboard",
                   "electronics", "pc", "hardware", "workspace", "furniture"},
        "captions": [
            ("IT WORKED ON MY MACHINE", "SHIP IT"),
            ("I HAVE 47 TABS OPEN", "AND ZERO ANSWERS"),
            ("THIS MEETING", "COULD'VE BEEN AN EMAIL"),
            ("DAY 1 OF DEBUGGING", "THE BUG IS ME"),
        ],
    },
    "person": {
        "broad": True,
        "labels": {"person", "human", "face", "portrait", "selfie", "man", "woman", "people", "smile"},
        "captions": [
            ("PRETENDING TO LISTEN", "SINCE BIRTH"),
            ("I'M NOT ARGUING", "I'M EXPLAINING WHY I'M RIGHT"),
            ("MY FACE WHEN", "IT'S ONLY TUESDAY"),
            ("SOCIALLY BATTERED", "BUT PHOTOGENIC"),
        ],
    },
    "outdoors": {
        "broad": True,
        "labels": {"outdoors", "nature", "tree", "sky", "mountain", "beach", "water", "sea",
                   "forest", "grass", "plant", "landscape", "sunset", "cloud", "field"},
        "captions": [
            ("TOUCHED GRASS", "IMMEDIATELY REGRETTED IT"),
            ("NATURE IS BEAUTIFUL", "MY WIFI IS NOT"),
            ("I CAME FOR THE VIEW", "I STAYED FOR THE SNACKS"),
            ("OUT OF OFFICE", "PERMANENTLY, HOPEFULLY"),
        ],
    },
    "vehicle": {
        "labels": {"car", "vehicle", "automobile", "truck", "motorcycle", "bus", "transportation",
                   "bicycle", "bike", "wheel", "train", "airplane"},
        "captions": [
            ("GPS SAID TURN LEFT", "GPS HAS BETRAYED ME"),
            ("FUEL: EMPTY", "CONFIDENCE: FULL"),
            ("I'M NOT LOST", "I'M EXPLORING AGGRESSIVELY"),
            ("PARALLEL PARKING", "A CRIME AGAINST HUMANITY"),
        ],
    },
    "drink": {
        "labels": {"coffee", "drink", "beverage", "cup", "mug", "tea", "juice", "bottle", "glass"},
        "captions": [
            ("COFFEE NUMBER FOUR", "I CAN SEE SOUNDS NOW"),
            ("DO NOT TALK TO ME", "UNTIL THIS IS EMPTY"),
            ("MY PERSONALITY", "IS 90% CAFFEINE"),
            ("HYDRATION GOALS", "TECHNICALLY IT'S LIQUID"),
        ],
    },
    "indoors": {
        "broad": True,
        "labels": {"indoors", "room", "living room", "bedroom", "home decor", "couch", "chair",
                   "table", "kitchen", "interior design", "building", "house"},
        "captions": [
            ("I CLEANED ONE CORNER", "PHOTOGRAPHED IT FROM 9 ANGLES"),
            ("HOME SWEET HOME", "AND ALSO SWEET CHAOS"),
            ("I'LL TIDY UP LATER", "- ME, FOR THREE WEEKS"),
            ("MINIMALIST DESIGN", "I JUST CAN'T FIND ANYTHING"),
        ],
    },
    "animal": {
        "broad": True,
        "labels": {"animal", "bird", "wildlife", "horse", "fish", "insect", "mammal", "reptile"},
        "captions": [
            ("EVOLUTION GAVE ME THIS", "AND I'M USING IT WRONG"),
            ("I HAVE NO THOUGHTS", "ONLY VIBES"),
            ("NATURE'S FINEST WORK", "ABSOLUTELY UNHINGED"),
            ("BORN TO BE WILD", "FORCED TO BE PHOTOGENIC"),
        ],
    },
    "phone": {
        "labels": {"phone", "mobile phone", "cell phone", "camera", "photography"},
        "captions": [
            ("BATTERY AT 1%", "LIVING ON THE EDGE"),
            ("I TOOK 200 PHOTOS", "ALL OF THEM BLURRY"),
            ("SCREEN TIME REPORT", "A PERSONAL ATTACK"),
            ("JUST ONE MORE SCROLL", "- 4 HOURS AGO"),
        ],
    },
    "sport": {
        "labels": {"sport", "sports", "ball", "football", "soccer", "basketball", "fitness",
                   "gym", "exercise", "running", "team sport"},
        "captions": [
            ("I PLAY TO WIN", "I MOSTLY PLAY TO BREATHE"),
            ("GYM DAY ONE", "ALSO GYM DAY LAST"),
            ("MY CARDIO ROUTINE", "RUNNING LATE"),
            ("ATHLETIC PERFORMANCE", "SPIRITUALLY, AT LEAST"),
        ],
    },
    "clothing": {
        "labels": {"clothing", "apparel", "shoe", "footwear", "hat", "shirt", "dress", "fashion", "accessories"},
        "captions": [
            ("DRESSED FOR SUCCESS", "SUCCESS DIDN'T SHOW UP"),
            ("THIS OLD THING?", "I PLANNED IT FOR SIX DAYS"),
            ("FASHION IS PAIN", "SO ARE THESE SHOES"),
            ("OUTFIT: IMMACULATE", "DESTINATION: THE FRIDGE"),
        ],
    },
}

# Used when Rekognition returns nothing recognisable at all.
_MYSTERY_CAPTIONS = [
    ("SCIENCE CANNOT EXPLAIN", "WHATEVER THIS IS"),
    ("I HAVE QUESTIONS", "THE PHOTO HAS NO ANSWERS"),
    ("UNIDENTIFIED OBJECT", "PROBABLY FRIENDLY"),
    ("THE AI LOOKED AT THIS", "AND QUIETLY GAVE UP"),
    ("MYSTERIOUS. BOLD.", "COMPLETELY UNREADABLE."),
]

# Used when we do have labels but none map to a known theme.
_GENERIC_TEMPLATES = [
    ("NOBODY:", "ABSOLUTELY NOBODY: {label}"),
    ("ME EXPLAINING {label}", "TO SOMEONE WHO DIDN'T ASK"),
    ("THE AI SAW {label}", "AND IT HAS OPINIONS"),
    ("{label} ENERGY", "AND HONESTLY? RESPECT."),
    ("I CAME HERE FOR {label}", "I STAYED FOR THE CHAOS"),
]

MAX_LINE_CHARS = 42


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _theme_for(labels: list[str]) -> str | None:
    """Pick the theme to joke about, preferring specific subjects.

    Labels arrive confidence-sorted, but Rekognition's most confident label is
    often its most generic: a photo of a puppy comes back as
    ``Animal, Canine, Dog, Pet, Labrador Retriever``. Taking the first match
    would caption it as a generic "animal" when a dog joke was available, so
    themes flagged ``broad`` only win if nothing specific matched.
    """
    broad_match = None
    for label in labels:
        low = label.lower()
        for theme_name, theme in _THEMES.items():
            if low not in theme["labels"]:
                continue
            if not theme.get("broad"):
                return theme_name
            if broad_match is None:
                broad_match = theme_name
    return broad_match


def fallback_caption(labels: list[str], seed: str | None = None) -> tuple[str, str]:
    """Pick a caption from the local library. Never fails.

    ``seed`` makes selection deterministic per image, so re-running the same
    upload gives the same joke instead of a different one each retry.
    """
    rng = random.Random(seed) if seed else random.Random()

    theme = _theme_for(labels)
    if theme:
        top, bottom = rng.choice(_THEMES[theme]["captions"])
        return top, bottom

    if labels:
        template = rng.choice(_GENERIC_TEMPLATES)
        label = labels[0].upper()
        return _clip(template[0].format(label=label)), _clip(template[1].format(label=label))

    return rng.choice(_MYSTERY_CAPTIONS)


def _clip(text: str, limit: int = MAX_LINE_CHARS) -> str:
    text = _norm(text).upper()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------
# Bedrock path
# --------------------------------------------------------------------------

_PROMPT = """You write captions for classic two-line internet memes.

An image recognition service looked at a photo and detected these things:
{labels}

Write ONE short, funny, good-natured meme caption about that subject.

Rules:
- Exactly two lines: a setup line and a punchline.
- Each line is at most 40 characters.
- ALL CAPS. No hashtags, no emoji, no quotation marks, no explanation.
- Keep it playful and safe for everyone. Never insult anyone's appearance.

Respond with ONLY this JSON and nothing else:
{{"top": "SETUP LINE", "bottom": "PUNCHLINE"}}"""

_bedrock_client = None


def _client():
    """Lazily build the Bedrock client so tests can import without AWS calls."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=config.BEDROCK_REGION,
            config=BotoConfig(
                read_timeout=config.BEDROCK_READ_TIMEOUT_SECONDS,
                connect_timeout=3,
                retries={"max_attempts": 1},  # we own the retry loop
            ),
        )
    return _bedrock_client


def _extract_pair(raw: str) -> tuple[str, str] | None:
    """Pull {"top","bottom"} out of a model response, tolerating stray prose."""
    if not raw:
        return None
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    top, bottom = _norm(str(data.get("top", ""))), _norm(str(data.get("bottom", "")))
    if not top and not bottom:
        return None
    return _clip(top), _clip(bottom)


def _invoke_bedrock(labels: list[str]) -> tuple[str, str] | None:
    """One Bedrock call. Returns None on any unusable outcome."""
    body = {
        "messages": [
            {"role": "user", "content": [{"text": _PROMPT.format(labels=", ".join(labels) or "an unclear object")}]}
        ],
        "inferenceConfig": {"maxTokens": 120, "temperature": 0.9, "topP": 0.9},
    }
    response = _client().invoke_model(
        modelId=config.BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload = json.loads(response["body"].read())
    text = payload["output"]["message"]["content"][0]["text"]
    return _extract_pair(text)


def build_caption(labels: list[str], seed: str | None = None) -> tuple[str, str, str]:
    """Return ``(top, bottom, source)`` where source is "bedrock" or "fallback".

    This function is the single point that guarantees the demo never breaks.
    """
    last_error = None
    for attempt in range(1, config.BEDROCK_MAX_ATTEMPTS + 1):
        try:
            pair = _invoke_bedrock(labels)
            if pair and (pair[0] or pair[1]):
                obs.log("bedrock_ok", attempt=attempt, model=config.BEDROCK_MODEL_ID)
                return pair[0], pair[1], "bedrock"
            last_error = "unusable_response"
            obs.warn("bedrock_unusable_response", attempt=attempt)
        except Exception as exc:  # noqa: BLE001 - any failure must degrade, not crash
            last_error = f"{type(exc).__name__}: {exc}"
            obs.warn("bedrock_attempt_failed", attempt=attempt, errorType=type(exc).__name__,
                     error=str(exc)[:300])

        if attempt < config.BEDROCK_MAX_ATTEMPTS:
            # Exponential backoff with jitter, capped so we stay inside the
            # Lambda timeout and the user's patience.
            delay = min(config.BEDROCK_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), 2.0)
            time.sleep(delay + random.random() * 0.2)

    top, bottom = fallback_caption(labels, seed=seed)
    obs.warn("fallback_used", reason=str(last_error)[:300], labels=labels[:5],
             theme=_theme_for(labels) or ("generic" if labels else "mystery"))
    return top, bottom, "fallback"
