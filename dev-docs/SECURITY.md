# Bezpieczeństwo

- Hasła: Argon2id; minimum 12 znaków przy tworzeniu.
- Sesje: losowe UUID po stronie serwera, 12 godzin, cookie HttpOnly/SameSite=Strict i Secure pod HTTPS.
- CSRF: osobny losowy token porównywany z sesją.
- RBAC: technician, senior_technician, admin; publikacja wiedzy wymaga roli senior lub admin.
- Dodawanie i przeglądanie przypadków historycznych wymaga roli senior lub admin; każdy odczyt wymaga wskazania jednego systemu.
- Import dokumentacji technicznej wymaga roli senior lub admin. Zakres klienta wymaga jawnego `client_id`; wyszukiwanie nadal filtruje system i klienta.
- Technik może zapisać raport realizacji i ocenę, lecz tylko senior/admin może opublikować metodę jako zatwierdzoną wiedzę systemu.
- Izolacja: program zawsze obowiązkowy; prywatna wiedza tylko dla klienta zgłoszenia.
- Anonimizacja: źródła przekazywane do UI są redagowane; test obejmuje e-mail, telefon i identyfikatory.
- Audyt: wszystkie modyfikujące operacje zapisują aktora, akcję, encję i metadane.

Przed pilotem należy ustawić losowe `SUPPORT_SESSION_SECRET`, zgodne `SUPPORT_CHECKPOINT_KEY` i `LANGGRAPH_AES_KEY`, zmienić hasło bootstrap i wystawić panel wyłącznie przez HTTPS/VPN.
