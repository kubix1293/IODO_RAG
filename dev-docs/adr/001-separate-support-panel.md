# ADR-001: osobny panel i schemat

Status: zaakceptowana.

Panel serwisowy jest osobną usługą na porcie 8081 i korzysta ze schematu `support`. Współdzieli tylko katalog klientów i infrastrukturę modeli. Ogranicza to sprzężenie z istniejącym IODO, pozwala niezależnie skalować worker i upraszcza kontrolę dostępu.
