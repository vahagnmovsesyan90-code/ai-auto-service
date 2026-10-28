import UIKit
import WebKit

/// AI Auto Service-ի WKWebView պատյանը. կայքը՝ հավելվածի մեջ, այլ հղումները՝ Safari-ում։
/// Ապահովում է՝ WebRTC (տեսախցիկ/խոսափող), JS alert/confirm/prompt, ներբեռնումներ (PNG արտահանում → share sheet),
/// swipe-back, offline էջ, target=_blank հղումներ։
final class WebViewController: UIViewController {
    private let cfg = AppConfig.shared
    private var web: WKWebView!
    private let progress = UIProgressView(progressViewStyle: .bar)
    private var lastURL: URL?
    private var progressObs: NSKeyValueObservation?
    /// APNs-ի token-ը (AppDelegate). էջին է տրվում ամեն բեռնումից հետո, էջն ինքն է ուղարկում սերվերին (front/src/push.js)
    private var pushToken: String?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(named: "PageBackground") ?? .systemBackground

        let c = WKWebViewConfiguration()
        c.allowsInlineMediaPlayback = true
        c.mediaTypesRequiringUserActionForPlayback = []
        c.websiteDataStore = .default()
        c.applicationNameForUserAgent = cfg.userAgentSuffix
        c.defaultWebpagePreferences.allowsContentJavaScript = true
        c.preferences.javaScriptCanOpenWindowsAutomatically = false

        web = WKWebView(frame: .zero, configuration: c)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.isOpaque = false
        web.backgroundColor = view.backgroundColor
        web.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(web)

        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.tintColor = UIColor(named: "AccentColor")
        progress.trackTintColor = .clear
        progress.isHidden = true
        view.addSubview(progress)

        NSLayoutConstraint.activate([
            web.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            web.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            progress.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            progress.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            progress.trailingAnchor.constraint(equalTo: view.trailingAnchor),
        ])

        progressObs = web.observe(\.estimatedProgress, options: [.new]) { [weak self] w, _ in
            guard let self else { return }
            self.progress.progress = Float(w.estimatedProgress)
            self.progress.isHidden = w.estimatedProgress >= 1
        }

        load(cfg.startURL)
    }

    override var preferredStatusBarStyle: UIStatusBarStyle { traitCollection.userInterfaceStyle == .dark ? .lightContent : .darkContent }

    func load(_ url: URL) {
        lastURL = url
        web?.load(URLRequest(url: url))
    }

    /// Ծանուցման url-ը (կայքի ներսի ուղի, օր.՝ /calls) → բացել
    func open(path: String) {
        guard path.hasPrefix("/"), !path.hasPrefix("//"), let url = URL(string: path, relativeTo: cfg.startURL)?.absoluteURL else { return }
        load(url)
    }

    func setPushToken(_ token: String) {
        pushToken = token
        injectPushToken()
    }

    private func injectPushToken() {
        guard let token = pushToken, let web, let url = web.url, !url.isFileURL else { return }
        let safe = token.filter { $0.isHexDigit }
        web.evaluateJavaScript("window.__aaNativePush={kind:'apns',token:'\(safe)'};window.dispatchEvent(new Event('aa:native-push'));")
    }

    private func showError() {
        guard let u = Bundle.main.url(forResource: "error", withExtension: "html") else { return }
        web.loadFileURL(u, allowingReadAccessTo: u.deletingLastPathComponent())
    }

    private func openExternal(_ url: URL) {
        UIApplication.shared.open(url, options: [:], completionHandler: nil)
    }
}

// MARK: - Նավիգացիա
extension WebViewController: WKNavigationDelegate {
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "app", url.host == "retry" {
            decisionHandler(.cancel)
            if let l = lastURL { load(l) }
            return
        }
        if url.isFileURL { decisionHandler(.allow); return }
        if navigationAction.shouldPerformDownload { decisionHandler(.download); return }
        if cfg.isAllowed(url) {
            if navigationAction.targetFrame == nil { web.load(navigationAction.request); decisionHandler(.cancel); return }
            decisionHandler(.allow)
            return
        }
        // tel:, mailto:, այլ կայքեր, App Store
        decisionHandler(.cancel)
        openExternal(url)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        // Կցված ֆայլեր (Content-Disposition: attachment) → ներբեռնում
        if let r = navigationResponse.response as? HTTPURLResponse,
           let cd = r.value(forHTTPHeaderField: "Content-Disposition"), cd.lowercased().contains("attachment") {
            decisionHandler(.download); return
        }
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        if let u = webView.url, !u.isFileURL { lastURL = u }
        progress.isHidden = false
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        progress.isHidden = true
        injectPushToken()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        if e.domain == NSURLErrorDomain, e.code == NSURLErrorCancelled { return }
        progress.isHidden = true
        showError()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        if e.domain == NSURLErrorDomain, e.code == NSURLErrorCancelled { return }
        progress.isHidden = true
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { webView.reload() }
}

// MARK: - UI (alert/confirm/prompt, WebRTC թույլտվություն, target=_blank)
extension WebViewController: WKUIDelegate {
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if cfg.isAllowed(url) { webView.load(navigationAction.request) } else { openExternal(url) }
        }
        return nil
    }

    @available(iOS 15.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(cfg.allowedHosts.contains(origin.host.lowercased()) ? .grant : .deny)
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
        present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        a.addTextField { $0.text = defaultText }
        a.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(nil) })
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(a.textFields?.first?.text) })
        present(a, animated: true)
    }
}

// MARK: - Ներբեռնում (PNG արտահանում, PDF և այլն) → share sheet
extension WebViewController: WKDownloadDelegate {
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("downloads", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let dest = dir.appendingPathComponent(suggestedFilename.isEmpty ? "aiauto-\(Int(Date().timeIntervalSince1970))" : suggestedFilename)
        try? FileManager.default.removeItem(at: dest)
        pendingDownloads[ObjectIdentifier(download)] = dest
        completionHandler(dest)
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let url = pendingDownloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        let share = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        share.popoverPresentationController?.sourceView = view
        share.popoverPresentationController?.sourceRect = CGRect(x: view.bounds.midX, y: view.bounds.midY, width: 1, height: 1)
        present(share, animated: true)
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        pendingDownloads.removeValue(forKey: ObjectIdentifier(download))
    }
}

private var pendingDownloads: [ObjectIdentifier: URL] = [:]
