// Polish labels for what the API returns (feature and evidence names follow ads/explain/catalog.py).

export const SCAM = {
  fake_investment: "fałszywa inwestycja", fake_online_casino: "fałszywe kasyno", miracle_cure: "cudowny lek",
  banking_phishing: "phishing bankowy", fake_giveaway: "fałszywe rozdanie", fake_subsidy_or_payout: "fałszywa dopłata / wypłata",
  fake_online_shop: "fałszywy sklep", political_disinformation: "dezinformacja polityczna",
  impersonation_other: "podszywanie się (inne)", not_suspicious: "niepodejrzane", other: "inne",
};
export const STATUS = {  // decision status -> [css class, stamp, heading]
  duplicate: ["ok", "Duplikat", "Ta sprawa już jest w bazie"],
  same_content: ["ok", "Ta sama treść", "Treść znanej kampanii na innym hoście"],
  confirmed: ["ok", "Potwierdzona", "Pasuje do znanej kampanii"],
  likely: ["info", "Prawdopodobna", "Prawdopodobnie znana kampania"],
  suggested_family: ["warn", "Możliwa rodzina", "Przypomina znaną rodzinę oszustw, za słabo na kampanię"],
  new_unconfirmed: ["warn", "Nowa", "Nowa kampania, do potwierdzenia przez analityka"],
};
export const GROUP = {  // feature group -> [label, colour]
  infrastructure: ["Infrastruktura", "#b42318"], core: ["Typ oszustwa i temat", "#1c4f8a"],
  templates: ["Szablony, lejek, szkielet strony", "#6b4fa0"], persuasion: ["Techniki perswazji", "#9a5b00"],
  entities: ["Produkt, osoby, firmy, media", "#17643a"], text: ["Narracja i tekst", "#2f7f95"],
  surface: ["Rekwizyty, kwoty, miejsca, logotypy", "#7d848c"], other: ["Inne", "#aab1b8"],
};
export const FEATURE = {
  tracker_ids: "Identyfikatory trackerów", redirect_chain_domains: "Domeny przekierowań",
  dom_and_form_clues: "Endpointy, formularze, pliki", ad_library_page_name: "Strona sponsorująca",
  scam_type: "Typ oszustwa", topic: "Temat", ad_creative_template: "Szablon reklamy",
  landing_page_template: "Szablon strony docelowej", funnel_stages: "Etapy lejka", persuasion_devices: "Techniki perswazji",
  product_name: "Produkt / platforma", featured_people: "Osoby", companies: "Firmy i instytucje",
  impersonated_media: "Podszywane media", narrative: "Schemat narracji", promise: "Obietnica i mechanizm",
  call_to_action: "Wezwanie do działania", summary: "Streszczenie porównawcze", keywords: "Słowa kluczowe",
  setting_and_props: "Sceneria i rekwizyty", amounts_dates_locations: "Kwoty, daty, miejsca",
  page_structure: "Szkielet strony (HTML, klasy CSS)", page_assets: "Zestaw obrazów strony",
  url_template: "Szablon śledzenia w adresach URL", logos_and_badges: "Logotypy i oznaczenia",
  infra_metadata: "Metadane domen i infrastruktury",
};
const EVIDENCE = {
  tracker: "wspólny identyfikator trackera", endpoint: "wspólne endpointy platformy (sesja/formularz)",
  file: "wspólny charakterystyczny plik strony", domain: "wspólna domena", page: "ta sama strona sponsorująca",
  images: "wspólne identyczne obrazy strony (ten sam zestaw)", adid: "ten sam identyfikator kampanii reklamowej",
  tracking: "ten sam własny szablon parametrów śledzenia", certificate: "domeny na jednym certyfikacie", other: "dowód",
};
const RAW_EVIDENCE = [["shared tracker ID", "tracker"], ["shared session/form endpoint", "endpoint"],
  ["shared page images", "images"], ["same ad campaign ID", "adid"], ["same tracking template", "tracking"],
  ["domains on one certificate", "certificate"], ["shared distinctive script/style file", "file"],
  ["shared domain", "domain"], ["same sponsoring page", "page"]];
export const MISSING = { a: "brak danych po stronie A", b: "brak danych po stronie B", both: "brak danych po obu stronach",
  unknown: "nie do porównania", supporting: "różne, ale to cecha wspierająca: różnica nie obniża wyniku" };
const ENUM_FEATURES = new Set(["scam_type", "topic", "ad_creative_template", "landing_page_template", "persuasion_devices", "funnel_stages"]);

export const pretty = (v) => (v == null ? "–" : SCAM[v] || String(v).replaceAll("_", " "));
export const valueText = (feature, v) => (ENUM_FEATURES.has(feature) ? pretty(v) : String(v));
export const featureName = (f) => FEATURE[f] || f;
export const evText = (e) => `${EVIDENCE[e.kind] || e.kind}: ${String(e.value).replace(/ identical image files$/, " identycznych plików")}`;
export const linkKind = (e) => (e.must_link ? "łączy w kampanię" : e.family_link ? "łączy w rodzinę" : "wspierający");

export function evRaw(s) {  // a strong_links string from the API, in Polish
  const hit = RAW_EVIDENCE.find(([prefix]) => s.startsWith(prefix));
  return hit ? evText({ kind: hit[1], value: s.slice(hit[0].length + 2) }) : s;
}

export function infraText(fact) {  // one fact that can link two domains (ads/preprocess/domain_meta.py)
  const [kind, ...rest] = fact.split(":");
  const v = rest.join(":");
  if (kind === "regbatch") {
    const [day, registrar] = v.split("|");
    return `zarejestrowane tego samego dnia (${day}) u tego samego rejestratora (${registrar})`;
  }
  return { ns: `serwery nazw: ${v}`, net: `sieć hostingu: ${v}`, cert_san: `na wspólnym certyfikacie z ${v}` }[kind] || fact;
}

export function infraSummary(facts) {  // the case card line: registration, age, registrar, hosting, certificates
  const get = (k) => facts.filter((f) => f.startsWith(k + ":")).map((f) => f.slice(k.length + 1)).join(", ");
  const parts = [
    get("registered") && `zarejestrowana ${get("registered")}`,
    get("age_at_capture_days") && `${get("age_at_capture_days")} dni przed nagraniem`,
    get("registrar") && `rejestrator: ${get("registrar")}`,
    get("net") && `hosting: ${get("net")}`,
    get("certs") && `certyfikaty: ${get("certs")}`,
    get("wayback_first") && `archiwum od ${get("wayback_first")}`,
    facts.includes("status:nxdomain") && "domena już nie istnieje",
    facts.includes("warning_list:cert_pl") && "na liście ostrzeżeń CERT Polska",
  ];
  return parts.filter(Boolean).join(" · ");
}
