"""Embedding and reranking models run with ONNX Runtime instead of PyTorch.

ONNX Runtime loads in well under a second, where importing torch takes over ten,
and the optimized graphs run faster on CPU. The models are the same
sentence-transformers checkpoints, exported by their authors, so scores match.
"""

import numpy as np

# Inputs are sorted by length and padded per batch, so short passages do not pay
# for the longest one in the pool.
BATCH_SIZE = 8


def _download(repo: str, filename: str) -> str:
    """Use the local cache when possible, so startup works offline and never waits on the network."""
    from huggingface_hub import hf_hub_download

    try:
        return hf_hub_download(repo, filename, local_files_only=True)
    except Exception:
        return hf_hub_download(repo, filename)


class _OnnxModel:
    def __init__(self, repo: str, onnx_file: str, max_length: int):
        import onnxruntime
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(_download(repo, "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length)
        self._tokenizer.no_padding()
        options = onnxruntime.SessionOptions()
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = onnxruntime.InferenceSession(
            _download(repo, onnx_file), options, providers=["CPUExecutionProvider"]
        )
        self._input_names = {item.name for item in self._session.get_inputs()}

    def _run_batches(self, encodings: list, run) -> list:
        """Run `run(feed, mask)` on length-sorted batches and return outputs in input order."""
        order = sorted(range(len(encodings)), key=lambda index: len(encodings[index].ids))
        outputs: list = [None] * len(encodings)
        for start in range(0, len(order), BATCH_SIZE):
            batch = order[start : start + BATCH_SIZE]
            width = max(len(encodings[index].ids) for index in batch)
            feed = {
                name: np.zeros((len(batch), width), dtype=np.int64)
                for name in ("input_ids", "attention_mask", "token_type_ids")
            }
            for row, index in enumerate(batch):
                encoding = encodings[index]
                length = len(encoding.ids)
                feed["input_ids"][row, :length] = encoding.ids
                feed["attention_mask"][row, :length] = encoding.attention_mask
                feed["token_type_ids"][row, :length] = encoding.type_ids
            feed = {name: value for name, value in feed.items() if name in self._input_names}
            for index, value in zip(batch, run(feed, feed["attention_mask"])):
                outputs[index] = value
        return outputs


class OnnxEmbedder(_OnnxModel):
    """Mean-pooled, normalized sentence embeddings, as sentence-transformers produces them."""

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        def run(feed, mask):
            hidden = self._session.run(None, feed)[0]
            weights = mask[..., None].astype(hidden.dtype)
            pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
            return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)

        return np.stack(self._run_batches(self._tokenizer.encode_batch(texts), run))


class OnnxCrossEncoder(_OnnxModel):
    """Relevance logits for (query, passage) pairs."""

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []

        def run(feed, _mask):
            return self._session.run(None, feed)[0][:, 0]

        return [float(score) for score in self._run_batches(self._tokenizer.encode_batch(pairs), run)]
