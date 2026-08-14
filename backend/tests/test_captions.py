"""The fallback path is the app's safety net, so it gets the most attention."""
import pytest

from generate import captions


class TestFallbackLibrary:
    def test_maps_label_to_its_theme(self):
        top, bottom = captions.fallback_caption(["Dog", "Pet"])
        assert (top, bottom) in captions._THEMES["dog"]["captions"]

    def test_first_matching_label_wins_among_specific_themes(self):
        # Labels arrive confidence-sorted, so the strongest signal should win.
        top, bottom = captions.fallback_caption(["Cat", "Dog"])
        assert (top, bottom) in captions._THEMES["cat"]["captions"]

    def test_specific_theme_beats_a_more_confident_broad_one(self):
        """Real Rekognition output for a puppy photo, in confidence order.

        "Animal" outranks "Dog" by confidence, but a dog joke is the better
        caption, so the specific theme must win.
        """
        labels = ["Animal", "Canine", "Dog", "Mammal", "Pet", "Puppy", "Labrador Retriever"]
        assert captions._theme_for(labels) == "dog"
        assert captions.fallback_caption(labels, seed="x") in captions._THEMES["dog"]["captions"]

    def test_broad_theme_used_when_nothing_specific_matches(self):
        assert captions._theme_for(["Animal", "Wildlife", "Bird"]) == "animal"

    def test_broad_themes_are_flagged(self):
        for name in ("animal", "person", "indoors", "outdoors"):
            assert captions._THEMES[name].get("broad") is True

    def test_no_labels_uses_mystery_captions(self):
        assert captions.fallback_caption([]) in captions._MYSTERY_CAPTIONS

    def test_unknown_label_still_produces_a_caption(self):
        top, bottom = captions.fallback_caption(["Xylophone"])
        assert top and bottom
        assert "XYLOPHONE" in f"{top} {bottom}"

    def test_seed_makes_selection_deterministic(self):
        first = captions.fallback_caption(["Dog"], seed="abc")
        second = captions.fallback_caption(["Dog"], seed="abc")
        assert first == second

    @pytest.mark.parametrize("labels", [[], ["Dog"], ["Food"], ["Unknown Thing"], ["Person", "Face"]])
    def test_always_returns_two_usable_lines(self, labels):
        top, bottom = captions.fallback_caption(labels, seed="s")
        assert isinstance(top, str) and isinstance(bottom, str)
        assert (top + bottom).strip()
        assert len(top) <= captions.MAX_LINE_CHARS
        assert len(bottom) <= captions.MAX_LINE_CHARS

    def test_every_theme_is_reachable_and_well_formed(self):
        for name, theme in captions._THEMES.items():
            assert theme["labels"], f"{name} has no labels"
            assert theme["captions"], f"{name} has no captions"
            for top, bottom in theme["captions"]:
                assert len(top) <= captions.MAX_LINE_CHARS
                assert len(bottom) <= captions.MAX_LINE_CHARS


class TestBedrockParsing:
    def test_extracts_clean_json(self):
        assert captions._extract_pair('{"top":"A","bottom":"B"}') == ("A", "B")

    def test_extracts_json_wrapped_in_prose(self):
        raw = 'Sure! Here you go:\n{"top": "hello", "bottom": "world"}\nHope that helps.'
        assert captions._extract_pair(raw) == ("HELLO", "WORLD")

    def test_returns_none_for_unparseable(self):
        assert captions._extract_pair("no json at all") is None
        assert captions._extract_pair("") is None
        assert captions._extract_pair("{not valid json}") is None

    def test_clips_overlong_lines(self):
        long = "X" * 200
        top, _ = captions._extract_pair(f'{{"top":"{long}","bottom":"b"}}')
        assert len(top) <= captions.MAX_LINE_CHARS


class TestBuildCaption:
    """build_caption must never raise, whatever Bedrock does."""

    def test_uses_bedrock_when_it_succeeds(self, monkeypatch):
        monkeypatch.setattr(captions, "_invoke_bedrock", lambda labels: ("TOP", "BOTTOM"))
        assert captions.build_caption(["Dog"]) == ("TOP", "BOTTOM", "bedrock")

    def test_falls_back_when_bedrock_throttles(self, monkeypatch):
        """The exact failure this account hit: ThrottlingException."""
        def throttle(labels):
            raise Exception("ThrottlingException: Too many tokens per day")

        monkeypatch.setattr(captions, "_invoke_bedrock", throttle)
        top, bottom, source = captions.build_caption(["Dog"], seed="x")

        assert source == "fallback"
        assert (top, bottom) in captions._THEMES["dog"]["captions"]

    def test_falls_back_when_bedrock_denies_access(self, monkeypatch):
        def denied(labels):
            raise Exception("AccessDeniedException")

        monkeypatch.setattr(captions, "_invoke_bedrock", denied)
        assert captions.build_caption(["Cat"], seed="x")[2] == "fallback"

    def test_falls_back_on_unusable_response(self, monkeypatch):
        monkeypatch.setattr(captions, "_invoke_bedrock", lambda labels: None)
        assert captions.build_caption(["Food"], seed="x")[2] == "fallback"

    def test_retries_before_giving_up(self, monkeypatch):
        calls = []

        def flaky(labels):
            calls.append(1)
            raise Exception("boom")

        monkeypatch.setattr(captions, "_invoke_bedrock", flaky)
        captions.build_caption(["Dog"], seed="x")
        # BEDROCK_MAX_ATTEMPTS is 2 in the test environment.
        assert len(calls) == 2

    def test_recovers_on_a_later_attempt(self, monkeypatch):
        state = {"n": 0}

        def flaky(labels):
            state["n"] += 1
            if state["n"] == 1:
                raise Exception("transient")
            return ("OK", "GOOD")

        monkeypatch.setattr(captions, "_invoke_bedrock", flaky)
        assert captions.build_caption(["Dog"]) == ("OK", "GOOD", "bedrock")

    def test_fallback_with_no_labels_and_broken_bedrock(self, monkeypatch):
        """Worst case: Rekognition gave nothing and Bedrock is down."""
        monkeypatch.setattr(captions, "_invoke_bedrock", lambda labels: (_ for _ in ()).throw(Exception("down")))
        top, bottom, source = captions.build_caption([], seed="x")
        assert source == "fallback"
        assert (top, bottom) in captions._MYSTERY_CAPTIONS
