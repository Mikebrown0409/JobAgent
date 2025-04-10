from .base_strategy import BaseApplicationStrategy
from .greenhouse_strategy import GreenhouseStrategy
from .lever_strategy import LeverStrategy
from .adaptive_strategy import AdaptiveStrategy

def get_strategy_for_platform(platform: str) -> BaseApplicationStrategy:
    """Factory function to get the appropriate strategy for a platform."""
    if platform == 'greenhouse':
        return GreenhouseStrategy()
    elif platform == 'lever':
        return LeverStrategy()
    elif platform == 'adaptive':
        return AdaptiveStrategy()
    else:
        # Default to adaptive strategy for unknown platforms
        return AdaptiveStrategy()
