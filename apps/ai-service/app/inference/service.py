from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np

from app.explain.service import build_explanation
from app.registry.schemas import Environment
from app.registry.service import RegistryService

from .schemas import PredictRequest, PredictResponse, Signal

log = logging.getLogger(__name__)


class ModelUnavailable(Exception):
    """No active model has been loaded for this environment."""


class FeatureSchemaMismatch(Exception):
    """Submitted features do not match the model's expected schema."""


# Decision thresholds on P(class == 1) i.e. up-direction probability.
_BUY_THRESHOLD = 0.6
_SELL_THRESHOLD = 0.4


def _decide(prob_up: float) -> Signal:
    if prob_up >= _BUY_THRESHOLD:
        return "BUY"
    if prob_up <= _SELL_THRESHOLD:
        return "SELL"
    return "HOLD"


class InferenceService:
    """Loads the active model from the registry and serves predictions.

    Cache: a short-window in-memory cache keyed by (model_id, feature tuple).
    Identical inputs within `cache_ttl_s` reuse the previous response.
    """

    def __init__(
        self,
        *,
        registry: RegistryService,
        environment: Environment = "paper",
        cache_ttl_s: float = 2.0,
    ) -> None:
        self._registry = registry
        self._environment: Environment = environment
        self._cache_ttl_s = cache_ttl_s
        self._lock = threading.Lock()
        self._estimator: Any | None = None
        self._model_id: str | None = None
        self._model_version: int | None = None
        self._feature_names: list[str] = []
        self._cache: dict[tuple[str, tuple[tuple[str, float], ...]], tuple[float, PredictResponse]] = {}

    @property
    def environment(self) -> Environment:
        return self._environment

    @property
    def model_id(self) -> str | None:
        return self._model_id

    @property
    def model_version(self) -> int | None:
        return self._model_version

    @property
    def loaded(self) -> bool:
        return self._estimator is not None

    def load(self) -> bool:
        """Load the active model for `environment` from the registry.

        Returns True if a model was loaded, False if no active model is set.
        """
        with self._lock:
            active = self._registry.active()
            mid = getattr(active, self._environment)
            if mid is None:
                self._estimator = None
                self._model_id = None
                self._model_version = None
                self._feature_names = []
                self._cache.clear()
                log.info(
                    "no active model to load",
                    extra={"environment": self._environment},
                )
                return False
            meta = self._registry.get(mid)
            self._estimator = self._registry.store.load_artifact(mid)
            self._model_id = meta.id
            self._model_version = meta.version
            self._feature_names = list(meta.feature_names)
            self._cache.clear()
            log.info(
                "model loaded",
                extra={
                    "environment": self._environment,
                    "model_id": meta.id,
                    "version": meta.version,
                    "n_features": len(self._feature_names),
                },
            )
            return True

    def reload(self) -> bool:
        return self.load()

    def predict(self, req: PredictRequest, *, explain: bool = False) -> PredictResponse:
        if self._estimator is None:
            raise ModelUnavailable("no active model loaded")

        order = self._feature_names or sorted(req.features.keys())
        missing = [c for c in order if c not in req.features]
        if missing:
            raise FeatureSchemaMismatch(
                f"missing features: {sorted(missing)}; expected {order}"
            )

        cache_key = (
            self._model_id or "",
            tuple((c, float(req.features[c])) for c in order),
        )
        now = time.monotonic()
        hit = self._cache.get(cache_key)
        if hit is not None and now - hit[0] <= self._cache_ttl_s:
            cached = hit[1].model_copy(update={"cached": True, "symbol": req.symbol, "timeframe": req.timeframe})
            if not explain:
                cached = cached.model_copy(update={"explanation": None})
            elif cached.explanation is None:
                cached = cached.model_copy(update={
                    "explanation": build_explanation(
                        estimator=self._estimator,
                        feature_names=order,
                        values=[float(req.features[c]) for c in order],
                        signal=cached.signal,
                        confidence=cached.confidence,
                    )
                })
            return cached

        x = np.asarray([[float(req.features[c]) for c in order]], dtype="float64")
        proba = self._estimator.predict_proba(x)[0]
        classes = [int(c) for c in self._estimator.classes_]
        prob_map = {str(c): float(p) for c, p in zip(classes, proba)}
        prob_up = prob_map.get("1", float(proba.max()) if 1 not in classes else 0.0)
        signal = _decide(prob_up)
        confidence = float(max(proba))
        risk_score = float(1.0 - confidence)
        reason = _explain(signal, prob_up, order, x[0])

        explanation = (
            build_explanation(
                estimator=self._estimator,
                feature_names=order,
                values=[float(v) for v in x[0]],
                signal=signal,
                confidence=confidence,
            )
            if explain
            else None
        )

        resp = PredictResponse(
            symbol=req.symbol,
            timeframe=req.timeframe,
            signal=signal,
            confidence=confidence,
            risk_score=risk_score,
            probabilities=prob_map,
            model_id=self._model_id or "",
            model_version=self._model_version or 0,
            reason=reason,
            cached=False,
            explanation=explanation,
        )
        self._cache[cache_key] = (now, resp)
        log.info(
            "inference complete",
            extra={
                "symbol": req.symbol,
                "model_id": self._model_id,
                "signal": signal,
                "confidence": confidence,
            },
        )
        return resp


def _explain(signal: Signal, prob_up: float, names: list[str], values) -> str:
    if signal == "BUY":
        return f"P(up)={prob_up:.2f} above buy threshold {_BUY_THRESHOLD:.2f}"
    if signal == "SELL":
        return f"P(up)={prob_up:.2f} below sell threshold {_SELL_THRESHOLD:.2f}"
    return f"P(up)={prob_up:.2f} within hold band"
