from app.models.enums import ProviderCode
from app.providers.aurora import AuroraProvider
from app.providers.base import AbstractProvider
from app.providers.errors import ProviderError
from app.providers.exolve import ExolveProvider
from app.providers.finenumbers import FinenumbersProvider
from app.providers.runexis import RunexisProvider
from app.providers.sipout import SipOutProvider
from app.providers.uis import UisProvider
from app.providers.voximplant import VoximplantProvider
from app.providers.mcn import McnProvider

PROVIDER_REGISTRY: dict[ProviderCode, type[AbstractProvider]] = {
    ProviderCode.runexis: RunexisProvider,
    ProviderCode.sipout: SipOutProvider,
    ProviderCode.finenumbers: FinenumbersProvider,
    ProviderCode.uis: UisProvider,
    ProviderCode.aurora: AuroraProvider,
    ProviderCode.exolve: ExolveProvider,
    ProviderCode.voximplant: VoximplantProvider,
    ProviderCode.mcn: McnProvider,
}


def get_provider(code: ProviderCode | str) -> AbstractProvider:
    if isinstance(code, str):
        try:
            code = ProviderCode(code)
        except ValueError as exc:
            raise ProviderError(f"Unknown provider: {code}") from exc
    cls = PROVIDER_REGISTRY.get(code)
    if not cls:
        raise ProviderError(f"Provider not registered: {code}")
    return cls()
