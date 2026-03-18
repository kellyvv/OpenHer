import SwiftUI
import WebKit

/// Embeds persona_engine_viz.html in a WKWebView.
/// When EngineDebugState receives new data from the backend, real values are
/// injected via evaluateJavaScript so the HTML visualization reflects live state.
struct EngineWebPanel: NSViewRepresentable {
    @ObservedObject var debugState: EngineDebugState
    @EnvironmentObject var appState: AppState

    private var persona: Persona? { appState.selectedPersona }

    private static let htmlURL = URL(fileURLWithPath:
        "/Users/zxw/AITOOL/openher-docker/desktop/prototype/persona_engine_viz.html")

    // MARK: - NSViewRepresentable

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        webView.navigationDelegate = context.coordinator   // ← wait for page load
        webView.loadFileURL(Self.htmlURL,
                            allowingReadAccessTo: Self.htmlURL.deletingLastPathComponent())
        context.coordinator.webView = webView
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        let coord = context.coordinator

        // ── Persona header: queue update; fires immediately if page ready ──
        let personaKey = persona?.personaId ?? ""
        if coord.lastPersonaId != personaKey {
            coord.lastPersonaId = personaKey
            coord.pendingHeaderJS = makeHeaderJS()
            if coord.pageLoaded {
                coord.flushPendingHeader()
            }
        }

        // ── Turn data: only inject when a new update arrives ──
        guard debugState.updateSeq > 0 else { return }
        guard coord.lastSeq != debugState.updateSeq else { return }
        coord.lastSeq = debugState.updateSeq
        let dataJS = makeDataJS()
        let headerJS = makeHeaderJS()
        if coord.pageLoaded {
            webView.evaluateJavaScript(dataJS) { _, error in
                if let error { print("[EngineWebPanel] data JS error: \(error)") }
            }
            webView.evaluateJavaScript(headerJS) { _, error in
                if let error { print("[EngineWebPanel] header JS error: \(error)") }
            }
        } else {
            // Page still loading — store for after didFinish
            coord.pendingDataJS   = dataJS
            coord.pendingHeaderJS = headerJS
        }
    }

    // MARK: - JS builders

    private func makeHeaderJS() -> String {
        let personaName = persona?.displayName ?? persona?.name ?? "Persona"
        let mbti        = persona?.mbti ?? "—"
        let agentAge    = debugState.age
        return """
        (function() {
            const pn = document.querySelector('.persona-name');
            if (pn) pn.textContent = '\(personaName) · \(mbti)';
            const meta = document.querySelector('.meta');
            if (meta) meta.textContent = 'age: \(agentAge) · hidden: 24 neurons';
        })();
        """
    }

    private func makeDataJS() -> String {
        let hiddenJS = debugState.hiddenActivations.map { String(format: "%.4f", $0) }.joined(separator: ",")
        let inputJS  = debugState.inputVector.map      { String(format: "%.4f", $0) }.joined(separator: ",")

        let signalOrder = ["directness","vulnerability","playfulness","initiative",
                           "depth","warmth","defiance","curiosity"]
        let signalsJS = signalOrder.map { k in
            let v = debugState.signals[k] ?? 0.5
            return "\"\(k)\": \(String(format: "%.4f", v))"
        }.joined(separator: ",")

        let driveOrder = ["connection","novelty","expression","safety","play"]
        let driveStateJS    = driveOrder.map { k in
            "\"\(k)\": \(String(format: "%.4f", debugState.driveState[k] ?? 0.5))"
        }.joined(separator: ",")
        let driveBaselineJS = driveOrder.map { k in
            "\"\(k)\": \(String(format: "%.4f", debugState.driveBaseline[k] ?? 0.5))"
        }.joined(separator: ",")

        let monologue = debugState.monologue
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'",  with: "\\'")
            .replacingOccurrences(of: "\n", with: "\\n")

        let frustration = String(format: "%.4f", debugState.frustration)
        let temperature = String(format: "%.4f", debugState.temperature)
        let turnCount   = debugState.turnCount
        let phased      = debugState.phaseTransition ? "true" : "false"

        let recallJS = debugState.styleRecall.prefix(3).map { item in
            "{ text: '\(item.text.replacingOccurrences(of:"'",with:"\\'"))', d: \(String(format:"%.2f",item.distance)) }"
        }.joined(separator: ",")

        return """
        (function() {
            if (typeof agent === 'undefined') return;

            agent.lastHidden  = [\(hiddenJS)];
            agent.lastInput   = [\(inputJS)];
            agent.lastSignals = {\(signalsJS)};
            agent.driveState  = {\(driveStateJS)};
            agent.frustration = \(frustration);
            agent.age         = \(debugState.age);

            const driveBaselineData = {\(driveBaselineJS)};
            if (agent.driveBaseline) Object.assign(agent.driveBaseline, driveBaselineData);

            const HIDDEN_SIZE = 24;
            const sorted = Array.from({length: HIDDEN_SIZE}, (_, i) => i)
                .sort((a, b) => Math.abs(agent.lastHidden[b]) - Math.abs(agent.lastHidden[a]));
            sorted.forEach((neuronIdx, rank) => { hiddenRank[neuronIdx] = rank; });

            turnCount = \(turnCount);
            const tc = document.getElementById('turnCount');
            if (tc) tc.textContent = \(turnCount);

            const frustPct = Math.min(1, \(frustration) / 2.0);
            const fb = document.getElementById('frustrationBar');
            if (fb) fb.style.width = (frustPct * 100) + '%';
            const fv = document.getElementById('frustrationVal');
            if (fv) fv.textContent = '\(frustration)';
            const temp = \(temperature);
            const tb = document.getElementById('tempBar');
            if (tb) tb.style.width = (Math.min(1, temp / 0.35) * 100) + '%';
            const tv = document.getElementById('tempVal');
            if (tv) tv.textContent = '\(temperature)';

            if (!computeActive) {
                idleParticles = [];
                animPulse = 0;
                computeActive = true;
                const st = document.getElementById('statusText');
                if (st) st.textContent = \(phased) ? '⚡ PHASE TRANSITION' : 'COMPUTING';
                if (\(phased)) phaseFlashT = 1.2;
                updateSidebar(agent.lastSignals, \(phased));
                const nodes = getNodePositions();
                spawnForwardParticles(nodes);
            }

            // ── Override monologue & recall AFTER updateSidebar (it uses static demo arrays) ──
            const monoEl = document.getElementById('monologue');
            if (monoEl) monoEl.textContent = '\(monologue)';

            const recallData = [\(recallJS)];
            const recallContainer = document.getElementById('recallList');
            if (recallContainer && recallData.length > 0) {
                recallContainer.innerHTML = recallData.map(r =>
                    '<div class="recall-item"><span class="recall-text">"' + r.text + '"</span><span class="recall-dist">d=' + r.d.toFixed(2) + '</span></div>'
                ).join('');
            }
        })();
        """
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, WKNavigationDelegate {
        var webView: WKWebView?
        var lastSeq: Int = -1
        var lastPersonaId: String = ""

        /// Set to true once didFinish fires — safe to run evaluateJavaScript after this.
        var pageLoaded: Bool = false

        /// JS queued before page finished loading.
        var pendingHeaderJS: String? = nil
        var pendingDataJS:   String? = nil

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            pageLoaded = true
            print("[EngineWebPanel] page loaded — flushing pending JS")
            flushPendingHeader()
            if let js = pendingDataJS {
                webView.evaluateJavaScript(js) { _, error in
                    if let error { print("[EngineWebPanel] pending data JS error: \(error)") }
                }
                pendingDataJS = nil
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            print("[EngineWebPanel] navigation failed: \(error)")
        }

        func flushPendingHeader() {
            guard let wv = webView, let js = pendingHeaderJS else { return }
            wv.evaluateJavaScript(js) { _, error in
                if let error { print("[EngineWebPanel] pending header JS error: \(error)") }
            }
            pendingHeaderJS = nil
        }
    }
}
