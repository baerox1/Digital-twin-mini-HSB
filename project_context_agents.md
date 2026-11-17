# System-Kontext: Logistik-Demonstrator (Rocrail Watchdog & Digital Twin)

## 1. Projekt-Überblick & Zielsetzung
Das Ziel dieses Projekts ist die Entwicklung einer Fehlertoleranz- und Diagnose-Schicht für eine Modellbahnanlage (Logistik-Demonstrator), die von Rocrail gesteuert wird. Das System löst Probleme wie plötzliches Stehenbleiben von Zügen (Stalls), verschluckte Weichenbefehle und fälschlich ausgelöste "Ghost-Train"-Alarme, **ohne** Kamerasysteme einzusetzen.

Die Lösung basiert auf einer rein mathematischen Zeitreihen-Analyse (Dead-Reckoning) und einer Härtung des Rocrail Client Protocols (RCP) über den TCP-Port 8051.

## 2. Architektur & Arbeitspakete (AP)

Das Projekt ist in drei aufeinander aufbauende Schichten unterteilt:

### AP 1: Automatisierte Agenten-Kalibrierung (Offline-Testing / System Identification)
*   **Ziel:** Ermittlung realer Durchlaufzeiten und physikalischer Parameter pro Zug (Agent).
*   **Vorgehen:** Ein Python-Skript fährt Züge über definierte Strecken (z.B. `hbf_1` $	o$ `sbf_2`) mit verschiedenen Soll-Geschwindigkeiten ($V_{	ext{cmd}}$).
*   **Datenquelle:** Der XML-Stream von Rocrail (Port 8051). Gefiltert wird nach `<fb>` (Feedback/Sensor)-Events.
*   **Ergebnis:** Ein empirisches Profil (Kalibrierungsprotokoll / `edge_timings.json`) pro Zug, das die erwartete Dauer $\Delta t = t_{	ext{in}} - t_{	ext{enter}}$ und die Standardabweichung $\sigma$ für jede Kante enthält.

### AP 2: Kommunikations-Härtung (Transport-Layer / TCP-Wrapper)
*   **Ziel:** Vermeidung von Paketverlusten an der Hardware (Digitalzentrale) und Behebung von Mikrounterbrechungen am Gleis.
*   **Vorgehen:** Aufbau einer asynchronen Priority Queue vor dem Rocrail-Socket.
*   **Komponenten:**
    1.  **Token-Bucket (Rate Limiting):** Weichenbefehle (`<sw>`) werden strikt entzerrt (z.B. alle $150	ext{ ms}$ einzeln gesendet), um Spannungsabfälle und Buffer-Overflows in der Zentrale zu verhindern.
    2.  **Anti-Stall Refresh (Keep-Alive):** Solange sich ein Zug im Transit zwischen zwei Sensoren befindet, wird sein letzter Fahrbefehl (`<lc>`) zyklisch (z.B. alle $800	ext{ ms}$) neu gesendet. So fahren Züge nach kurzen Stromabrissen auf verschmutzten Schienen automatisch weiter.
*   **Priorisierung:** Nothalt (`V="0"`) > Weichen (`<sw>`) > Fahrbefehle (`<lc>`).

### AP 3: Plausibilitäts-Watchdog & Digital Twin (Online-Verification)
*   **Ziel:** Erkennung und automatische Behebung von Laufzeitfehlern (Sensor-Ausfälle, klemmende Weichen).
*   **Vorgehen:** Ein leichtgewichtiger topologischer Graph (Digital Twin) läuft parallel zu Rocrail.
*   **Logik (Dead-Reckoning):** 
    *   Wenn ein Zug in Block A startet, berechnet der Twin aus den Daten von AP 1 das erwartete Ankunfts-Zeitfenster am Ziel-Sensor in Block B: $T_{	ext{valid}} = [t_{	ext{exp}} - 3\sigma, t_{	ext{exp}} + 3\sigma + \epsilon]$.
*   **Fehler-Klassifikation & Recovery:**
    1.  **Timeout / Stall:** Timer läuft ab, kein Sensor feuert $	o$ Recovery: Retry-Fahrbefehl, danach Sperrung des Blocks.
    2.  **Ghost-Train (Klemmende Weiche):** Ein Nachbar-Sensor (z.B. Block C) feuert exakt im Zeitfenster $T_{	ext{valid}}$ des erwarteten Zugs $	o$ Diagnose: Zug ist wegen falscher Weichenstellung abgebogen. Recovery: Block in Rocrail korrigieren, Notstopp verhindern.
    3.  **Sensor Drop:** Nachfolge-Sensor feuert im Zeitfenster, aber der erste Sensor wurde verschluckt $	o$ Recovery: Synthetisches Nachfeuern des fehlenden Sensors.

## 3. Technische Umsetzung & Gotchas (Für Coding-Agenten)

### 3.1 Netzwerk & `asyncio`
*   Das Backend MUSS asynchron sein (`asyncio.start_connection`). `time.sleep()` blockiert den Sensor-Reader und darf nicht verwendet werden.

### 3.2 Das Rocrail Message-Framing (Kritisch!)
Rocrail sendet XML nicht zeilenweise, sondern als kontinuierlichen TCP-Stream mit Header.
*   **Format:** `<xmlh><xml size="LENGTH"/></xmlh><DATA...>`
*   **Parser-Logik:** Der Reader muss zuerst den `<xmlh>`-Block parsen, die `size` auslesen und dann **exakt** diese Anzahl an Bytes vom TCP-Stream lesen, bevor der String an den XML-Parser (`xml.etree.ElementTree`) übergeben wird. Ein stumpfes `reader.read(1024)` führt unweigerlich zu abgeschnittenen XML-Tags und Abstürzen.

### 3.3 Log-Dateien als Offline-Simulation
*   Die `rocrail.trc` oder `.log`-Dateien enthalten das exakte XML-Format, das auch live über Port 8051 kommt.
*   Für die lokale Entwicklung von AP 1 und AP 3 können diese Log-Dateien vom Python-Skript zeilenweise eingelesen werden, um Sensordaten zu simulieren, ohne an der physischen Anlage angeschlossen zu sein.
