#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gaussian Mixture Model forecasting.

Usage patterns are rarely a single steady rate: there are light sessions and
heavy sessions, idle hours and busy hours. A single average hides that. A
Gaussian Mixture Model (GMM) fits the *distribution* of hourly carbon/energy
rates, giving a better expected value plus an uncertainty range and the
dominant usage modes - both for the whole machine and for each application.

The GMM here is a small, dependency-free 1-D Expectation-Maximisation
implementation (no numpy / sklearn required).
"""

import math
import random
from typing import Dict, List, Tuple

from carbon_tracker.models import SessionData

# 95% interval multiplier for a normal distribution.
_Z_95 = 1.959963985


class GaussianMixture1D:
    """A 1-D Gaussian Mixture fitted with Expectation-Maximisation."""

    def __init__(self):
        self.weights: List[float] = []
        self.means: List[float] = []
        self.variances: List[float] = []
        self.n_samples: int = 0

    @staticmethod
    def _gauss(x: float, mean: float, var: float) -> float:
        if var <= 0:
            return 0.0
        return math.exp(-((x - mean) ** 2) / (2.0 * var)) / math.sqrt(
            2.0 * math.pi * var
        )

    def fit(
        self,
        samples: List[float],
        n_components: int = 0,
        n_iter: int = 120,
        n_restarts: int = 5,
        tol: float = 1e-6,
        seed: int = 12345,
    ) -> "GaussianMixture1D":
        data = [float(s) for s in samples if s is not None and s >= 0]
        self.n_samples = len(data)

        if not data:
            self.weights, self.means, self.variances = [1.0], [0.0], [1e-6]
            return self

        # Auto-pick a sensible number of components for the sample size.
        if n_components <= 0:
            n_components = max(1, min(3, len(data) // 3))
        k = max(1, min(n_components, len(set(data)) or 1, len(data)))

        mean_all = sum(data) / len(data)
        var_all = sum((x - mean_all) ** 2 for x in data) / len(data)
        var_all = max(var_all, 1e-9)
        var_floor = max(var_all * 1e-3, 1e-9)

        if k == 1:
            self.weights, self.means, self.variances = [1.0], [mean_all], [var_all]
            return self

        best_ll = -math.inf
        best = ([1.0 / k] * k, list(data[:k]), [var_all] * k)

        for restart in range(n_restarts):
            rng = random.Random(seed + restart)
            means = rng.sample(data, k)
            variances = [var_all] * k
            weights = [1.0 / k] * k
            prev_ll = -math.inf

            for _ in range(n_iter):
                # E-step: responsibilities + log-likelihood.
                resp = [[0.0] * k for _ in range(len(data))]
                ll = 0.0
                for i, x in enumerate(data):
                    ps = [weights[j] * self._gauss(x, means[j], variances[j])
                          for j in range(k)]
                    s = sum(ps)
                    if s <= 0.0:
                        ps = [1.0 / k] * k
                        s = 1.0
                    for j in range(k):
                        resp[i][j] = ps[j] / s
                    ll += math.log(s) if s > 0 else 0.0

                # M-step.
                for j in range(k):
                    nj = sum(resp[i][j] for i in range(len(data)))
                    if nj < 1e-9:
                        weights[j] = 1e-9
                        continue
                    mu = sum(resp[i][j] * data[i] for i in range(len(data))) / nj
                    var = sum(
                        resp[i][j] * (data[i] - mu) ** 2 for i in range(len(data))
                    ) / nj
                    weights[j] = nj / len(data)
                    means[j] = mu
                    variances[j] = max(var, var_floor)

                wsum = sum(weights) or 1.0
                weights = [w / wsum for w in weights]

                if abs(ll - prev_ll) < tol:
                    break
                prev_ll = ll

            if ll > best_ll:
                best_ll = ll
                best = (list(weights), list(means), list(variances))

        self.weights, self.means, self.variances = best
        return self

    def mean(self) -> float:
        return sum(w * m for w, m in zip(self.weights, self.means))

    def variance(self) -> float:
        # Law of total variance for a mixture.
        mu = self.mean()
        return sum(
            w * (v + m * m) for w, m, v in zip(self.weights, self.means, self.variances)
        ) - mu * mu

    def std(self) -> float:
        return math.sqrt(max(self.variance(), 0.0))

    def interval(self, z: float = _Z_95) -> Tuple[float, float]:
        mu, sd = self.mean(), self.std()
        return (max(0.0, mu - z * sd), mu + z * sd)

    def components(self) -> List[dict]:
        comps = [
            {"weight": w, "rate": m, "std": math.sqrt(max(v, 0.0))}
            for w, m, v in zip(self.weights, self.means, self.variances)
        ]
        comps.sort(key=lambda c: -c["weight"])
        return comps


def _hourly_samples(session: SessionData) -> Tuple[List[float], List[float]]:
    """Aggregate per-app hourly carbon/energy into whole-system per-hour samples."""
    carbon: Dict[int, float] = {}
    energy: Dict[int, float] = {}
    for app in session.apps.values():
        for hr, val in app.carbon_by_hour.items():
            carbon[hr] = carbon.get(hr, 0.0) + val
        for hr, val in app.energy_by_hour.items():
            energy[hr] = energy.get(hr, 0.0) + val
    return list(carbon.values()), list(energy.values())


def _build_forecast(
    carbon_samples: List[float],
    energy_samples: List[float],
    hours: float,
) -> dict:
    carbon_mix = GaussianMixture1D().fit(carbon_samples)
    energy_mix = GaussianMixture1D().fit(energy_samples)

    c_rate, c_std = carbon_mix.mean(), carbon_mix.std()
    c_low, c_high = carbon_mix.interval()
    e_rate = energy_mix.mean()
    e_low, e_high = energy_mix.interval()

    return {
        "method": "gaussian_mixture",
        "projected_carbon_grams": c_rate * hours,
        "carbon_low_grams": c_low * hours,
        "carbon_high_grams": c_high * hours,
        "projected_energy_kwh": e_rate * hours,
        "energy_low_kwh": e_low * hours,
        "energy_high_kwh": e_high * hours,
        "rate_grams_per_hour": c_rate,
        "rate_std_grams_per_hour": c_std,
        "carbon_components": carbon_mix.components(),
        "n_samples": carbon_mix.n_samples,
    }


def forecast_project(sessions: List[SessionData], hours: float) -> dict:
    """Forecast future carbon/energy for ``hours`` using GMMs over historical
    sessions, both overall and per application."""
    result = {
        "projected_hours": hours,
        "method": "gaussian_mixture",
        "projected_carbon_grams": 0.0,
        "carbon_low_grams": 0.0,
        "carbon_high_grams": 0.0,
        "projected_energy_kwh": 0.0,
        "energy_low_kwh": 0.0,
        "energy_high_kwh": 0.0,
        "rate_grams_per_hour": 0.0,
        "rate_std_grams_per_hour": 0.0,
        "carbon_components": [],
        "based_on_sessions": len(sessions),
        "based_on_hours": 0.0,
        "n_samples": 0,
        "per_app": {},
    }

    if not sessions or hours <= 0:
        result["method"] = "none"
        return result

    overall_carbon: List[float] = []
    overall_energy: List[float] = []
    total_hours = 0.0

    # Per-app sample accumulators.
    app_carbon: Dict[str, List[float]] = {}
    app_energy: Dict[str, List[float]] = {}

    for session in sessions:
        sess_hours = session.duration_seconds / 3600.0
        total_hours += sess_hours

        c_hourly, e_hourly = _hourly_samples(session)
        if c_hourly:
            overall_carbon.extend(c_hourly)
        elif sess_hours > 1e-6:
            overall_carbon.append(session.total_carbon_grams / sess_hours)
        if e_hourly:
            overall_energy.extend(e_hourly)
        elif sess_hours > 1e-6:
            overall_energy.append(session.total_energy_kwh / sess_hours)

        for name, app in session.apps.items():
            cs = list(app.carbon_by_hour.values())
            es = list(app.energy_by_hour.values())
            if not cs and app.total_active_seconds > 1e-6:
                rate_h = app.total_active_seconds / 3600.0
                cs = [app.total_carbon_grams / rate_h]
                es = [app.total_energy_kwh / rate_h]
            app_carbon.setdefault(name, []).extend(cs)
            app_energy.setdefault(name, []).extend(es)

    result["based_on_hours"] = total_hours

    overall = _build_forecast(overall_carbon, overall_energy, hours)
    result.update(overall)
    result["projected_hours"] = hours
    result["based_on_sessions"] = len(sessions)
    result["based_on_hours"] = total_hours

    for name in app_carbon:
        app_fc = _build_forecast(
            app_carbon.get(name, []), app_energy.get(name, []), hours
        )
        result["per_app"][name] = {
            "projected_carbon_grams": app_fc["projected_carbon_grams"],
            "carbon_low_grams": app_fc["carbon_low_grams"],
            "carbon_high_grams": app_fc["carbon_high_grams"],
            "projected_energy_kwh": app_fc["projected_energy_kwh"],
            "rate_grams_per_hour": app_fc["rate_grams_per_hour"],
            "rate_std_grams_per_hour": app_fc["rate_std_grams_per_hour"],
            "components": app_fc["carbon_components"],
            "n_samples": app_fc["n_samples"],
        }

    return result
