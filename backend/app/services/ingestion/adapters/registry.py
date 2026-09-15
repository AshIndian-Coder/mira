from app.services.ingestion.adapters.base import DocumentAdapter, ParsedDocument


class AdapterRegistry:
    """
    Ordered registry of document adapters.

    Specific adapters should be registered before the generic fallback.
    """

    def __init__(self) -> None:
        self._adapters: list[DocumentAdapter] = []

    def register(self, adapter: DocumentAdapter) -> None:
        self._adapters.append(adapter)

    def find(
        self,
        document: ParsedDocument,
    ) -> DocumentAdapter | None:

        for adapter in self._adapters:
            if adapter.can_handle(document):
                return adapter

        return None

    @property
    def adapters(self) -> tuple[DocumentAdapter, ...]:
        return tuple(self._adapters)
