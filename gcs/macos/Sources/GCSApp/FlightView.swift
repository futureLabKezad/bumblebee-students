// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import AppKit
import SwiftUI
import WebKit

/// Serves the «Полёт» page of the app bundle to its own WKWebView at bbflight://app/...:
/// flight_embedded.html and the five Pyodide files, nothing else. No socket is opened;
/// the page's Content-Security-Policy ('self' only) keeps it away from the drone.
@MainActor
final class FlightPageFiles: NSObject, WKURLSchemeHandler {
    static let scheme = "bbflight"
    static let origin = "bbflight://app"
    static let pageURL = URL(string: "bbflight://app/flight_embedded.html")!

    private static let types: [String: String] = [
        "/flight_embedded.html": "text/html; charset=utf-8",
        "/pyodide/pyodide.js": "text/javascript",
        "/pyodide/pyodide.asm.js": "text/javascript",
        "/pyodide/pyodide.asm.wasm": "application/wasm",
        "/pyodide/python_stdlib.zip": "application/zip",
        "/pyodide/pyodide-lock.json": "application/json",
    ]

    /// Sources/GCSApp/FlightWeb of the build (build_app.sh fills it from gcs/web/dist).
    static var folder: URL? { Bundle.module.url(forResource: "FlightWeb", withExtension: nil) }

    static var pageExists: Bool {
        guard let folder = folder else { return false }
        return FileManager.default.fileExists(atPath: folder.appendingPathComponent("flight_embedded.html").path)
    }

    func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask) {
        guard let url = urlSchemeTask.request.url, url.host == "app",
              let type = Self.types[url.path], let folder = Self.folder,
              let data = try? Data(contentsOf: folder.appendingPathComponent(String(url.path.dropFirst()))),
              let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: [
                  "Content-Type": type, "Content-Length": String(data.count), "Cache-Control": "no-store",
              ]) else {
            urlSchemeTask.didFailWithError(URLError(.fileDoesNotExist))
            return
        }
        urlSchemeTask.didReceive(response)
        urlSchemeTask.didReceive(data)
        urlSchemeTask.didFinish()
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) {}     // every task ends inside start
}

/// The «Полёт» section of one connection: the web page (gcs/web, flight_embedded.html) in a
/// WKWebView, the bridge to the drone (FlightBridge.swift) and the app's own questions.
/// MainShell keeps one model while the app is connected, so the editor's text and the
/// loaded Python stay when another section is shown. A takeoff is confirmed in the app's
/// own alert here, which page code cannot press; STOP FLIGHT in the toolbar does not
/// depend on the page.
@MainActor
final class FlightModel: NSObject, ObservableObject {
    private static let dialogSeconds: UInt64 = 60        // an unanswered «Взлёт?» closes as «no»
    private static let yesAfterSeconds = 1.5             // a window that pops up under the cursor is not a «yes»
    private static let handlerName = "bbflight"

    /// The Flight section was opened in this connection (STOP FLIGHT stays in the toolbar from then on).
    @Published private(set) var opened = false
    /// Shown instead of the page: missing files, a page that stopped working.
    @Published private(set) var note: String?
    @Published private(set) var stopNote = ""
    /// A flight program this app started (or saw running) is on the drone.
    @Published private(set) var missionActive = false

    private(set) var webView: WKWebView?
    /// The section is on screen now (set by FlightView): no «Взлёт?» from a hidden page.
    var shown = false

    private weak var app: AppState?
    private var bridge: FlightBridge?
    private let api = MissionAPI()
    private let files = FlightPageFiles()
    private var alert: NSAlert?
    private var alertExpired = false                     // the open «Взлёт?» was closed by its own timer
    private var closed = false

    /// The first opening of the section: loads the page.
    func open(app: AppState) {
        guard !opened, !closed else { return }
        opened = true
        self.app = app
        guard FlightPageFiles.pageExists else {
            note = "The Flight module files are missing from this build (FlightWeb/flight_embedded.html)."
            return
        }
        let bridge = FlightBridge(
            api: api,
            confirmTakeoff: { [weak self] request in
                await self?.confirmTakeoff(request) ?? .notAsked("the Flight section is closed: no takeoff")
            },
            drone: { [weak app] in (host: app?.droneHost ?? "", name: app?.droneName ?? "") })
        bridge.onMissionActiveChanged = { [weak self, weak bridge] in
            let active = bridge?.missionActive ?? false
            self?.missionActive = active
            self?.stopNote = active ? "flight program running" : ""
        }
        bridge.onTakeoffInFlightChanged = { [weak self, weak bridge] in
            if bridge?.takeoffInFlight == true { self?.stopNote = "takeoff sent, waiting for the drone…" }
        }
        self.bridge = bridge

        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(files, forURLScheme: FlightPageFiles.scheme)
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: Self.handlerName)
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        let web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = false
        web.allowsLinkPreview = false
        if #available(macOS 13.3, *) { web.isInspectable = false }
        web.load(URLRequest(url: FlightPageFiles.pageURL))
        webView = web
    }

    /// The shell is gone (Disconnect, another drone): an open «Взлёт?» closes as «no», the page stops.
    func close() {
        closed = true
        if let alert = alert, let window = alert.window.sheetParent {
            window.endSheet(alert.window, returnCode: .abort)
        }
        if let web = webView {
            web.stopLoading()
            web.configuration.userContentController.removeScriptMessageHandler(forName: Self.handlerName, contentWorld: .page)
            web.removeFromSuperview()
        }
        webView = nil
    }

    /// The shell is on screen again with this same model after close() (should SwiftUI take the
    /// shell away and bring it back): the section can be opened anew; the map and the program
    /// come back from the page's own storage.
    func revive(app: AppState, reopen: Bool) {
        guard closed else { return }
        closed = false
        opened = false
        note = nil
        stopNote = ""
        missionActive = false
        bridge = nil
        if reopen { open(app: app) }
    }

    /// The app's own Stop for a flight program: one click, no questions; tried again if the drone
    /// is silent. It works before the section was ever opened (a program may be flying that
    /// this window did not start).
    func stopFlight(app: AppState) async {
        bridge?.noteStop()                       // a takeoff request that is still on its way must not win
        stopNote = "sending STOP…"
        let reply = await api.stop(host: app.droneHost)
        let time = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        stopNote = reply.code == 200 ? "STOP sent " + time : "STOP did not reach the drone: use the RC (CH8)"
    }

    /// Why «Взлёт?» cannot be asked now (the page gets these words), or nil.
    private func whyNotAsk(_ r: TakeoffRequest) -> String? {
        guard let app = app, !closed, app.connected, app.droneHost == r.host else {
            return "the app is no longer connected to this drone: no takeoff"
        }
        if !shown || webView?.window == nil {
            return "the Flight section is not shown now: open it and check the program again"
        }
        if app.identityMismatch != nil {
            return "the app is asking whether this is the right drone: answer in its window and check the program again"
        }
        if alert != nil { return "the “Take off?” window is already open" }
        return nil
    }

    /// The explicit human «yes» for a takeoff. Return presses «Отмена»; «Взлететь» wakes up after
    /// a moment; no answer in a minute is «no». «Yes» counts only while this section is still
    /// shown and the app is still connected to the drone the question names.
    private func confirmTakeoff(_ r: TakeoffRequest) async -> TakeoffAnswer {
        if let early = whyNotAsk(r) { return .notAsked(early) }
        guard let app = app, let window = webView?.window else { return .notAsked("the Flight section is closed: no takeoff") }
        alertExpired = false
        let box = NSAlert()
        box.alertStyle = .warning
        box.messageText = "Take off?"
        box.informativeText = TakeoffText.body(r, droneName: app.droneName, link: app.telemetry.link.text)
        box.addButton(withTitle: "Cancel")                // the first button: Return
        let yes = box.addButton(withTitle: "Take off")
        yes.keyEquivalent = ""
        yes.isEnabled = false
        let wake = Task { @MainActor in
            try? await Task.sleep(nanoseconds: UInt64(Self.yesAfterSeconds * 1_000_000_000))
            if !Task.isCancelled { yes.isEnabled = true }
        }
        let expire = Task { @MainActor [weak window] in
            try? await Task.sleep(nanoseconds: Self.dialogSeconds * 1_000_000_000)
            if !Task.isCancelled {
                self.alertExpired = true
                window?.endSheet(box.window, returnCode: .abort)
            }
        }
        alert = box
        let answer = await box.beginSheetModal(for: window)
        alert = nil
        wake.cancel()
        expire.cancel()
        if answer != .alertSecondButtonReturn {
            return .declined(alertExpired ? "the “Take off?” window closed by itself: no answer for \(Self.dialogSeconds) s"
                                     : "takeoff cancelled in the app’s window")
        }
        if let late = whyNotAsk(r) { return .declined(late) }
        return .go
    }
}

extension FlightModel: WKScriptMessageHandlerWithReply {
    /// One message of the page (a JSON text) -> the reply (a JSON text), or nil: not for the
    /// bridge, over the budget, or not from our page.
    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) async -> (Any?, String?) {
        guard !closed, message.frameInfo.isMainFrame, message.frameInfo.request.url == FlightPageFiles.pageURL,
              let text = message.body as? String, let bridge = bridge else { return (nil, nil) }
        let reply = await bridge.handle(text)
        return (closed ? nil : reply, nil)
    }
}

extension FlightModel: WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    /// The page stays where it is: exactly one address may load. Its own blob: addresses are
    /// how it saves a map or a program to a file («Скачать map.txt»): those become downloads.
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction) async -> WKNavigationActionPolicy {
        let url = navigationAction.request.url
        if navigationAction.shouldPerformDownload, url?.absoluteString.hasPrefix("blob:" + FlightPageFiles.origin + "/") == true {
            return .download
        }
        return url == FlightPageFiles.pageURL ? .allow : .cancel
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    /// Where to save the file: the person chooses.
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String) async -> URL? {
        guard !closed, let window = webView?.window else { return nil }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        guard await panel.beginSheetModal(for: window) == .OK, let url = panel.url else { return nil }
        try? FileManager.default.removeItem(at: url)     // the person agreed to replace it; WebKit refuses an existing file
        return url
    }

    /// «Открыть файл…» of the map editor: the person chooses the file.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo) async -> [URL]? {
        guard !closed, let window = webView.window else { return nil }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        return await panel.beginSheetModal(for: window) == .OK ? panel.urls : nil
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        guard !closed else { return }
        note = "The Flight page stopped working. If a flight program is running, use STOP FLIGHT at the top "
            + "or the RC (CH8). Then press Disconnect and connect again."
    }

    /// No new windows.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        nil
    }
}

/// The section's view: the page, or a line of text when it cannot be shown.
struct FlightView: View {
    @ObservedObject var model: FlightModel

    var body: some View {
        Group {
            if let note = model.note {
                Text(note)
                    .font(Theme.body).foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center)
                    .padding(Theme.s4)
            } else if let web = model.webView {
                FlightWebHost(webView: web)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear { model.shown = true }
        .onDisappear { model.shown = false }
    }
}

/// Puts the model's one WKWebView into the section each time it is shown again.
private struct FlightWebHost: NSViewRepresentable {
    let webView: WKWebView

    func makeNSView(context: Context) -> NSView {
        let box = NSView()
        webView.removeFromSuperview()
        webView.frame = box.bounds
        webView.autoresizingMask = [.width, .height]
        box.addSubview(webView)
        return box
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}
