"""Configurable-speed game event replay engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
import numpy as np

from vic_save_puck.data.loader import load_merged
from vic_save_puck.data.enricher import enrich_games


@dataclass
class GameEvent:
    """A single POS transaction event."""
    timestamp: pd.Timestamp
    stand: str
    item: str
    category: str
    qty: int
    price_point: str
    mins_from_puck_drop: float
    time_window: int

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "stand": self.stand,
            "item": self.item,
            "category": self.category,
            "qty": self.qty,
            "price_point": self.price_point,
            "mins_from_puck_drop": self.mins_from_puck_drop,
            "time_window": self.time_window,
        }


@dataclass
class NoiseConfig:
    """Configuration for noise injection."""
    demand_spike_stand: str | None = None      # Stand to spike
    demand_spike_factor: float = 1.0           # Multiplier for spike
    demand_spike_after_min: float = 20.0       # Start spike after this minute
    stand_outage: str | None = None            # Stand that goes offline
    stand_outage_start_min: float = 30.0       # When outage starts
    stand_outage_end_min: float = 50.0         # When outage ends
    global_volume_factor: float = 1.0          # Scale all demand


Observer = Callable[[GameEvent], None]
WindowObserver = Callable[[int, list[GameEvent]], None]  # time_window, events in window


class GameSimulator:
    """Replay a real game's transactions at configurable speed."""

    def __init__(
        self,
        game_date: str,
        speed: float = 10.0,
        noise: NoiseConfig | None = None,
        observers: list[Observer] | None = None,
        window_observers: list[WindowObserver] | None = None,
    ):
        self.game_date = pd.Timestamp(game_date)
        self.speed = speed
        self.noise = noise or NoiseConfig()
        self.observers: list[Observer] = observers or []
        self.window_observers: list[WindowObserver] = window_observers or []

        # Load game data
        merged = load_merged()
        self.game_txns = merged[merged["game_date"] == self.game_date].copy()
        if self.game_txns.empty:
            raise ValueError(f"No transactions found for {game_date}")

        self.game_txns = self.game_txns.sort_values("datetime").reset_index(drop=True)

        # Load game metadata
        games = enrich_games()
        game_row = games[games["game_date"] == self.game_date]
        if not game_row.empty:
            self.game_meta = game_row.iloc[0].to_dict()
        else:
            self.game_meta = {}

        self._events: list[GameEvent] = []
        self._window_events: dict[int, list[GameEvent]] = {}

    @property
    def total_events(self) -> int:
        return len(self.game_txns)

    @property
    def game_info(self) -> dict:
        return {
            "date": str(self.game_date.date()),
            "opponent": self.game_meta.get("opponent", "Unknown"),
            "attendance": self.game_meta.get("attendance", 0),
            "archetype": self.game_meta.get("archetype", "mixed"),
            "total_transactions": self.total_events,
        }

    def _apply_noise(self, row: pd.Series) -> list[GameEvent]:
        """Apply noise config to a transaction, returning 0+ events."""
        mins = row["mins_from_puck_drop"]
        stand = row["stand"]

        # Stand outage: drop events from the outage stand during window
        if (self.noise.stand_outage and stand == self.noise.stand_outage
                and self.noise.stand_outage_start_min <= mins <= self.noise.stand_outage_end_min):
            return []

        qty = int(row["Qty"])

        # Global volume scaling
        qty = max(1, round(qty * self.noise.global_volume_factor))

        # Demand spike at specific stand
        if (self.noise.demand_spike_stand and stand == self.noise.demand_spike_stand
                and mins >= self.noise.demand_spike_after_min):
            qty = max(1, round(qty * self.noise.demand_spike_factor))

        return [GameEvent(
            timestamp=row["datetime"],
            stand=stand,
            item=row["Item"],
            category=row["category_norm"],
            qty=qty,
            price_point=str(row.get("Price Point Name", "")),
            mins_from_puck_drop=float(mins),
            time_window=int(row["time_window"]),
        )]

    def run(self, realtime: bool = True) -> list[GameEvent]:
        """
        Run the simulation.

        If realtime=True, sleeps between events to simulate wall-clock pace.
        If realtime=False, emits all events instantly (for batch processing).
        """
        all_events: list[GameEvent] = []
        window_events: dict[int, list[GameEvent]] = {}
        current_window = None

        prev_time = None

        for _, row in self.game_txns.iterrows():
            events = self._apply_noise(row)

            for event in events:
                # Real-time pacing
                if realtime and prev_time is not None and self.speed > 0:
                    delta = (event.timestamp - prev_time).total_seconds()
                    if delta > 0:
                        time.sleep(delta / self.speed)

                prev_time = event.timestamp

                # Emit to observers
                for obs in self.observers:
                    obs(event)

                all_events.append(event)

                # Track window events
                tw = event.time_window
                if tw not in window_events:
                    window_events[tw] = []
                window_events[tw].append(event)

                # Window boundary: notify window observers
                if current_window is not None and tw != current_window:
                    for wobs in self.window_observers:
                        wobs(current_window, window_events.get(current_window, []))

                current_window = tw

        # Final window notification
        if current_window is not None:
            for wobs in self.window_observers:
                wobs(current_window, window_events.get(current_window, []))

        self._events = all_events
        self._window_events = window_events
        return all_events

    def run_batch(self) -> list[GameEvent]:
        """Run without timing — emit all events instantly."""
        return self.run(realtime=False)

    def get_events_dataframe(self) -> pd.DataFrame:
        """Convert emitted events to DataFrame."""
        if not self._events:
            return pd.DataFrame()
        return pd.DataFrame([e.to_dict() for e in self._events])
