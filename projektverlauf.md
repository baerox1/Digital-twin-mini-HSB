# Projektverlauf: Digital Twin (Rocrail)

Stand: 10. November 2026. Technische Zielsetzung des Gesamtsystems: [project_context_agents.md](project_context_agents.md).

## Ziel

Eine Diagnose-Schicht für die Modellbahn, ohne Kamera. Züge werden über Sensorzeiten geprüft. Dafür gibt es drei Arbeitspakete:

1. **AP 1, Kalibrierung.** Pro Zug und pro Kante die Dauer zwischen Enter- und In-Sensor messen: Δt = t_in − t_enter, dazu die Streuung σ.
2. **AP 2, Kommunikation.** Weichen- und Fahrbefehle auf dem Rocrail-Port 8051 entzerren, damit Befehle nicht verloren gehen.
3. **AP 3, Watchdog.** Mit den Werten aus AP 1 prüfen, ob ein Zug im erwarteten Zeitfenster ankommt, und Stall, Ghost-Train und verschluckte Sensoren unterscheiden.

Als Nächstes zählt nur AP 1. AP 2 und AP 3 starten, wenn für die gefahrenen Kanten echte Wiederholungen vorliegen.

## Bisher erledigt

Das Labor-Notebook `rocrail_zeitreihe_laboraufgaben.ipynb` und der Mitschnitt `1771731551.log` legen die Nachrichtenstruktur fest. Rocrail schickt keinen XML-Baum, sondern einzelne Frames: `<xmlh><xml size="N"/></xmlh>` plus Nutzlast. `lc` ist die Lok, `fb` der Sensor, `bk` der Block, `st` die Fahrstraße, `clock` die Uhr.

Daraus ist [ap1_sensor_delta.py](ap1_sensor_delta.py) entstanden. Es filtert steigende Sensorflanken (`fb` mit `state="true"` und einer `id`). Enter ist die letzte Flanke vor `bk.entering` von false nach true, In die letzte andere Flanke vor dem Wechsel zurück auf false. Lok, Herkunftsblock und Sollgeschwindigkeit `V` kommen aus der letzten fachlichen `lc`-Meldung. `V` ist Prozent.

Aufruf:

```text
python ap1_sensor_delta.py ..\1771731551.log
```

Ohne Argument liest das Skript `../1771731551.log`. Ergebnisdateien in diesem Ordner:

- [edge_passages.json](edge_passages.json): jede einzelne Durchfahrt
- [edge_timings.json](edge_timings.json): Mittelwert und σ, erst ab zwei Fahrten derselben Lok, derselben Kante und desselben `V`

Prüfung am vorhandenen Log: Captrain Vectron, Kante `hbf_1->west_cw_1`, Enter `fb37`, In `fb35`, `V=80`, Δt = 1,75 s. Insgesamt 2085 Nachrichten und 24 Durchfahrten. Nur zwei Kanten von Flixtrain kommen doppelt vor, deshalb ist das Profil noch keine Kalibrierung.

Zwei Eigenschaften des Mitschnitts bleiben gültig:

- Nachrichten haben keine eigene Uhrzeit. Anker sind der Unix-Zeitstempel im Dateinamen und die `clock`-Meldung etwa einmal pro Minute. Abstände innerhalb einer Minute sind interpoliert.
- `size` zählt ein CRLF mit. Diese Log-Datei speichert nur LF. Das Skript liest zuerst `size` Bytes und bei ungültigem XML ein Byte weniger.

## Was das vorhandene Log nicht leistet

`1771731551.log` ist ein alter Mitschnitt, kein Versuchsfahrplan. Captrain fährt dort meist mit 80, Flixtrain mit 70, und fast jede Kante nur einmal. Für das nächste Mal brauchen wir neue Logs von Fahrten, die wir selbst festlegen und wiederholen.

## Festgelegte Schritte im Labor

Diese Reihenfolge gilt bei jedem Labortermin für AP 1.

1. Vor dem Fahren aufschreiben: Lok, Startblock, Zielblock, Geschwindigkeiten in Prozent, Anzahl Wiederholungen. Dieselbe Kombination mindestens zweimal fahren, sonst entsteht kein σ. Sinnvoll sind mehrere Geschwindigkeiten, zum Beispiel 40, 60 und 80, jeweils wiederholt.
2. In Rocrail die Lok in den Startblock stellen, den Zielblock vorgeben und `V` setzen. Die Strecke ist dieser Auftrag, nicht eine Sensornummer. Rocrail schreibt sie ins Log, zum Beispiel: `loco [Captrain Vectron] is in block [hbf_1] and should travel to [ksmo_2]`.
3. Automatik starten und den Server-Mitschnitt der ganzen Sitzung sichern. Eine Datei für alle Fahrten des Termins reicht. Der Dateiname muss eine reine Unix-Zeit sein, zum Beispiel `1731240000.log`, weil nur dann der Dateiname ein Zeitanker ist. Namen wie `Gruppe2.log` haben nur die Minuten aus `clock`.
4. Sensor-IDs nicht heraussuchen. Welche zwei Rückmelder Enter und In eines Blocks sind, ordnet das Skript über `bk.entering` zu. Im alten Log ist `west_cw_1` zum Beispiel `fb37` dann `fb35`.
5. Danach in diesem Ordner ausführen:

```text
python ap1_sensor_delta.py ..\NEUE_DATEI.log
```

6. In `edge_passages.json` prüfen, ob `loco`, `from_block`, `block` und `v_cmd` zum Auftrag aus Schritt 2 passen. Die Kette der `edge`-Zeilen einer Lok ist die gefahrene Strecke, Stück für Stück von Block zu Block. Δt gehört jeweils nur zum Einfahren in den Zielblock der Kante, nicht zur gesamten Fahrt bis zum Endziel.
7. `edge_timings.json` erst danach lesen. Ein Profil erscheint nur, wenn dieselbe Lok dieselbe Kante mit demselben `V` mindestens zweimal gefahren ist.

## Ziel der nächsten Termine

Solange AP 1 offen ist, ist das Ziel ein Kalibrierprotokoll: genug Wiederholungen, damit `edge_timings.json` pro Zug, Kante und Geschwindigkeit einen Mittelwert und ein σ enthält. Erst diese Datei ist die Grundlage für das Zeitfenster in AP 3.
