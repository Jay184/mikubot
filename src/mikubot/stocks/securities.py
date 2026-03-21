from .models import Security, SecurityState, SecurityLinkState
from .store import MarketStore
from ..config import StockMarketSettings


class SecurityRepository:
    def __init__(self, store: MarketStore, settings: StockMarketSettings):
        self.store = store
        self.settings = settings

    def get(self, ticker: str, *, include_delisted: bool = False) -> Security | None:
        """
        Reconstruct a Security object from config + state.
        """
        key_upper = ticker.upper()
        config = next((s for s in self.settings.securities if s.key.upper() == key_upper), None)
        
        if not config:
            return None

        state = Security.load_state(key_upper) or SecurityState(
            price=config.starting_price,
            link=SecurityLinkState(),
        )

        return Security(config=config, state=state) if include_delisted or state.listed else None

    def all(self, include_delisted: bool = False) -> dict[str, Security]:
        tickers = self.store.domain("securities").keys()
        securities = {k: self.get(k) for k in tickers}
        return {k: sec for k, sec in securities.items()
                if sec is not None and (include_delisted or sec.state.listed)}

    def freeze(self, ticker: str):
        sec = self.get(ticker, include_delisted=True)
        sec.state.frozen = True
        sec.save_state()

    def unfreeze(self, ticker: str):
        sec = self.get(ticker, include_delisted=True)
        sec.state.frozen = False
        sec.save_state()

    def list(self, ticker: str):
        sec = self.get(ticker, include_delisted=True)
        sec.state.listed = True
        sec.save_state()

    def delist(self, ticker: str):
        sec = self.get(ticker, include_delisted=True)
        sec.state.listed = False
        sec.save_state()
