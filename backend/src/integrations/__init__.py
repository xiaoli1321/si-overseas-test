from src.core.config import get_settings

_cgm_clients = {}


def get_cgm_client():
    settings = get_settings()
    enabled = settings.overseas_api_enabled
    if enabled not in _cgm_clients:
        if enabled:
            from src.integrations.overseas_client import OverseasCGMClient

            _cgm_clients[enabled] = OverseasCGMClient(settings)
        else:
            from src.integrations.mock_cgm import MockCGMClient

            _cgm_clients[enabled] = MockCGMClient()
    return _cgm_clients[enabled]
