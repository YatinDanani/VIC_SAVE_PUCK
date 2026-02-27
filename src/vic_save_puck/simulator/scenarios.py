"""Pre-built demo scenarios for the game simulator."""

from __future__ import annotations

from dataclasses import dataclass

from vic_save_puck.simulator.engine import GameSimulator, NoiseConfig
from vic_save_puck.data.enricher import enrich_games


@dataclass
class Scenario:
    """A pre-configured demo scenario."""
    name: str
    description: str
    game_date: str
    noise: NoiseConfig
    speed: float = 60.0

    def build_simulator(self, speed: float | None = None, **kwargs) -> GameSimulator:
        return GameSimulator(
            game_date=self.game_date,
            speed=speed or self.speed,
            noise=self.noise,
            **kwargs,
        )


def _pick_game(archetype: str = "mixed", is_playoff: bool = False) -> str:
    """Pick a representative game date for a scenario."""
    games = enrich_games()
    candidates = games[
        (games["archetype"] == archetype) & (games["is_playoff"] == is_playoff)
    ]
    if candidates.empty:
        candidates = games
    # Pick median attendance game
    median_att = candidates["attendance"].median()
    idx = (candidates["attendance"] - median_att).abs().idxmin()
    return str(candidates.loc[idx, "game_date"].date())


def get_scenarios() -> dict[str, Scenario]:
    """Return all pre-built demo scenarios."""
    games = enrich_games()

    # Find a good game for each scenario
    normal_date = _pick_game("mixed")
    beer_date = _pick_game("beer_crowd")
    family_date = _pick_game("family")

    # Playoff game
    playoff_games = games[games["is_playoff"]]
    playoff_date = str(playoff_games.iloc[0]["game_date"].date()) if not playoff_games.empty else normal_date

    # Promo game
    promo_games = games[games["is_promo"]]
    promo_date = str(promo_games.iloc[0]["game_date"].date()) if not promo_games.empty else normal_date

    return {
        "normal": Scenario(
            name="Normal Game",
            description="Standard mixed-crowd game. Forecast should be accurate with minor drift.",
            game_date=normal_date,
            noise=NoiseConfig(),
        ),
        "untagged_promo": Scenario(
            name="Untagged Promo",
            description="System doesn't know it's a promo night. Demand spikes 40%+ mid-game.",
            game_date=promo_date if promo_date != normal_date else normal_date,
            noise=NoiseConfig(global_volume_factor=1.4),
        ),
        "stand_redistribution": Scenario(
            name="Stand Redistribution",
            description="Island Canteen goes down during INT1. Other stands absorb demand.",
            game_date=normal_date,
            noise=NoiseConfig(
                stand_outage="SOFMC Island Canteen",
                stand_outage_start_min=20.0,
                stand_outage_end_min=50.0,
                demand_spike_stand="SOFMC TacoTacoTaco",
                demand_spike_factor=1.8,
                demand_spike_after_min=20.0,
            ),
        ),
        "weather_surprise": Scenario(
            name="Weather Surprise",
            description="Unseasonably warm day — beer demand diverges from forecast.",
            game_date=family_date,  # Use a typically low-beer game
            noise=NoiseConfig(
                # Simulate warm weather boosting beer: won't change data but
                # forecast uses cold-weather profile while actuals are warm
                global_volume_factor=1.15,
            ),
        ),
        "playoff": Scenario(
            name="Playoff Game",
            description="Real playoff game data — high intensity, beer-heavy crowd.",
            game_date=playoff_date,
            noise=NoiseConfig(),
        ),
    }


def list_scenarios() -> list[dict]:
    """List available scenarios with metadata."""
    scenarios = get_scenarios()
    return [
        {
            "key": key,
            "name": s.name,
            "description": s.description,
            "game_date": s.game_date,
        }
        for key, s in scenarios.items()
    ]
