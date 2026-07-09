# Workflow projektu

Ostatnia aktualizacja: 2026-07-08

Cel pliku: proces utrzymywania dokumentacji po zmianach w kodzie, konfiguracji i wdrozeniu.

## Dokumentacja po zmianach

Po wykonaniu prac implementacyjnych i testow, gdy zmiana dziala poprawnie, nalezy uzyc agenta dokumentacyjnego `agent_to_docs` do dopisania istotnych informacji i utrzymywania dokumentacji projektu na biezaco.

Dotyczy to w szczegolnosci zmian w:

- uruchamianiu i konfiguracji Docker Compose,
- modelach embeddingowych i LLM,
- schemacie bazy danych,
- interfejsach CLI/API/web,
- procedurach operacyjnych,
- znanych ograniczeniach i kolejnych krokach.

Agent dokumentacyjny powinien aktualizowac odpowiednie pliki w `docs/` oraz, jesli ma to znaczenie dla uzytkownika, takze `README.md`.

## Procedura

Po kazdej zakonczonej zmianie:

1. Zweryfikowac dzialanie zmiany testami lub komendami operacyjnymi.
2. Uruchomic albo zlecic zadanie agentowi `agent_to_docs`.
3. Przekazac agentowi faktyczny stan po testach, a nie tylko planowana zmiane.
4. Pozwolic agentowi `agent_to_docs` wykonac czynnosci dokumentacyjne.
5. Nie zamykac agenta dokumentacyjnego, dopoki nie zwroci wyniku albo nie wystapi rzeczywisty blad narzedzia.
6. Nie tworzyc rownolegle niezaleznych plikow dokumentacji zamiast agenta. Glowne zadanie dokumentacyjne ma nalezec do `agent_to_docs`; lokalne poprawki powinny sluzyc tylko integracji, weryfikacji albo awaryjnemu obejsciu bledu narzedzia.
7. Zaktualizowac dokumentacje i dopiero wtedy uznac prace za domknieta.

Do agenta `agent_to_docs` nalezy przekazac zwiezle, konkretne fakty:

- jakie pliki i uslugi zmieniono,
- jakie endpointy, porty albo zmienne doszly,
- jakie komendy testowe wykonano,
- jakie byly wyniki testow,
- jakie nowe ograniczenia, adresy, porty lub zmienne konfiguracyjne sa istotne,
- co powinno zostac dopisane do dokumentacji operacyjnej.

Pliki do sprawdzenia po typowej zmianie:

- `README.md`
- `docs/00-INDEKS.md`
- `docs/STATUS.md`
- `docs/OPERATIONS.md`
- `docs/NEXT_STEPS.md`
- `docs/WORKFLOW.md`, jesli zmienia sie sam proces pracy

Przy zmianach dotyczacych web UI, portow, adresow LAN lub Dockera dokumentacja musi zawierac zweryfikowane adresy testowe, mapowanie portow i komendy diagnostyczne. Dla aktualnego wdrozenia testowym adresem hosta jest `192.168.1.14`.

Przy zmianach dotyczacych LLM dokumentacja musi zawierac:

- nazwe modelu,
- URL uslugi wewnatrz Compose,
- port hostowy, jesli jest wystawiony,
- timeout,
- parametry kontekstu i generacji, jesli wplywaja na operacje,
- realny wynik testu oraz znane ograniczenia wydajnosciowe.

## Obecny komplet dokumentacji operacyjnej

Aktualny komplet gotowy do skopiowania znajduje sie w:

```bash
/home/maverick/iodo-docs-update/docs
```

Docelowy katalog projektu:

```bash
/opt/IODO/docs
```

Jesli `/opt/IODO/docs` jest niezapisywalny dla agenta dokumentacyjnego, nalezy skopiowac pliki z `/tmp/iodo-docs/docs` z uprawnieniami administratora.
