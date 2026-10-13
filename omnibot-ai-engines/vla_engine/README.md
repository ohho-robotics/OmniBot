# OmniVLA engine (`vla_engine`)

The **offline** training and inference stack for Vision-Language-Action
(OpenVLA / SmolVLA) models. Pure PyTorch plus a FastAPI inference server; no ROS
dependency.

PyPI distribution name (when published): **`omnibot-vla-engine`**. Import as
`vla_engine`.

## Distinction

- **`vla_engine/` (this folder)**: OmniVLA engine — model wrappers, a FastAPI
  inference server, and TensorRT export tooling. Independent of ROS.
- **`robot_ws/src/omnibot_vla/`**: the ROS 2 node that wraps OpenVLA for
  real-time robot control.
- **`vla_serve`**: a thin FastAPI server with the same `/health`, `/load_model`,
  and `/predict` contract (packaged separately in the OhhO SDK / `ohho-os` tree;
  not vendored in this repo).

## Layout

```
vla_engine/
├── models/
│   ├── base.py        # VLAModel ABC (load_model, predict_action)
│   └── openvla.py     # OpenVLAModel — HF AutoModelForVision2Seq wrapper
├── inference/
│   ├── server.py      # FastAPI app (auth, rate limit, body-size guard)
│   └── schema.py      # InferenceRequest / InferenceResponse (pydantic)
├── trt/
│   ├── encoder_export.py  # export SmolVLA vision encoder → ONNX, build TRT
│   └── build_engine.py    # CLI: checkpoint → ONNX → TRT engine (+sanity check)
├── utils/image.py     # base64 ↔ PIL/numpy helpers
└── tests/test_server.py
```

## Setup

Editable install (recommended):

```bash
pip install -e "omnibot-ai-engines/vla_engine[serve,gpu]"
```

CPU-only inference dependencies (no weights download):

```bash
pip install -e "omnibot-ai-engines/vla_engine[serve,gpu]" \
  --extra-index-url https://download.pytorch.org/whl/cpu
```

Legacy one-shot install from `requirements.txt` (same stacks, no packaging):

```bash
pip install -r omnibot-ai-engines/vla_engine/requirements.txt
```

## Inference server

```bash
python -m vla_engine.inference.server   # serves on 0.0.0.0:8000
```

Endpoints:

| Method | Path | Notes |
|---|---|---|
| `GET`  | `/health`     | `{status, model_loaded}` |
| `POST` | `/load_model` | query params `model_path` (default `openvla/openvla-7b`), `load_4bit` |
| `POST` | `/predict`    | body = `InferenceRequest` → `InferenceResponse` |

`POST /predict` request body:

```json
{ "instruction": "pick up the red cup", "image_base64": "<base64 JPEG/PNG>" }
```

Response: `{ "action": {"vector": [...], "raw_output": "..."}, "raw_output": "...", "latency_ms": 0.0 }`.

The model is loaded lazily on startup; if loading fails the server still comes
up and `/predict` returns 503 until `/load_model` succeeds.

### Server configuration (environment variables)

| Env var | Default | Purpose |
|---|---|---|
| `VLA_API_KEY` | `''` (auth disabled) | required `X-API-Key` header when set |
| `VLA_RATE_LIMIT` | `10` | token-bucket requests/second per key |
| `VLA_CORS_ORIGINS` | `*` | comma-separated allowed origins |
| `VLA_MAX_BODY_BYTES` | `10485760` | request body size cap (HTTP 413 above) |

## TensorRT export (optional)

Export the SmolVLA vision encoder to a TRT engine for faster inference. Requires
`tensorrt`, `onnx`, and `lerobot` (installed separately).

```bash
# FP16 (recommended for RTX GPUs)
python -m vla_engine.trt.build_engine \
    --checkpoint lerobot/smolvla_base \
    --output engines/smolvla_vision_fp16.trt \
    --precision fp16

# INT8 with calibration images
python -m vla_engine.trt.build_engine \
    --checkpoint lerobot/smolvla_base \
    --output engines/smolvla_vision_int8.trt \
    --precision int8 \
    --calibration-data ~/datasets/omnibot/calibration_images/
```

Default input size is 320×240 (`--image-width` / `--image-height`). The built
engine is consumed by `policy_node` in `omnibot_lerobot` via `use_trt: true`.

## Tests

After `pip install -e "omnibot-ai-engines/vla_engine[serve,gpu,test]"`:

```bash
pytest omnibot-ai-engines/vla_engine/tests/
```

CI runs the same suite in the `vla-engine` job in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
(CPU PyTorch, mocked model). Tests are skipped when `torch` is not installed.

## Distribution (TODO — OHH-55)

**Not published in this change.** Varun to decide:

1. Publish **`omnibot-vla-engine`** on PyPI (optional console alias `vla-serve`), or
2. Fold the server stack into **`ohho-os[serve]`** on PyPI and keep this folder as the source tree only.

Until then, use editable install from this repo.
