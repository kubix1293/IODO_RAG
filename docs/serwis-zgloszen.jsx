import { useState, useMemo } from "react";

/* ————— SERWISDESK — panel zgłoszeń dla serwisantów IT —————
   Paleta: chłodna szarość warsztatowa + kobalt sygnałowy
   Typografia: Archivo (display) / Inter (tekst) / JetBrains Mono (ID, statusy)
*/

const T = {
  bg: "#EDF0EE",
  surface: "#FFFFFF",
  ink: "#1A2321",
  muted: "#66736E",
  line: "#D7DDD9",
  lineSoft: "#E4E8E5",
  accent: "#2A5CFF",
  accentSoft: "#E8EDFF",
  ok: "#1F9D63",
  okSoft: "#E2F4EA",
  warn: "#D97E0B",
  warnSoft: "#FCEFDA",
  crit: "#DE3B3B",
  critSoft: "#FBE5E5",
  violet: "#7A5AF8",
  violetSoft: "#EEEAFE",
};

const FONT_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');
* { box-sizing: border-box; }
::selection { background: ${T.accent}; color: #fff; }
button { font-family: inherit; }
input, textarea, select { font-family: inherit; }
input:focus, textarea:focus, select:focus, button:focus-visible { outline: 2px solid ${T.accent}; outline-offset: 1px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
@keyframes pulseDot { 0%,100%{opacity:.35} 50%{opacity:1} }
.spin-dot { animation: pulseDot 1.1s ease-in-out infinite; }
.row-hover:hover { background: #F6F8F6; }
.scroll-y::-webkit-scrollbar { width: 8px; }
.scroll-y::-webkit-scrollbar-thumb { background: ${T.line}; border-radius: 8px; }
`;

const STATUSY = {
  nowe: { label: "NOWE", color: T.accent, soft: T.accentSoft },
  w_trakcie: { label: "W TRAKCIE", color: T.warn, soft: T.warnSoft },
  oczekuje: { label: "OCZEKUJE", color: T.violet, soft: T.violetSoft },
  zamkniete: { label: "ZAMKNIĘTE", color: T.ok, soft: T.okSoft },
};

const PRIORYTETY = {
  krytyczny: { label: "Krytyczny", color: T.crit },
  wysoki: { label: "Wysoki", color: T.warn },
  normalny: { label: "Normalny", color: T.accent },
  niski: { label: "Niski", color: T.muted },
};

const seedClients = [
  { id: 1, nazwa: "Biuro Rachunkowe Kalkulus", kontakt: "Anna Wiśniewska", email: "biuro@kalkulus.pl", telefon: "61 852 40 12", notatki: "Umowa SLA — reakcja do 4h. Serwer NAS + 8 stanowisk." },
  { id: 2, nazwa: "Piekarnia Złoty Kłos", kontakt: "Marek Zieliński", email: "sklep@zlotyklos.pl", telefon: "512 334 908", notatki: "Kasa fiskalna Posnet, terminal płatniczy, 2 komputery." },
  { id: 3, nazwa: "Kancelaria Lex Partner", kontakt: "Tomasz Adamczyk", email: "sekretariat@lexpartner.pl", telefon: "61 664 21 87", notatki: "Wysokie wymogi bezpieczeństwa danych. VPN + szyfrowanie dysków." },
];

const seedTickets = [
  {
    id: 41, klientId: 1, tytul: "Serwer NAS nie odpowiada po aktualizacji",
    opis: "Po wczorajszej aktualizacji firmware NAS Synology przestał być widoczny w sieci. Dioda statusu miga na pomarańczowo. Pracownicy nie mają dostępu do plików księgowych.",
    priorytet: "krytyczny", status: "w_trakcie", kategoria: "Serwery / NAS",
    data: "2026-07-22 08:15", analiza: null, notatki: [{ data: "2026-07-22 09:40", tekst: "Umówiony dojazd na 13:00. Zabrać konsolę i kabel serial." }],
  },
  {
    id: 40, klientId: 2, tytul: "Drukarka fiskalna gubi połączenie z kasą",
    opis: "Kilka razy dziennie drukarka fiskalna traci połączenie i trzeba restartować program sprzedażowy. Zaczęło się po burzy w zeszłym tygodniu.",
    priorytet: "wysoki", status: "nowe", kategoria: "Urządzenia fiskalne",
    data: "2026-07-21 16:02", analiza: null, notatki: [],
  },
  {
    id: 39, klientId: 3, tytul: "VPN rozłącza się przy większych plikach",
    opis: "Prawnicy pracujący zdalnie zgłaszają, że tunel VPN zrywa się przy pobieraniu plików powyżej ~200 MB. Małe pliki działają bez problemu.",
    priorytet: "normalny", status: "oczekuje", kategoria: "Sieć / VPN",
    data: "2026-07-20 11:30", analiza: null, notatki: [{ data: "2026-07-21 10:00", tekst: "Czekamy na logi z routera od klienta." }],
  },
  {
    id: 38, klientId: 1, tytul: "Wymiana dysku w stacji roboczej — księgowość",
    opis: "Komputer pani Grażyny bardzo wolno się uruchamia, SMART pokazuje realokowane sektory. Do wymiany HDD na SSD z klonowaniem systemu.",
    priorytet: "niski", status: "zamkniete", kategoria: "Sprzęt / stacje robocze",
    data: "2026-07-17 09:20", analiza: null, notatki: [{ data: "2026-07-18 15:10", tekst: "Wymieniono na SSD 1TB, sklonowano system, czas startu 4x szybszy. Zamknięte." }],
  },
];

const defaultSettings = {
  nazwaSerwisu: "SERWISDESK",
  kategorie: ["Sprzęt / stacje robocze", "Serwery / NAS", "Sieć / VPN", "Oprogramowanie", "Urządzenia fiskalne", "Drukarki", "Bezpieczeństwo", "Inne"],
  wskazowkiAI: "Jesteśmy małym serwisem IT obsługującym firmy w Wielkopolsce. Preferujemy rozwiązania możliwe do wykonania zdalnie, zanim zaproponujemy dojazd. Zawsze zwracaj uwagę na kopie zapasowe przed ingerencją w sprzęt lub system.",
};

/* ————— drobne komponenty ————— */

const mono = { fontFamily: "'JetBrains Mono', monospace" };

function StatusChip({ status }) {
  const s = STATUSY[status];
  return (
    <span style={{ ...mono, fontSize: 10.5, fontWeight: 600, letterSpacing: "0.06em", color: s.color, background: s.soft, padding: "3px 8px", borderRadius: 4, whiteSpace: "nowrap" }}>
      {s.label}
    </span>
  );
}

function PriorityTick({ priorytet, withLabel }) {
  const p = PRIORYTETY[priorytet];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 3, height: 14, borderRadius: 2, background: p.color, display: "inline-block" }} />
      {withLabel && <span style={{ fontSize: 12.5, color: T.ink, fontWeight: 500 }}>{p.label}</span>}
    </span>
  );
}

function Field({ label, children, hint }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: T.muted, marginBottom: 6 }}>{label}</div>
      {children}
      {hint && <div style={{ fontSize: 12, color: T.muted, marginTop: 5 }}>{hint}</div>}
    </div>
  );
}

const inputStyle = {
  width: "100%", padding: "10px 12px", fontSize: 14, color: T.ink,
  background: T.surface, border: `1px solid ${T.line}`, borderRadius: 8,
};

function Btn({ children, onClick, kind = "primary", small, disabled, style }) {
  const base = {
    padding: small ? "7px 12px" : "10px 18px",
    fontSize: small ? 12.5 : 13.5, fontWeight: 600, borderRadius: 8,
    cursor: disabled ? "default" : "pointer", border: "1px solid transparent",
    transition: "background .15s, border-color .15s", opacity: disabled ? 0.55 : 1,
  };
  const kinds = {
    primary: { background: T.accent, color: "#fff" },
    ghost: { background: "transparent", color: T.ink, border: `1px solid ${T.line}` },
    danger: { background: "transparent", color: T.crit, border: `1px solid ${T.critSoft}` },
    ai: { background: T.ink, color: "#fff" },
  };
  return (
    <button onClick={disabled ? undefined : onClick} disabled={disabled} style={{ ...base, ...kinds[kind], ...style }}>
      {children}
    </button>
  );
}

/* ————— analiza AI ————— */

async function analizujZgloszenie(ticket, klient, settings) {
  const prompt = `Jesteś doświadczonym inżynierem wsparcia IT analizującym zgłoszenie serwisowe.

KONTEKST SERWISU (wskazówki od zespołu — stosuj się do nich):
${settings.wskazowkiAI || "brak"}

KLIENT: ${klient ? `${klient.nazwa} — ${klient.notatki || "brak notatek"}` : "nieznany"}

ZGŁOSZENIE:
Tytuł: ${ticket.tytul}
Kategoria: ${ticket.kategoria}
Priorytet nadany: ${ticket.priorytet}
Opis: ${ticket.opis}

Dostępne kategorie: ${settings.kategorie.join(", ")}
Dostępne priorytety: krytyczny, wysoki, normalny, niski

Odpowiedz WYŁĄCZNIE poprawnym obiektem JSON (bez markdown, bez komentarzy) o strukturze:
{
  "interpretacja": "2-3 zdania: co najprawdopodobniej się dzieje i dlaczego",
  "kategoria_sugerowana": "jedna z dostępnych kategorii",
  "priorytet_sugerowany": "jeden z dostępnych priorytetów",
  "przyczyny": ["możliwa przyczyna 1", "możliwa przyczyna 2", "..."],
  "rozwiazania": ["konkretny krok 1 (od najprostszego/zdalnego)", "krok 2", "..."],
  "pytania_do_klienta": ["pytanie doprecyzowujące 1", "..."]
}`;

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: 1000,
      messages: [{ role: "user", content: prompt }],
    }),
  });
  const data = await response.json();
  const text = (data.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
  const clean = text.replace(/```json|```/g, "").trim();
  return JSON.parse(clean);
}

/* ————— główna aplikacja ————— */

export default function App() {
  const [view, setView] = useState("tickets");
  const [tickets, setTickets] = useState(seedTickets);
  const [clients, setClients] = useState(seedClients);
  const [settings, setSettings] = useState(defaultSettings);
  const [selectedId, setSelectedId] = useState(null);
  const [filtrStatus, setFiltrStatus] = useState("wszystkie");
  const [szukaj, setSzukaj] = useState("");

  const selected = tickets.find(t => t.id === selectedId) || null;
  const klientOf = t => clients.find(c => c.id === t.klientId);

  const filtered = useMemo(() => {
    return tickets
      .filter(t => filtrStatus === "wszystkie" || t.status === filtrStatus)
      .filter(t => {
        if (!szukaj.trim()) return true;
        const q = szukaj.toLowerCase();
        const k = klientOf(t);
        return t.tytul.toLowerCase().includes(q) || t.opis.toLowerCase().includes(q)
          || (k && k.nazwa.toLowerCase().includes(q)) || String(t.id).includes(q);
      })
      .sort((a, b) => b.id - a.id);
  }, [tickets, filtrStatus, szukaj, clients]);

  const updateTicket = (id, patch) =>
    setTickets(ts => ts.map(t => (t.id === id ? { ...t, ...patch } : t)));

  const addTicket = t => {
    const id = Math.max(0, ...tickets.map(x => x.id)) + 1;
    const now = new Date();
    const data = now.toISOString().slice(0, 16).replace("T", " ");
    setTickets(ts => [{ ...t, id, data, status: "nowe", analiza: null, notatki: [] }, ...ts]);
    setSelectedId(id);
    setView("tickets");
  };

  const counts = useMemo(() => {
    const c = { wszystkie: tickets.length };
    Object.keys(STATUSY).forEach(k => (c[k] = tickets.filter(t => t.status === k).length));
    return c;
  }, [tickets]);

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.ink, fontFamily: "'Inter', system-ui, sans-serif", display: "flex" }}>
      <style>{FONT_CSS}</style>

      {/* ——— pasek boczny ——— */}
      <aside style={{ width: 218, flexShrink: 0, borderRight: `1px solid ${T.line}`, background: T.surface, display: "flex", flexDirection: "column", position: "sticky", top: 0, height: "100vh" }}>
        <div style={{ padding: "22px 20px 18px", borderBottom: `1px solid ${T.lineSoft}` }}>
          <div style={{ fontFamily: "'Archivo', sans-serif", fontWeight: 800, fontSize: 17, letterSpacing: "-0.01em", display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: T.accent, display: "inline-block" }} />
            {settings.nazwaSerwisu}
          </div>
          <div style={{ ...mono, fontSize: 10, color: T.muted, marginTop: 4, letterSpacing: "0.08em" }}>PANEL SERWISANTA</div>
        </div>

        <nav style={{ padding: "14px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
          {[
            { id: "tickets", label: "Zgłoszenia", badge: counts.nowe > 0 ? counts.nowe : null },
            { id: "new", label: "Nowe zgłoszenie" },
            { id: "clients", label: "Klienci", badge2: clients.length },
            { id: "settings", label: "Ustawienia" },
          ].map(item => {
            const active = view === item.id;
            return (
              <button key={item.id}
                onClick={() => { setView(item.id); if (item.id !== "tickets") setSelectedId(null); }}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "9px 12px", borderRadius: 8, border: "none", cursor: "pointer",
                  fontSize: 13.5, fontWeight: active ? 600 : 500, textAlign: "left",
                  background: active ? T.accentSoft : "transparent",
                  color: active ? T.accent : T.ink, transition: "background .15s",
                }}>
                {item.label}
                {item.badge != null && (
                  <span style={{ ...mono, fontSize: 10.5, fontWeight: 600, background: T.accent, color: "#fff", borderRadius: 10, padding: "1px 7px" }}>{item.badge}</span>
                )}
                {item.badge2 != null && (
                  <span style={{ ...mono, fontSize: 10.5, color: T.muted }}>{item.badge2}</span>
                )}
              </button>
            );
          })}
        </nav>

        <div style={{ marginTop: "auto", padding: "16px 20px", borderTop: `1px solid ${T.lineSoft}`, fontSize: 11.5, color: T.muted, lineHeight: 1.5 }}>
          <div style={{ ...mono, fontSize: 10, letterSpacing: "0.08em", marginBottom: 4 }}>ANALIZA AI</div>
          Silnik diagnostyczny gotowy. Wskazówki dla modelu ustawisz w Ustawieniach.
        </div>
      </aside>

      {/* ——— treść ——— */}
      <main className="scroll-y" style={{ flex: 1, minWidth: 0, padding: "28px 34px", overflowY: "auto", height: "100vh" }}>
        {view === "tickets" && !selected && (
          <TicketList
            tickets={filtered} counts={counts} klientOf={klientOf}
            filtrStatus={filtrStatus} setFiltrStatus={setFiltrStatus}
            szukaj={szukaj} setSzukaj={setSzukaj}
            onOpen={id => setSelectedId(id)} onNew={() => setView("new")}
          />
        )}
        {view === "tickets" && selected && (
          <TicketDetail
            ticket={selected} klient={klientOf(selected)} settings={settings}
            onBack={() => setSelectedId(null)} updateTicket={updateTicket}
          />
        )}
        {view === "new" && (
          <NewTicket clients={clients} settings={settings} onSave={addTicket} onCancel={() => setView("tickets")} />
        )}
        {view === "clients" && <Clients clients={clients} setClients={setClients} tickets={tickets} />}
        {view === "settings" && <Settings settings={settings} setSettings={setSettings} />}
      </main>
    </div>
  );
}

/* ————— nagłówek sekcji ————— */
function PageHead({ title, sub, right }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 22, gap: 16, flexWrap: "wrap" }}>
      <div>
        <h1 style={{ fontFamily: "'Archivo', sans-serif", fontWeight: 800, fontSize: 26, letterSpacing: "-0.02em", margin: 0 }}>{title}</h1>
        {sub && <div style={{ fontSize: 13.5, color: T.muted, marginTop: 4 }}>{sub}</div>}
      </div>
      {right}
    </div>
  );
}

/* ————— lista zgłoszeń ————— */
function TicketList({ tickets, counts, klientOf, filtrStatus, setFiltrStatus, szukaj, setSzukaj, onOpen, onNew }) {
  const filtry = [["wszystkie", "Wszystkie"], ...Object.entries(STATUSY).map(([k, v]) => [k, v.label.charAt(0) + v.label.slice(1).toLowerCase()])];
  return (
    <div style={{ maxWidth: 980 }}>
      <PageHead title="Zgłoszenia" sub="Rejestr zgłoszeń serwisowych" right={<Btn onClick={onNew}>+ Nowe zgłoszenie</Btn>} />

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        {filtry.map(([k, label]) => {
          const active = filtrStatus === k;
          return (
            <button key={k} onClick={() => setFiltrStatus(k)}
              style={{
                padding: "6px 12px", borderRadius: 20, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                border: `1px solid ${active ? T.ink : T.line}`, background: active ? T.ink : T.surface,
                color: active ? "#fff" : T.muted, transition: "all .15s",
              }}>
              {label} <span style={{ ...mono, fontSize: 10.5, opacity: 0.7 }}>{counts[k]}</span>
            </button>
          );
        })}
        <input value={szukaj} onChange={e => setSzukaj(e.target.value)} placeholder="Szukaj: tytuł, klient, nr…"
          style={{ ...inputStyle, width: 230, marginLeft: "auto", padding: "8px 12px" }} />
      </div>

      <div style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, overflow: "hidden" }}>
        {tickets.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: T.muted, fontSize: 14 }}>
            Brak zgłoszeń dla wybranych filtrów. Dodaj nowe zgłoszenie, aby zacząć.
          </div>
        )}
        {tickets.map((t, i) => {
          const k = klientOf(t);
          return (
            <div key={t.id} className="row-hover" onClick={() => onOpen(t.id)}
              style={{
                display: "grid", gridTemplateColumns: "86px 1fr auto auto", gap: 14, alignItems: "center",
                padding: "14px 18px", cursor: "pointer",
                borderTop: i === 0 ? "none" : `1px solid ${T.lineSoft}`,
              }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <PriorityTick priorytet={t.priorytet} />
                <span style={{ ...mono, fontSize: 12, color: T.muted }}>ZGL-{String(t.id).padStart(4, "0")}</span>
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {t.tytul}
                  {t.analiza && <span title="Przeanalizowano przez AI" style={{ ...mono, fontSize: 9.5, color: T.violet, background: T.violetSoft, borderRadius: 3, padding: "1px 5px", marginLeft: 8, verticalAlign: "middle" }}>AI</span>}
                </div>
                <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>
                  {k ? k.nazwa : "—"} · {t.kategoria}
                </div>
              </div>
              <div style={{ ...mono, fontSize: 11, color: T.muted, whiteSpace: "nowrap" }}>{t.data}</div>
              <StatusChip status={t.status} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ————— szczegóły zgłoszenia + analiza AI ————— */
function TicketDetail({ ticket, klient, settings, onBack, updateTicket }) {
  const [analizuje, setAnalizuje] = useState(false);
  const [bladAI, setBladAI] = useState(null);
  const [nowaNotatka, setNowaNotatka] = useState("");

  const runAI = async () => {
    setAnalizuje(true); setBladAI(null);
    try {
      const wynik = await analizujZgloszenie(ticket, klient, settings);
      updateTicket(ticket.id, { analiza: wynik });
    } catch (e) {
      setBladAI("Analiza nie powiodła się — spróbuj ponownie. Model mógł zwrócić niepoprawny format.");
    } finally {
      setAnalizuje(false);
    }
  };

  const przyjmijSugestie = () => {
    if (!ticket.analiza) return;
    updateTicket(ticket.id, {
      kategoria: ticket.analiza.kategoria_sugerowana || ticket.kategoria,
      priorytet: PRIORYTETY[ticket.analiza.priorytet_sugerowany] ? ticket.analiza.priorytet_sugerowany : ticket.priorytet,
    });
  };

  const dodajNotatke = () => {
    if (!nowaNotatka.trim()) return;
    const data = new Date().toISOString().slice(0, 16).replace("T", " ");
    updateTicket(ticket.id, { notatki: [...ticket.notatki, { data, tekst: nowaNotatka.trim() }] });
    setNowaNotatka("");
  };

  const a = ticket.analiza;

  return (
    <div style={{ maxWidth: 980 }}>
      <button onClick={onBack} style={{ background: "none", border: "none", color: T.muted, fontSize: 13, cursor: "pointer", padding: 0, marginBottom: 14, fontWeight: 500 }}>
        ← Wróć do listy
      </button>

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 20, marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <div style={{ ...mono, fontSize: 12, color: T.muted, marginBottom: 6 }}>ZGL-{String(ticket.id).padStart(4, "0")} · {ticket.data}</div>
          <h1 style={{ fontFamily: "'Archivo', sans-serif", fontWeight: 800, fontSize: 24, letterSpacing: "-0.02em", margin: 0, maxWidth: 640 }}>{ticket.tytul}</h1>
          <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
            <StatusChip status={ticket.status} />
            <PriorityTick priorytet={ticket.priorytet} withLabel />
            <span style={{ fontSize: 12.5, color: T.muted }}>{ticket.kategoria}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {Object.entries(STATUSY).map(([k, s]) => (
            <Btn key={k} small kind="ghost" onClick={() => updateTicket(ticket.id, { status: k })}
              style={ticket.status === k ? { borderColor: s.color, color: s.color, fontWeight: 700 } : {}}>
              {s.label.charAt(0) + s.label.slice(1).toLowerCase()}
            </Btn>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 18, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {/* opis */}
          <section style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, padding: 20 }}>
            <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: T.muted, marginBottom: 8 }}>Opis zgłoszenia</div>
            <p style={{ fontSize: 14, lineHeight: 1.65, margin: 0 }}>{ticket.opis}</p>
          </section>

          {/* analiza AI */}
          <section style={{ background: T.ink, color: "#E8ECEA", borderRadius: 12, padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: a || analizuje ? 16 : 8, gap: 12, flexWrap: "wrap" }}>
              <div style={{ ...mono, fontSize: 11, letterSpacing: "0.1em", color: "#9FB0AA", display: "flex", alignItems: "center", gap: 8 }}>
                <span className={analizuje ? "spin-dot" : ""} style={{ width: 7, height: 7, borderRadius: "50%", background: analizuje ? T.warn : a ? "#4ADE80" : "#5A6763", display: "inline-block" }} />
                ANALIZA DIAGNOSTYCZNA AI
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {a && <Btn small kind="ghost" style={{ borderColor: "#3A4744", color: "#C9D2CF" }} onClick={przyjmijSugestie}>Przyjmij sugestie</Btn>}
                <Btn small onClick={runAI} disabled={analizuje} style={{ background: T.accent }}>
                  {analizuje ? "Analizuję…" : a ? "Analizuj ponownie" : "Uruchom analizę"}
                </Btn>
              </div>
            </div>

            {!a && !analizuje && !bladAI && (
              <p style={{ fontSize: 13, color: "#9FB0AA", margin: 0, lineHeight: 1.6 }}>
                Model przeanalizuje treść zgłoszenia i kontekst klienta, a następnie zaproponuje interpretację, prawdopodobne przyczyny i kolejne kroki naprawcze.
              </p>
            )}
            {bladAI && <p style={{ fontSize: 13, color: "#FCA5A5", margin: 0 }}>{bladAI}</p>}
            {analizuje && (
              <p style={{ ...mono, fontSize: 12.5, color: "#9FB0AA", margin: 0 }}>› Przetwarzam opis usterki i kontekst klienta…</p>
            )}

            {a && !analizuje && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.08em", color: "#7E8D88", marginBottom: 6 }}>INTERPRETACJA</div>
                  <p style={{ fontSize: 14, lineHeight: 1.65, margin: 0 }}>{a.interpretacja}</p>
                </div>

                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ ...mono, fontSize: 11.5, background: "#26312E", padding: "5px 10px", borderRadius: 6 }}>
                    kategoria → <b style={{ color: "#fff" }}>{a.kategoria_sugerowana}</b>
                  </span>
                  <span style={{ ...mono, fontSize: 11.5, background: "#26312E", padding: "5px 10px", borderRadius: 6 }}>
                    priorytet → <b style={{ color: PRIORYTETY[a.priorytet_sugerowany]?.color || "#fff" }}>{a.priorytet_sugerowany}</b>
                  </span>
                </div>

                {a.przyczyny?.length > 0 && (
                  <div>
                    <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.08em", color: "#7E8D88", marginBottom: 6 }}>MOŻLIWE PRZYCZYNY</div>
                    {a.przyczyny.map((p, i) => (
                      <div key={i} style={{ fontSize: 13.5, lineHeight: 1.6, display: "flex", gap: 8, marginBottom: 3 }}>
                        <span style={{ color: T.warn, ...mono, fontSize: 12 }}>?</span> {p}
                      </div>
                    ))}
                  </div>
                )}

                {a.rozwiazania?.length > 0 && (
                  <div>
                    <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.08em", color: "#7E8D88", marginBottom: 6 }}>PROPONOWANE ROZWIĄZANIA</div>
                    {a.rozwiazania.map((r, i) => (
                      <div key={i} style={{ fontSize: 13.5, lineHeight: 1.6, display: "flex", gap: 10, marginBottom: 6 }}>
                        <span style={{ ...mono, fontSize: 11.5, color: "#4ADE80", flexShrink: 0, paddingTop: 1 }}>{String(i + 1).padStart(2, "0")}</span>
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>
                )}

                {a.pytania_do_klienta?.length > 0 && (
                  <div>
                    <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.08em", color: "#7E8D88", marginBottom: 6 }}>PYTANIA DO KLIENTA</div>
                    {a.pytania_do_klienta.map((p, i) => (
                      <div key={i} style={{ fontSize: 13.5, lineHeight: 1.6, color: "#C9D2CF", marginBottom: 3 }}>· {p}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* notatki serwisowe */}
          <section style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, padding: 20 }}>
            <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: T.muted, marginBottom: 12 }}>Notatki serwisowe</div>
            {ticket.notatki.length === 0 && <div style={{ fontSize: 13, color: T.muted, marginBottom: 12 }}>Brak notatek. Zapisuj tu przebieg prac.</div>}
            {ticket.notatki.map((n, i) => (
              <div key={i} style={{ borderLeft: `2px solid ${T.line}`, paddingLeft: 12, marginBottom: 12 }}>
                <div style={{ ...mono, fontSize: 10.5, color: T.muted, marginBottom: 3 }}>{n.data}</div>
                <div style={{ fontSize: 13.5, lineHeight: 1.55 }}>{n.tekst}</div>
              </div>
            ))}
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <input value={nowaNotatka} onChange={e => setNowaNotatka(e.target.value)}
                onKeyDown={e => e.key === "Enter" && dodajNotatke()}
                placeholder="Dodaj notatkę z przebiegu naprawy…" style={{ ...inputStyle, flex: 1 }} />
              <Btn kind="ghost" onClick={dodajNotatke}>Zapisz</Btn>
            </div>
          </section>
        </div>

        {/* karta klienta */}
        <aside style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, padding: 20, position: "sticky", top: 0 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: T.muted, marginBottom: 10 }}>Klient</div>
          {klient ? (
            <>
              <div style={{ fontFamily: "'Archivo', sans-serif", fontWeight: 700, fontSize: 16, marginBottom: 10 }}>{klient.nazwa}</div>
              <div style={{ fontSize: 13, lineHeight: 1.7, color: T.ink }}>
                <div>{klient.kontakt}</div>
                <div style={{ ...mono, fontSize: 12, color: T.muted }}>{klient.telefon}</div>
                <div style={{ ...mono, fontSize: 12, color: T.muted, wordBreak: "break-all" }}>{klient.email}</div>
              </div>
              {klient.notatki && (
                <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.lineSoft}`, fontSize: 12.5, lineHeight: 1.6, color: T.muted }}>
                  {klient.notatki}
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 13, color: T.muted }}>Nie przypisano klienta.</div>
          )}
        </aside>
      </div>
    </div>
  );
}

/* ————— nowe zgłoszenie ————— */
function NewTicket({ clients, settings, onSave, onCancel }) {
  const [f, setF] = useState({
    klientId: clients[0]?.id ?? null, tytul: "", opis: "",
    priorytet: "normalny", kategoria: settings.kategorie[0] || "Inne",
  });
  const [blad, setBlad] = useState(null);
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));

  const zapisz = () => {
    if (!f.tytul.trim()) return setBlad("Podaj tytuł zgłoszenia — krótko, co nie działa.");
    if (!f.opis.trim()) return setBlad("Opisz usterkę — im więcej szczegółów, tym lepsza analiza AI.");
    setBlad(null);
    onSave({ ...f, klientId: Number(f.klientId) });
  };

  return (
    <div style={{ maxWidth: 640 }}>
      <PageHead title="Nowe zgłoszenie" sub="Zarejestruj usterkę lub zlecenie serwisowe" />
      <div style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, padding: 24 }}>
        <Field label="Klient">
          <select value={f.klientId ?? ""} onChange={e => set("klientId", e.target.value)} style={inputStyle}>
            {clients.map(c => <option key={c.id} value={c.id}>{c.nazwa}</option>)}
          </select>
        </Field>
        <Field label="Tytuł zgłoszenia">
          <input value={f.tytul} onChange={e => set("tytul", e.target.value)} placeholder="np. Komputer w recepcji nie uruchamia się" style={inputStyle} />
        </Field>
        <Field label="Opis usterki" hint="Objawy, od kiedy występuje, co się zmieniło. Te informacje trafią do analizy AI.">
          <textarea value={f.opis} onChange={e => set("opis", e.target.value)} rows={6}
            placeholder="Opisz dokładnie, co się dzieje…" style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6 }} />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <Field label="Priorytet">
            <select value={f.priorytet} onChange={e => set("priorytet", e.target.value)} style={inputStyle}>
              {Object.entries(PRIORYTETY).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
            </select>
          </Field>
          <Field label="Kategoria">
            <select value={f.kategoria} onChange={e => set("kategoria", e.target.value)} style={inputStyle}>
              {settings.kategorie.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </Field>
        </div>
        {blad && <div style={{ fontSize: 13, color: T.crit, marginBottom: 14 }}>{blad}</div>}
        <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
          <Btn onClick={zapisz}>Zapisz zgłoszenie</Btn>
          <Btn kind="ghost" onClick={onCancel}>Anuluj</Btn>
        </div>
      </div>
    </div>
  );
}

/* ————— klienci ————— */
function Clients({ clients, setClients, tickets }) {
  const empty = { nazwa: "", kontakt: "", email: "", telefon: "", notatki: "" };
  const [f, setF] = useState(empty);
  const [dodawanie, setDodawanie] = useState(false);
  const [blad, setBlad] = useState(null);
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));

  const dodaj = () => {
    if (!f.nazwa.trim()) return setBlad("Nazwa firmy jest wymagana.");
    setBlad(null);
    const id = Math.max(0, ...clients.map(c => c.id)) + 1;
    setClients(cs => [...cs, { ...f, id }]);
    setF(empty); setDodawanie(false);
  };

  const usun = id => {
    const ma = tickets.some(t => t.klientId === id);
    if (ma) return setBlad("Ten klient ma przypisane zgłoszenia — najpierw je zamknij lub przepisz.");
    setBlad(null);
    setClients(cs => cs.filter(c => c.id !== id));
  };

  return (
    <div style={{ maxWidth: 860 }}>
      <PageHead title="Klienci" sub="Baza obsługiwanych firm — kontekst dla analizy AI"
        right={<Btn onClick={() => { setDodawanie(d => !d); setBlad(null); }}>{dodawanie ? "Zamknij formularz" : "+ Dodaj klienta"}</Btn>} />

      {blad && <div style={{ fontSize: 13, color: T.crit, marginBottom: 14 }}>{blad}</div>}

      {dodawanie && (
        <div style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, padding: 22, marginBottom: 18 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Field label="Nazwa firmy"><input value={f.nazwa} onChange={e => set("nazwa", e.target.value)} placeholder="np. Hurtownia Delta" style={inputStyle} /></Field>
            <Field label="Osoba kontaktowa"><input value={f.kontakt} onChange={e => set("kontakt", e.target.value)} placeholder="Imię i nazwisko" style={inputStyle} /></Field>
            <Field label="E-mail"><input value={f.email} onChange={e => set("email", e.target.value)} placeholder="adres@firma.pl" style={inputStyle} /></Field>
            <Field label="Telefon"><input value={f.telefon} onChange={e => set("telefon", e.target.value)} placeholder="np. 61 000 00 00" style={inputStyle} /></Field>
          </div>
          <Field label="Notatki o infrastrukturze" hint="Serwery, liczba stanowisk, SLA — AI wykorzysta to przy analizie zgłoszeń tego klienta.">
            <textarea value={f.notatki} onChange={e => set("notatki", e.target.value)} rows={3} style={{ ...inputStyle, resize: "vertical" }} />
          </Field>
          <Btn onClick={dodaj}>Zapisz klienta</Btn>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
        {clients.map(c => {
          const licznik = tickets.filter(t => t.klientId === c.id).length;
          const otwarte = tickets.filter(t => t.klientId === c.id && t.status !== "zamkniete").length;
          return (
            <div key={c.id} style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, padding: 18, display: "flex", flexDirection: "column" }}>
              <div style={{ fontFamily: "'Archivo', sans-serif", fontWeight: 700, fontSize: 15.5, marginBottom: 8 }}>{c.nazwa}</div>
              <div style={{ fontSize: 13, lineHeight: 1.65, color: T.ink }}>
                {c.kontakt && <div>{c.kontakt}</div>}
                {c.telefon && <div style={{ ...mono, fontSize: 12, color: T.muted }}>{c.telefon}</div>}
                {c.email && <div style={{ ...mono, fontSize: 12, color: T.muted, wordBreak: "break-all" }}>{c.email}</div>}
              </div>
              {c.notatki && <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.55, marginTop: 10 }}>{c.notatki}</div>}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "auto", paddingTop: 14 }}>
                <span style={{ ...mono, fontSize: 11, color: otwarte > 0 ? T.warn : T.muted }}>
                  {licznik} zgł. · {otwarte} otwarte
                </span>
                <Btn small kind="danger" onClick={() => usun(c.id)}>Usuń</Btn>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ————— ustawienia ————— */
function Settings({ settings, setSettings }) {
  const [nowaKat, setNowaKat] = useState("");
  const [zapisano, setZapisano] = useState(false);
  const set = (k, v) => { setSettings(s => ({ ...s, [k]: v })); setZapisano(false); };

  const dodajKat = () => {
    const k = nowaKat.trim();
    if (!k || settings.kategorie.includes(k)) return;
    set("kategorie", [...settings.kategorie, k]);
    setNowaKat("");
  };

  return (
    <div style={{ maxWidth: 640 }}>
      <PageHead title="Ustawienia" sub="Konfiguracja serwisu i zachowania analizy AI" />

      <div style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 12, padding: 24, marginBottom: 18 }}>
        <Field label="Nazwa serwisu" hint="Wyświetlana w pasku bocznym.">
          <input value={settings.nazwaSerwisu} onChange={e => set("nazwaSerwisu", e.target.value)} style={inputStyle} />
        </Field>

        <Field label="Kategorie zgłoszeń" hint="Używane w formularzu i sugerowane przez AI.">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
            {settings.kategorie.map(k => (
              <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, background: T.bg, border: `1px solid ${T.line}`, borderRadius: 20, padding: "5px 6px 5px 12px" }}>
                {k}
                <button onClick={() => set("kategorie", settings.kategorie.filter(x => x !== k))}
                  aria-label={`Usuń kategorię ${k}`}
                  style={{ border: "none", background: "transparent", cursor: "pointer", color: T.muted, fontSize: 13, lineHeight: 1, padding: "2px 6px" }}>×</button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={nowaKat} onChange={e => setNowaKat(e.target.value)} onKeyDown={e => e.key === "Enter" && dodajKat()}
              placeholder="Nowa kategoria…" style={{ ...inputStyle, flex: 1 }} />
            <Btn kind="ghost" onClick={dodajKat}>Dodaj</Btn>
          </div>
        </Field>
      </div>

      <div style={{ background: T.ink, borderRadius: 12, padding: 24, color: "#E8ECEA" }}>
        <div style={{ ...mono, fontSize: 11, letterSpacing: "0.1em", color: "#9FB0AA", marginBottom: 10 }}>WSKAZÓWKI DLA ANALIZY AI</div>
        <p style={{ fontSize: 13, color: "#9FB0AA", lineHeight: 1.6, marginTop: 0, marginBottom: 14 }}>
          Tutaj „uczysz" model, jak pracuje Twój serwis: preferowane procedury, typowy sprzęt klientów, zasady bezpieczeństwa. Treść trafia do każdej analizy zgłoszenia.
        </p>
        <textarea value={settings.wskazowkiAI} onChange={e => set("wskazowkiAI", e.target.value)} rows={6}
          style={{ ...inputStyle, background: "#26312E", border: "1px solid #3A4744", color: "#E8ECEA", resize: "vertical", lineHeight: 1.6 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
          <Btn onClick={() => setZapisano(true)} style={{ background: T.accent }}>Zapisz wskazówki</Btn>
          {zapisano && <span style={{ ...mono, fontSize: 12, color: "#4ADE80" }}>✓ Zapisano — obowiązują przy kolejnych analizach</span>}
        </div>
      </div>
    </div>
  );
}
