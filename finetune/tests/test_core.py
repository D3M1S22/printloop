import os
import re
import tempfile

os.environ.setdefault("FDMFT_DATA_DIR", tempfile.mkdtemp(prefix="fdmft-test-"))

from fdmft.build import session_groups, split_of  # noqa: E402
from fdmft.prepare import near_duplicate_groups  # noqa: E402
from fdmft.prompt import messages, output_schema, parse, target  # noqa: E402
from fdmft.sources import RawItem, one_per_original, registry, roboflow_stem  # noqa: E402
from fdmft.taxonomy import load, map_labels, normalize_label  # noqa: E402
from fdmft.train import lora_targets, stratified_subset  # noqa: E402


def test_labels():
    assert normalize_label(" Layer Shifting ") == "layer_shifting"
    assert map_labels(["Stringing", "zits"]) == (["stringing", "blobs"], [], [])
    assert map_labels(["Good"]) == (["none"], [], [])
    assert map_labels(["good", "spaghetti"])[0] == ["spaghetti"]
    assert map_labels(["part", "Spagheti"])[0] == ["spaghetti"]
    assert map_labels(["error extrusion"]) == ([], ["error extrusion"], [])
    assert map_labels(["boh"]) == ([], [], ["boh"])


def test_order_and_primary():
    tax = load()
    assert tax.primary(["stringing", "spaghetti"]) == "spaghetti"
    assert tax.primary([]) == "none"


def test_sources_licences():
    tax = load()
    for src in registry().values():
        if src.use == "train":
            assert src.license in tax.licenses_train, src.id


def test_near_duplicates():
    hashes = {"a": "ffffffffffffffff", "b": "fffffffffffffff0", "c": "0000000000000000", "d": "000000000000003f"}
    assert near_duplicate_groups(hashes, 4) == [["a", "b"]]
    assert near_duplicate_groups(hashes, 4, can_merge=lambda a, b, d: False) == []


def test_roboflow_one_per_original():
    assert roboflow_stem("train/abc_jpg.rf.549c891f051b38ac8300be431e761f8c.jpg") == "abc_jpg"

    def it(key):
        return RawItem(source="rf", key=key, raw_labels=["x"], group_id="rf:project", load=bytes)
    items = [it("train/a_jpg.rf.1111111111111111aaaa.jpg"), it("valid/a_jpg.rf.2222222222222222bbbb.jpg"),
             it("train/b_jpg.rf.4444444444444444dddd.jpg")]
    out = {i.group_id: i for i in one_per_original(iter(items))}
    assert out["rf:a_jpg"].key.startswith("valid/") and out["rf:a_jpg"].meta["copies"] == 2


def test_build_helpers():
    recs = [{"id": "a", "key": "W/Image_20231128195336980.jpg"}, {"id": "b", "key": "W/Image_20231128195406987.jpg"},
            {"id": "c", "key": "W/Image_20231128221000000.jpg"}]
    g = session_groups(recs)
    assert g["a"] == g["b"] != g["c"]
    assert split_of("x:1") in {"train", "val", "test"}


def test_prompt_roundtrip():
    tax = load()
    t = target(["stringing", "spaghetti"], tax)
    assert t == '{"defects": ["spaghetti", "stringing"], "primary": "spaghetti"}'
    assert parse(t, tax) == (True, ["spaghetti", "stringing"])
    assert parse('{"defects": [], "primary": "none"}', tax) == (True, [])
    assert parse("not json", tax) == (False, [])
    assert parse('{"defects": ["bogus"], "primary": "bogus"}', tax)[0] is False
    msgs = messages("IMG", tax, [])
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[1]["content"][0]["type"] == "image"          # image before the text
    assert output_schema(tax)["properties"]["primary"]["enum"][-1] == "none"


def test_lora_targets_match_only_plain_linear():
    names = []
    for i in range(42):
        for m in ("self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj", "self_attn.o_proj", "mlp.gate_proj",
                  "mlp.up_proj", "mlp.down_proj", "per_layer_input_gate", "per_layer_projection"):
            names.append(f"model.language_model.layers.{i}.{m}")
    for i in range(16):
        for m in ("self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj", "self_attn.o_proj", "mlp.gate_proj",
                  "mlp.up_proj", "mlp.down_proj"):
            names.append(f"model.vision_tower.encoder.layers.{i}.{m}.linear")     # inner nn.Linear: adapt
            names.append(f"model.vision_tower.encoder.layers.{i}.{m}")            # Gemma4ClippableLinear: never
    names += ["model.vision_tower.patch_embedder.input_proj", "model.embed_vision.embedding_projection",
              "lm_head", "model.audio_tower.layers.0.self_attn.q_proj.linear", "model.language_model.per_layer_model_projection"]
    rx = re.compile(lora_targets(vision=True))
    hit = [n for n in names if rx.fullmatch(n)]
    assert len(hit) == 42 * 9 + 16 * 7 + 2
    assert not any(n.endswith(("_proj", "gate_proj")) and "vision_tower.encoder" in n for n in hit)
    assert not any("audio" in n or n == "lm_head" for n in hit)
    assert len([n for n in names if re.fullmatch(lora_targets(vision=False), n)]) == 42 * 9


def test_stratified_subset_is_deterministic():
    rows = [{"id": str(i), "primary": "a" if i % 3 else "b"} for i in range(30)]
    s1, s2 = stratified_subset(rows, 10), stratified_subset(rows, 10)
    assert [r["id"] for r in s1] == [r["id"] for r in s2] and len(s1) == 10
    assert {r["primary"] for r in s1} == {"a", "b"}
