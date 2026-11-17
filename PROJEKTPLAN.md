# Digitaler Zwilling der Eisenbahnstrecke – Projekt- und Messplan

Stand: 17.11.2026. Neuer Entwurf von null; vorhandene Laboransätze dienen ausschließlich als Kontext. Es wurde noch kein neuer Logger oder Schätzer implementiert und keine reale Messung durchgeführt.

## 1. Ziel und erste Abgrenzung

Ein beobachtender digitaler Zwilling soll aus einem Ereignisstrom rekonstruieren, welche Streckenabschnitte ein identifizierter Zug befahren kann, und diese Beobachtungen mit einem vorher festgelegten Fahrtauftrag vergleichen. Zunächst gespeicherte Logs kausal abspielen, später denselben Kern mit MQTT speisen.

Erstes Ergebnis: ein Zug auf einer bekannten Teilstrecke, bestätigte Sensorpassagen, nachvollziehbare Abschnittsschätzung und Meldungen für Abweichungen, Verzögerungen und unzureichende Daten. Kein Anspruch auf zentimetergenaue Position. Die Steuerung bleibt zunächst bei Rocrail.

Es gibt drei getrennte Aussagen:

1. **Soll:** Welchen Weg soll der Zug fahren?
2. **Beobachtung:** Welche Sensoren haben tatsächlich gemeldet, welche Bedienhandlungen wurden registriert?
3. **Schätzung:** Welche Aufenthaltsorte und Zugidentitäten sind mit den Beobachtungen vereinbar?

Rocrails Blockzuordnung ist eine zusätzliche Steuerungsannahme. Sie darf einen hilfreichen Vergleich liefern, aber die unabhängige Beobachtung nicht ersetzen. Insbesondere darf die Lokalisierung den Sollweg nicht als zwingende Wahrheit verwenden: Sonst kann sie einen falschen Weg gerade nicht erkennen.

## 2. Befunde aus den Kontextdateien

Explizit geprüfte Quellen:

- `../Labor Rocrail/Gruppe2.log`, `Gruppe2_2.log`, `plan.xml`, beide Analyse-Notebooks und bestehender Makrograph/Player.
- `../Labor Zeitreihen/Übung_-_Interpolation.ipynb`.
- `/home/cedrikmt/Downloads/Labor_Logistiksimulation/Labor Logistiksimulation/Anwendung.py` und `RocRail-Projekt/project/rocrail.ini`.
- Der dortige `RocRail-Projekt/project/plan.xml` ist zum Prüfzeitpunkt bytegleich mit `../Labor Rocrail/plan.xml`.

| Quelle | Gesicherter Befund | Konsequenz |
|---|---|---|
| `plan.xml` | 34 Blöcke, 66 Rückmelder, 118 konfigurierte Fahrstraßen, 68 Weichenobjekte und 11 Loks | Vorhandene Konfiguration als Ausgangspunkt importieren und vor Ort prüfen; Objektzahlen sind keine Zählung physisch unabhängiger Geräte. |
| Fahrstraßen | Start/Ziel in `bka`/`bkb`, Seiten in `bkaside`/`bkbside`, Weichenbedingungen in `swcmd`; acht Start-Ziel-Paare kommen mehrfach vor | Gerichtete Kanten mit eigener Fahrstraßen-ID und Seiteninformation erhalten. Nicht nach Start/Ziel zusammenwerfen. |
| Block-Rückmelder | `fbevent` verbindet Sensor, `enter`/`in`, Herkunft und Fahrstraße | Die Bedeutung eines Sensors hängt von der Einfahrtrichtung/Fahrstraße ab. |
| `Gruppe2.log` | 778 Nachrichten, 52 `fb`, 106 `lc`, vier `clock` im Minutenabstand | Gute Quelle für Format/Reihenfolge, keine präzise Fahrzeitkalibrierung. |
| `Gruppe2_2.log` | 930 Nachrichten, 112 `fb`, 103 `lc`, nur ein `clock` | Zeitverlauf nicht aus der Nachrichtenanzahl rekonstruieren. |
| `lc` | Zug-ID, `V`, `dir`, `blockid`, `destblockid`; `V_realkmh` in beiden Logs immer 0 | Zugidentität und Steuerinformationen vorhanden; kein gemessener Ortswert und keine gemessene Geschwindigkeit. |
| `fb` | Binär; manche Meldungen nur über Hardwareadresse und Interface identifiziert | Rohidentität erhalten, unbekannte Sensoren melden und nicht stillschweigend entfernen. |
| `Gruppe2_2.log` vs. Plan | 71 unterschiedliche `st`-IDs des Logs fehlen als exakte IDs im aktuellen Plan, darunter `R_AllTournout` | Versions-/Namensabgleich erforderlich. Das beweist nicht, dass 71 physische Wege fehlen. |
| Längen | Bei allen `bk` und `st` steht `len=0` | Keine metrischen Fahrzeiten aus diesen Feldern oder Bildschirmkoordinaten ableiten. |
| Alter Player | Verwendet vollständige spätere Blockfolgen und spätere Ankunftszeiten, ordnet teils erstem passenden Zug zu | Rückblickende Animation ist keine belastbare kausale Live-Lokalisierung. |
| Zeitreihen-Notebook | Synthetischer verrauschter Sinus; lineares Auffüllen, Polynom- und Logarithmusfit | Keine fehlenden binären Flanken oder Ereigniszeiten daraus erzeugen. |

Konkretes Richtungsbeispiel aus `plan.xml`: Für `hbf_1` ist `fb15` bei Einfahrt aus `west_ccw_3` ein `in`-Melder, bei Einfahrt aus `ost_cw_2` dagegen ein `enter`-Melder. Ein globales Mapping `fb15 = Ankunft` wäre falsch.

Die alte `Anwendung.py` sendet erste Fahrtaufträge vor dem Öffnen der Logdatei und schreibt im Loop empfangene Nachrichten ohne eigenen Zeitstempel. Ein Aufruf von `sys.stdout.flush()` sichert nicht den Dateipuffer der Logdatei. Den alten Ablauf deshalb nicht ungeprüft als neuen Messlogger verwenden.

## 3. Modell und Architektur

### Datenfluss

Rohdaten werden unverändert archiviert. Ein Eingangsadapter erzeugt normalisierte Ereignisse. Auf derselben Ereignisfolge arbeiten Lokalisierung und Soll-Ist-Prüfung; die Darstellung liest deren Ergebnisse. Ein Logadapter und später ein MQTT-Adapter sollen dasselbe interne Format liefern.

Vorgeschlagene Bausteine:

| Baustein | Verantwortung |
|---|---|
| Erfassung | Nachrichten vollständig abgrenzen, zeitstempeln, Sequenznummer vergeben, Empfang/Versand/Bedienmarker trennen, Verbindungsabbrüche dokumentieren |
| Normalisierung | XML-Typ und Attribute erhalten, Adressen auf IDs abbilden, unbekannte Objekte und Datenlücken kennzeichnen |
| Anlagenmodell | Blöcke, Blockseiten, Sensorzuordnungen, Fahrstraßen, Weichenanforderungen und Modellversion |
| Lokalisierung | Zustandsmenge je Zug aus bisherigen Sensoren und physisch zulässigen Übergängen fortschreiben |
| Zeitmodell | Abschnittszeiten samt Streuung nach Zug, Richtung, Fahrstufe und Betriebszustand |
| Sollplanung | Vor Fahrtbeginn nachvollziehbaren Sollweg und zulässige Alternativen festlegen |
| Validierung | Erwartete gegen beobachtete Sensor-/Abschnittsfolge prüfen; Evidenz und Unsicherheit ausgeben |
| Replay/Darstellung | Ereignisgetreues Abspielen, Zustand und Begründung anzeigen, keine zukünftigen Ereignisse an den Schätzer geben |

Starttechnik: Python, Standardbibliothek für XML/JSON, NetworkX für Graphen und Pandas für Auswertung. ML, Datenbank, 3D-Modell und aufwendige Weboberfläche sind zunächst nicht erforderlich. Notebooks dürfen Ergebnisse untersuchen; der Kern sollte als getrennte Python-Module reproduzierbar laufen.

### Topologie: zunächst zwei zusammenhängende Ebenen

**Planungsgraph:** Blöcke mit Seiten-/Richtungszustand als Knoten bzw. Zustände; konfigurierte Fahrstraßen als gerichtete, identifizierbare Kanten. Eine Implementierung kann einen gerichteten Multigraphen verwenden. Die Einfahrseite muss bei zulässigen Folgebewegungen berücksichtigt werden; ein reiner Blockname reicht an Kehren oder bei Richtungswechseln nicht immer.

**Beobachtungsmodell:** Für jede Fahrstraße die zugehörigen Sensoren und ihre richtungsabhängige Bedeutung hinterlegen. Bei nicht beobachtbaren Abzweigen Kandidaten offenhalten. Ein eigener Sensorgraph ist später möglich, aber die Zuordnung zu Blockseiten und Fahrstraßen muss erhalten bleiben.

Bildschirmkoordinaten aus Rocrail sind Darstellungsdaten. Geometrie und späterer Nachbau des Tischaufbaus erhalten eigene Koordinaten. Der Bahnhofsmakrograph ist eine abgeleitete Übersicht, keine ausreichende Grundlage der Lokalisierung.

Konfiguration ist nicht automatisch physische Wahrheit: Verbindungen, Weichenobjekte, mögliche Umkehrfahrten und Sensornamen an der Anlage validieren. Die 118 Fahrstraßen nicht pauschal als aktuell frei befahrbar behandeln.

### Positionsrekonstruktion

Bekannter Startzustand: reale Zugidentität, Abschnitt und Orientierung. Danach für jede Sensorflanke prüfen:

1. Welche Abschnitte sind vom letzten Zustand physisch erreichbar?
2. Welche Fahrtrichtungen und dokumentierten Weicheninformationen sind damit vereinbar?
3. Welche Züge kommen für dieses Ereignis infrage?
4. Welche Hypothesen bleiben unter Berücksichtigung der Datenqualität bestehen?

Ein eindeutiger Sensor ordnet einen Zug einem Bereich zu. Zwischen Sensoren bleibt dessen Position geschätzt. Mehrere plausible Züge/Wege bleiben als gemeinsame Hypothesen erhalten; ein Ereignis darf nicht beliebig zwei Zügen gleichzeitig zugeschrieben werden. Mit Mehrzugbetrieb kommen globale Konsistenzbedingungen hinzu, etwa gegenseitige Ausschlüsse und bekannte Reihenfolgen. Ein einzelner Impuls beweist nicht automatisch, dass der gesamte Zug einen Abschnitt freigegeben hat.

Zustand je Zug beispielsweise: letzter bestätigter Sensor mit Zeit, möglicher Abschnitt bzw. Kandidatenmenge, Orientierung, letzter Steuerwert, Bestätigungsquelle und Datenqualitätsstatus. Begriffe: `bestaetigt`, `geschaetzt`, `mehrdeutig`, `unbekannt`. Prozentuale Konfidenzen erst verwenden, wenn sie kalibriert sind.

Zeitfenster helfen bei der Plausibilität, dürfen aber ohne weitere Evidenz weder einen langen Halt als falschen Weg beweisen noch eine physisch mögliche, verspätete Hypothese beseitigen. `dir=true` muss vor Ort mit Lokorientierung und Blockseiten verknüpft werden; daraus folgt nicht global eine Himmelsrichtung.

Bei symmetrischen Verläufen, unbekannten Startpositionen oder mehreren gleich plausiblen Zügen kann Identität aus binären Sensoren prinzipiell unentscheidbar bleiben. Dann zusätzliche Anfangsinformation, beobachtete Referenzpassagen oder weitere Sensorik benötigen. Der Sollweg darf diese Informationslücke nicht kaschieren.

### Fahrzeitgewichte

Zunächst empirische Abschnittszeiten statt `Laenge/Geschwindigkeit` verwenden. Messdefinition vorab festlegen, etwa steigende Flanke von Sensor A bis steigende Flanke von Sensor B in einer bestimmten Richtung. Zu jeder Graphkante muss klar sein, auf welche Referenzpassagen sich ihre Zeit bezieht; aufeinanderfolgende Gewichte dürfen keine Lücken oder doppelt gezählten Zeiten erzeugen.

Ein zweites Zeitmaß ist Auftrag bis Ankunft. Es enthält Disposition, Wartezeit, Beschleunigung, Fahrzeit und Bremsen und ist deshalb keine reine Kantenfahrzeit. Stillstand, Blockierungszeit und Durchfahrt getrennt markieren. `on → off` eines Sensors misst eine Detektionsdauer, nicht ohne Weiteres die Reisezeit zwischen zwei Orten.

Anfangs nach Kante/Fahrstraße, Richtung, Zug und Fahrstufe gruppieren. Median, Streuung und Stichprobenzahl speichern; bei wenigen Messungen vorläufige Min/Max-Spannen ausweisen. 3–5 Wiederholungen sind eine erste Orientierung, keine belastbar geschätzten Extremquantile.

`V` ist ein Steuerwert. Eine Halbierung verdoppelt die Fahrzeit nicht zwingend; Anfahr-/Bremsrampen, Lok, Last, Kurven und Wartezeiten wirken mit. Später ein zeitabhängiges Modell mit Geschwindigkeitshistorie entwickeln. Mehrere Zwischenstopps dürfen nicht in eine vermeintliche Konstantgeschwindigkeitskalibrierung eingehen.

### Sollweg und Entscheidung

Für den ersten Versuch explizite Block-/Fahrstraßenfolge festlegen. Anschließend zum Beispiel Dijkstra mit positiven Fahrzeitgewichten; bei Gleichstand feste Reihenfolge nach Fahrstraßen-ID. Modellversion, Gewichte, Zugrestriktionen, Startseite und Ergebnis speichern. Wenn Alternativen erlaubt sind, diese explizit definieren.

Ein eigener deterministisch gewählter Weg muss nicht Rocrails Wegwahl entsprechen. Nur dann gegen genau diesen Weg prüfen, wenn er tatsächlich als Soll vereinbart bzw. umgesetzt wurde. Sonst gegen die erlaubte Wegmenge prüfen oder eine Planabweichung melden, ohne sie als physisches Fehlfahren auszugeben.

Ausgaben unterscheiden:

- **Bisher vereinbar:** Beobachtungen passen zum Sollweg; nächster Abschnitt ggf. noch nicht bestätigt.
- **Wegabweichung belegt:** Eine zuverlässig zugeordnete Passage widerspricht allen erlaubten Wegen.
- **Zeitabweichung:** Erwartete Passage bleibt über das begründete Zeitfenster hinaus aus.
- **Nicht entscheidbar:** Zuordnung/Topologie ist mehrdeutig oder Daten fehlen.
- **Ankunft bestätigt:** Vereinbarte Zielbedingung ist beobachtet.

Ein Ausbleiben von Meldungen kann Zugstillstand, Sensorfehler oder Kommunikationsausfall bedeuten. Ohne zusätzliche Information diese Ursachen nicht behaupten. Eine falsche Abzweigung wird frühestens beim ersten unterscheidenden Sensor erkennbar; in einem uninstrumentierten Abschnitt kann der Monitor keine sofortige Gewissheit liefern.

## 4. Messung heute: erst Kurzprüfung, dann kleine Messserie

### Vor der ersten Fahrt – etwa 10–15 Minuten einplanen

- [ ] Aktuellen Plan und relevante Konfiguration als Snapshot sichern, Version/Hash und Messdatum notieren. Änderungen während der Sitzung markieren und neuen Snapshot ablegen.
- [ ] Klären: Sensoren punktuelle Impulse, Belegtabschnitte oder gehaltene Softwarezustände? Reagieren Lok, Achsen und Wagen unterschiedlich? Entprellung/Verzögerung bereits konfiguriert?
- [ ] Klären: Zeigen `sw`-Meldungen einen Befehl, eine Controllerbestätigung oder eine physisch gemessene Endlage? Vorhandene physische Rückmelder identifizieren.
- [ ] Eine reale Lok mit Rocrail-ID und Decoderadresse identifizieren; tatsächlichen Startabschnitt und Orientierung notieren. Alle anderen Fahrzeuge und aktiven Sensoren im Anfangszustand erfassen.
- [ ] Logger vor allen Fahrtaufträgen starten, Anfangszustand aufnehmen, danach ggf. Leerlauf vorsehen. Fehlende Anfangswerte als unbekannt behandeln.
- [ ] Auftragsjournal und Logger auf demselben Rechner bzw. mit dokumentierter Uhrzuordnung verwenden. UTC oder ISO-8601 mit explizitem Offset; Deutschland heute `+01:00`.
- [ ] Empfangszeit pro vollständiger Nachricht und monotone Zeit erfassen, nicht erst beim späteren Parsen der fertigen Logdatei. Empfangszeit ist kein exakter physischer Passagezeitpunkt; Transport-/Verarbeitungslatenz dokumentieren.
- [ ] Bei Chunking/Batches Eingangszeit und Zuordnung erhalten; beim Aufteilen keine künstlich unterschiedlichen Ereigniszeiten erfinden. Rohpayload, Sequenz und Quelle unverändert sichern.
- [ ] Bei Video einen sicht-/hörbaren Marker mit korrespondierendem Journalzeitpunkt aufnehmen; bei längerer Sitzung am Ende wiederholen, um Drift zu erkennen.
- [ ] 1–2 Minuten Probefahrt: bekannte Sensoren passieren, Auftrag und Halt markieren. Aufnahme direkt öffnen und prüfen: einzelne Zeiten, beide Flanken, richtige IDs, vollständige Nachrichten, gespeicherte Aufträge, keine unbemerkte Filterung oder Pufferverluste.

**Entscheidung:** Erst wenn diese Prüfung erfolgreich ist, die eigentliche Kalibrierungsserie aufnehmen. Falls keine Einzelzeitstempel verfügbar gemacht werden können, heute dennoch Sensor-/Topologiezuordnung und unabhängiges Video dokumentieren; die Logs ausdrücklich als ungeeignet für präzise Fahrzeitkalibrierung kennzeichnen. Ein Video kann separat Zeiten liefern, behebt aber nicht automatisch die gesamte Logzeitbasis.

### Minimalserie bei knapper Laborzeit

| Reihenfolge | Aufnahme | Zweck |
|---|---|---|
| 1 | Anfangszustand und kurze Ruhephase, etwa 30–60 s | Fremdmeldungen und Ausgangszustände erkennen |
| 2 | Ein Zug, kurze bekannte Strecke, feste Fahrstufe, 3–5 Wiederholungen | Sensorfolge, erste Abschnittszeiten und Streuung |
| 3 | Dieselbe Strecke andere Fahrtrichtung, soweit erlaubt, 3–5 Wiederholungen | Richtungszuordnung und andere Melderrollen |
| 4 | Zweite Fahrstufe auf derselben Strecke | Einfluss des Steuerwerts vergleichen |
| 5 | Bekannter Halt/Neustart und eine alternative Abzweigung, getrennt markiert | Zeitabweichung und Wegunterscheidung überprüfen |
| 6 | Optional zweite Lok, danach klar dokumentierter Zweizugbetrieb | Zugabhängigkeit und Mehrdeutigkeit untersuchen |

Wenn die Zeit knapp ist: Reihenfolge 1–2 sauber abschließen. Wenige nachvollziehbare Fahrten sind wertvoller als lange unkommentierte Automatikläufe. Normale Wiederholungen vor Sonderfällen aufnehmen; eine Person bedient, eine protokolliert/beobachtet, wenn möglich. Keine unmarkierten Umsetzungen oder Reset-Aktionen.

Fehlerfälle zunächst im Replay als ausdrücklich synthetische Datenvarianten erzeugen, z. B. eine Meldung auslassen oder verzögern. Synthetische Daten nicht als reale Fehlfahrt auswerten. Reale Versuche nur als regulär kontrollierte Abzweig-/Haltfahrten planen; keine gefährliche Weichenmanipulation unter dem Zug.

### Was zusammen gespeichert werden muss

**Sitzungsdaten:** Mess-ID, Plan-/Konfigurationsversion, Softwareversion, Start/Ende, Uhrquelle/Offset, Zeitauflösung, Loggerstand, Verbindungsausfälle, Sensortyp, Detektionsbereiche, lokspezifische Beschleunigungs-/Bremsparameter soweit bekannt, Fotos und ggf. Video.

**Je Fahrt:** Fahrt-ID, reale Zug-ID und Decoderadresse, Wagen/Zuglänge, Startort und Orientierung, Ziel, vereinbarte Fahrstraßen-/Blockfolge, Fahrstufe und Änderungen, Bedienmodus, relevante Weichenstellungen, Halte und manuelle Eingriffe. Für konstante Durchfahrtzeiten ausreichend Anlauf vor der Referenzpassage vorsehen und tatsächlich gleiches Verhalten prüfen.

**Je Rohereignis:** Sitzungs-ID, Sequenz, UTC-Empfangszeit, monotone Zeit, Quelle/Richtung (`rx`, `tx`, `operator`), Rohpayload; Quellzeit zusätzlich, falls vorhanden, mit Kennzeichnung ihrer Zeitbasis. `rdate`, `runtime`, `mtime` oder `operated` nicht als universelle Ereigniszeit verwenden. Abbrüche/Neustarts begrenzen die Gültigkeit monotoner Zeit und müssen als neue Sitzung bzw. Verbindungsepoche markiert sein.

**Je Auftrag mehrere Zeitpunkte trennen:** beabsichtigt/Bedienhandlung, tatsächlich gesendet, gegebenenfalls von Rocrail bestätigt, physische Abfahrt, beobachtete Ankunft. Ein Klickzeitpunkt beweist weder Annahme noch Bewegung.

Vorlage für das zusätzliche Journal, Semikolon-CSV; Zeitfelder erst mit realen Messwerten füllen:

```csv
session_id;run_id;timestamp_iso8601;event_type;train_id;start_block;target_block;planned_route_ref;speed_command;direction_ref;observation;reference_source
```

Mögliche `event_type`: `SESSION_START`, `INITIAL_STATE`, `TASK_REQUESTED`, `TASK_SENT`, `TASK_ACKNOWLEDGED`, `DEPARTURE_OBSERVED`, `PASSAGE_OBSERVED`, `SPEED_CHANGED`, `STOP_REQUESTED`, `STOP_OBSERVED`, `ARRIVAL_OBSERVED`, `MANUAL_INTERVENTION`, `CONNECTION_LOST`, `SESSION_END`. Eine manuelle Beobachtung einschließlich Reaktionsungenauigkeit kennzeichnen; technische Bestätigung nur protokollieren, wenn es tatsächlich eine gibt.

### Fotos für den späteren geometrischen Zwilling

Heute möglichst eine Gesamtansicht von oben mit Orientierung, Tischmaßen oder Maßreferenz aufnehmen. Ergänzend Abzweige, verdeckte Strecken, Blockgrenzen und Melderpositionen fotografieren. Im Bild bzw. einer zugehörigen Skizze die Rocrail-IDs zuordnen. Das ist später schwerer rekonstruierbar als eine schön gestaltete Oberfläche; Fotos sind heute sinnvoll, 3D-Modellierung kann warten.

## 5. Umsetzung in überprüfbaren Etappen

| Etappe | Konkretes Ergebnis | Abnahme |
|---|---|---|
| 0 – Messbarkeit | Zeitgestempelte Probeaufnahme plus Journal und Anfangszustand | Bekannter Auftrag und zwei echte Sensorpassagen zeitlich zuordenbar; Datenqualität dokumentiert |
| 1 – Modellimport | Blöcke/Seiten, Fahrstraßen, Sensorrollen, Weichenbedingungen | Eindeutige IDs, alle Referenzen geprüft; gewählte Teilstrecke an der Anlage bestätigt; unbekannte Altlogobjekte sichtbar |
| 2 – Ereignisreplay | Parser, normalisiertes Format, Wiedergabe mit Ereigniszeit | Rohreihenfolge und Pulse erhalten; wiederholbares Ergebnis; Zeitlücken bleiben sichtbar |
| 3 – Einzuglokalisierung | Zustandsmaschine/Kandidatenmenge auf Teilstrecke | Physisch beobachtete Passagen korrekt zugeordnet; kein Zukunftswissen; Mehrdeutigkeit ausdrücklich ausgewiesen |
| 4 – Zeitmodell | Erste Gewichte nach Strecke/Richtung/Lok/Fahrstufe | Definition jeder Zeitspanne, Streuung und Stichprobenzahl nachvollziehbar; Halt getrennt |
| 5 – Wegprüfung | Gespeicherter Sollweg und begründete Zustands-/Abweichungsmeldungen | Normale Fahrten, kontrollierte Alternativfahrt, Halt und Datenlücke unterscheidbar |
| 6 – Mehrzugbetrieb | Gemeinsame Zuordnungshypothesen | Keine willkürlichen Identitätswechsel; nicht beobachtbare Fälle bleiben offen |
| 7 – MQTT | Zweiter Eingangsadapter für denselben Kern | Tatsächliche Topic-/Payload-/Zeitsemantik geprüft; initiale Zustände, Duplikate, Retained-Nachrichten, Wiederverbindung und Reihenfolge berücksichtigt |
| 8 – Darstellung | 2D-Schema; danach optional realistische Geometrie | Messung, Steuerungsannahme und geschätzte Position unterscheidbar |

Wichtige Tests: Präfix eines Logs ergibt bis zu dessen Ende denselben Zustand wie der entsprechende Präfix eines längeren Logs. Bei beschleunigtem Replay laufen Modell-Timer in Ereigniszeit. Kalibrierungsfahrten und unabhängige Prüffahrten trennen, bevor Grenzwerte beurteilt werden. Gütemaße: Zuordnungsfehler an beobachteten Passagen, Anteil mehrdeutiger/unbekannter Zustände, Fehlalarme pro Fahrt, erkannte Abweichungen und Erkennungsverzögerung ab erster unterscheidender Passage. Unabhängige Referenz ist Video/Beobachtung, nicht nur Rocrails Anzeige.

## 6. Vorgeschlagene spätere Ablage

Dies ist ein Vorschlag, noch kein angelegtes Programmgerüst:

| Pfad | Inhalt |
|---|---|
| `docs/` | Projektentscheidungen, Datenwörterbuch, Messprotokoll, Sensorkarte |
| `data/raw/<session_id>/` | Unveränderte Rohdaten, Auftragjournal, Anfangszustand, Plan-/Konfigurationssnapshot und Referenzen |
| `data/processed/` | Reproduzierbar abgeleitete Ereignisse und Fahrten |
| `models/` | Versionierte Topologie, Sensorzuordnung, Fahrzeitparameter |
| `src/twin/` | Adapter, Normalisierung, Topologie, Schätzung, Zeitmodell, Routing, Validierung und Replay |
| `tests/` | Kleine aussagekräftige Ereignisfolgen und Referenzfälle |
| `notebooks/` | Explorative Analyse und Abbildungen |

## 7. Offene Punkte für das Labor

1. Wie wird heute aufgezeichnet, und lassen sich pro Nachricht Empfangszeiten ergänzen?
2. Welche Hardware/Detektionsbereiche stecken hinter den Rückmeldern; welche Fahrzeuge lösen aus?
3. Sind gemeldete Weichenzustände physisch rückgemeldet?
4. Sind aktueller Plan, reale Anlage und heutige Rocrail-Konfiguration deckungsgleich?
5. Lässt sich zunächst eine Lok mit bekanntem Startzustand isoliert fahren?
6. Wie wird der Sollweg verbindlich vorgegeben; welche Alternativen sind erlaubt?
7. Welche Auftrags-/Zustandsereignisse wird MQTT später tatsächlich bereitstellen?

Diese Punkte müssen nicht vor jedem weiteren Planungsschritt beantwortet sein. Die Zeitbasis und Sensorsemantik sind jedoch vor einer belastbaren Fahrzeitmessserie zu prüfen.

## 8. Quellenhinweise

Die konkreten Zahlen und Beispiele stammen aus der lokalen Dateiprüfung und den beiden angeforderten Ordneranalysen. Die Dateien wurden dabei nicht verändert. Das offizielle Rocrail-Wiki beschreibt den Clock Service als standardmäßig minütliche Meldung und unterstützt eine beschleunigte bzw. pausierbare Modelluhr: https://wiki.rocrail.net/doku.php?id=clockservice-en . Deshalb eigene reale Erfassungszeiten zusätzlich zur Rocrail-Uhr sichern. Die spätere MQTT-Schnittstelle und die reale Sensor-/Weichenhardware wurden noch nicht praktisch geprüft.
